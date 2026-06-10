# Model-assisted scaffolding (Section 26) - OFF by default, honesty-gated.
#
# Morvix never calls a model or the network itself. If you opt in, you point it
# at YOUR own executable hook; Morvix runs it with a JSON request on stdin and
# reads a JSON response on stdout. The hook is where any API call happens.
#
# The hard guarantee: a model can only ever contribute INPUTS or generator CODE,
# never an answer. sanitize_response rebuilds the response from scratch, copying
# only an allow-list of keys - so an "expected"/"answer"/"output" field a model
# (or a prompt-injected sample) tries to sneak in is simply discarded. Suggested
# inputs are inert until you run gen --expected, which is still the sole source
# of expected answers.

import json
import os
import subprocess
import sys

from morvix import layout
from morvix.errors import UserError

ASSIST_VERSION = 1
SCAFFOLD_HEADER = (
    "# UNVERIFIED model-suggested generator - REVIEW before trusting it.\n"
    "# Morvix did not run or check this. Expected answers still come only from\n"
    "# 'gen --expected' running your own solution.\n"
)


def build_request(kind, project, prompt=None, samples=None):
    """The JSON request handed to the hook. Carries context, never an answer."""
    return {
        "morvix_assist": ASSIST_VERSION,
        "kind": kind,  # "scaffold" (generator code) or "inputs" (candidate inputs)
        "language": project.language,
        "model": project.model,
        "prompt": prompt or "",
        "samples": list(samples or []),
        "note": (
            'Return JSON. For kind=scaffold: {"generator": "<python source>"}. '
            'For kind=inputs: {"inputs": ["<input text>", ...]}. '
            "Do NOT include expected outputs or answers - they are ignored."
        ),
    }


def call_hook(hook_path, request, timeout=60):
    """Run the user's hook, feeding the request JSON on stdin; parse JSON stdout.

    Morvix makes no network calls - the hook does, with the user's own key.
    """
    if not os.path.isfile(hook_path):
        raise UserError(f"Hook not found: {hook_path}", hint="Point --hook at your executable.")
    if os.name == "posix" and os.access(hook_path, os.X_OK):
        argv = [hook_path]
    else:  # assume a Python script; works on Windows too
        argv = [sys.executable or "python3", hook_path]
    try:
        res = subprocess.run(
            argv,
            input=json.dumps(request).encode("utf-8"),
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise UserError(f"The hook timed out after {timeout}s.") from e
    except OSError as e:
        raise UserError(f"Could not run the hook: {e}") from e
    if res.returncode != 0:
        raise UserError(
            "The hook exited non-zero.",
            hint=res.stderr.decode("utf-8", "replace")[:400] or None,
        )
    try:
        return json.loads(res.stdout.decode("utf-8", "replace"))
    except (json.JSONDecodeError, ValueError) as e:
        raise UserError("The hook did not return valid JSON.") from e


def sanitize_response(kind, raw):
    """Rebuild the response from scratch with only safe keys.

    This is the honesty firewall: whatever the hook returned, we keep ONLY the
    generator source (scaffold) or the input strings (inputs). Any answer-shaped
    key is never copied, so it cannot reach an expected_* field.
    """
    clean = {"morvix_assist": ASSIST_VERSION, "kind": kind}
    if not isinstance(raw, dict):
        return clean
    if kind == "scaffold":
        gen = raw.get("generator")
        if isinstance(gen, str):
            clean["generator"] = gen
    elif kind == "inputs":
        items = raw.get("inputs")
        if isinstance(items, list):
            clean["inputs"] = [str(x) for x in items]
    return clean


def write_scaffold(project, name, generator_source):
    """Write a model-suggested generator with an UNVERIFIED header; never run it."""
    if not name.endswith(".py"):
        name += ".py"
    rel = os.path.join(layout.GENERATORS_DIR, name)
    path = os.path.join(project.root, rel)
    if os.path.exists(path):
        raise UserError(f"Generator already exists: {name}", hint="Pick another --name.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(SCAFFOLD_HEADER + "\n" + (generator_source or ""))
    return rel
