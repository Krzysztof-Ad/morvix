# Input validators: gate that generated inputs are well-formed (Section 13).
#
# A validator is a tiny program that reads ONE input on stdin and exits 0 if the
# input is well-formed, non-zero otherwise. It is the input-side counterpart of a
# comparator: a comparator judges output, a validator judges input. The crucial
# difference - and the honesty boundary - is that a validator sees inputs ONLY.
# It never reads, writes or computes an expected answer; it runs BEFORE answers
# are frozen by gen --expected, and its verdict is purely "is this input shaped
# the way my program expects to read it".
#
# We build and run a validator exactly the way a generator or the solution is
# built and run: get_adapter(...).build once, then process.run per input. If the
# language's toolchain is missing we degrade with an honest result rather than
# pretending every input passed.

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional

from morvix import layout, process, provenance
from morvix.adapters import detect_language, get_adapter
from morvix.errors import MorvixError, UserError

# A starter validator the user edits to match their program's input format.
# It reads ALL of stdin, checks a shape rule, and exits 0 (well-formed) or 1.
# It must never read or assert an expected answer - inputs only.
VALIDATOR_TEMPLATE = """#!/usr/bin/env python3
# A Morvix input validator: read ONE input on stdin, exit 0 if it is
# well-formed and non-zero otherwise. Inputs ONLY - never read, compute or
# print an expected answer; correctness of the answer is not your job.
#
# Morvix runs this once per input as:  python3 <thisfile>  < input
# Edit check() so it accepts exactly what your program is allowed to read.
#
#   gen --validate                 # run the saved validator over your cases
#   gen --random --require-valid   # resample until inputs pass the validator

import sys


def check(text):
    # TODO: replace with your program's real input contract.
    # Example below: first line is an integer n, then n whitespace-separated
    # numbers follow. Returns True when the input is well-formed.
    tokens = text.split()
    if not tokens:
        return False
    try:
        n = int(tokens[0])
    except ValueError:
        return False
    rest = tokens[1:]
    if len(rest) != n:
        return False
    for tok in rest:
        try:
            int(tok)
        except ValueError:
            return False
    return True


def main():
    text = sys.stdin.read()
    sys.exit(0 if check(text) else 1)


if __name__ == "__main__":
    main()
"""

VALIDATOR_EXT = ".py"

# A generous wall limit: a validator just parses one input, it should be quick.
_VALIDATE_WALL = 30.0


@dataclass
class ValidationResult:
    """The outcome of validating one input.

    - valid:    True if the validator exited 0 (well-formed).
    - exit_code: the validator's exit code (None if it was signalled/timed out).
    - degraded: True when we could NOT actually run the validator (missing
      toolchain, no input file): the input was neither confirmed nor rejected.
    - message:  a short human reason, present on degrade or rejection.
    - case_id:  the case this result belongs to (None for an ad-hoc text check).
    """

    valid: bool
    exit_code: Optional[int] = None
    degraded: bool = False
    message: str = ""
    case_id: Optional[str] = None


# Write text to an absolute path, creating parent dirs first. newline="" so
# the bytes survive Windows untranslated (scaffolds must run as written).
def _write_text(abspath, text):
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _default_validator_relpath():
    """Where the saved/default validator lives under generators/."""
    return os.path.join(layout.GENERATORS_DIR, "validate" + VALIDATOR_EXT)


def new_validator(ctx, project, name="validate"):
    """Write a starter validator into generators/ and return its relative path."""
    if not name.endswith(VALIDATOR_EXT):
        name += VALIDATOR_EXT
    rel = os.path.join(layout.GENERATORS_DIR, name)
    path = project.abspath(rel)
    if os.path.exists(path):
        raise UserError(
            f"Validator already exists: {name}",
            hint="Pick another name, or edit the existing one.",
        )
    _write_text(path, VALIDATOR_TEMPLATE)
    if ctx is not None and getattr(ctx, "interactive", False):
        ctx.messenger.info(f"Edit the validator at {rel}")
    return rel


def resolve_validator(project, explicit=None):
    """Pick which validator to use: explicit arg, then the project config, then
    the default scaffold path. Returns an absolute path (which may not exist yet -
    callers that need it present check and raise/degrade themselves)."""
    rel = explicit or getattr(project, "validator", None) or _default_validator_relpath()
    if os.path.isabs(rel):
        return rel
    return project.abspath(rel)


# Build the validator once and return (check_text, cleanup). check_text(bytes)
# runs it on one input and returns a ValidationResult. Raises MorvixError if the
# toolchain is missing or the build fails, so callers can degrade honestly.
def _compile_validator(project, validator_path):
    language = detect_language(validator_path)
    if not language:
        raise MorvixError(
            f"Could not detect the language of '{os.path.basename(validator_path)}'.",
            hint="Use a recognised extension (.py, .c, .cpp, ...).",
        )
    workdir = tempfile.mkdtemp(prefix="morvix-validate-")
    try:
        adapter = get_adapter(language)
        build = adapter.build(validator_path, project.lang_config(language), workdir)
    except MorvixError:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    if not build.ok:
        shutil.rmtree(workdir, ignore_errors=True)
        raise MorvixError(build.error or "validator build failed", hint=build.diagnostics)
    spec = adapter.run_spec(build, project.lang_config(language))

    def check_text(data):
        # The validator sees INPUT bytes on stdin and nothing else. Its exit code
        # is the whole verdict; we never look at (or trust) anything it prints.
        res = process.run(
            spec.argv,
            stdin=data,
            cwd=workdir,
            env=process.base_env(project.locale, spec.env),
            wall_limit=_VALIDATE_WALL,
        )
        if res.timed_out:
            return ValidationResult(
                valid=False, exit_code=None, message="validator timed out on this input"
            )
        if res.signaled:
            name = res.describe_exit()
            return ValidationResult(valid=False, exit_code=None, message=f"validator {name}")
        return ValidationResult(valid=res.exit_code == 0, exit_code=res.exit_code)

    def cleanup():
        shutil.rmtree(workdir, ignore_errors=True)

    return check_text, cleanup


def _degraded(reason, case_id=None):
    return ValidationResult(valid=False, degraded=True, message=reason, case_id=case_id)


def validate_cases(project, cases, validator_path):
    """Validate each case's primary input against the validator.

    Returns one ValidationResult per case, in order. If the validator cannot be
    built (no toolchain, build failure) every case degrades with an honest reason
    instead of crashing or pretending the inputs are fine.
    """
    if not cases:
        return []
    try:
        check_text, cleanup = _compile_validator(project, validator_path)
    except MorvixError as e:
        reason = e.message + (f" ({e.hint})" if e.hint else "")
        return [_degraded(reason, case_id=c.id) for c in cases]

    results = []
    try:
        for case in cases:
            data = provenance.case_input_bytes(case, project.root)
            if data is None:
                results.append(_degraded("no input file to validate", case_id=case.id))
                continue
            res = check_text(data)
            res.case_id = case.id
            results.append(res)
    finally:
        cleanup()
    return results


def is_valid(project, text, validator_path):
    """True if the validator accepts one input string. Degrades to True (an honest
    'we could not check, so do not block') when the toolchain is missing - the
    same direction validate_cases reports as degraded, but as a simple bool here
    so resampling callers never loop forever against a missing validator."""
    try:
        check_text, cleanup = _compile_validator(project, validator_path)
    except MorvixError:
        return True
    try:
        res = check_text(text.encode("utf-8") if isinstance(text, str) else text)
    finally:
        cleanup()
    return res.valid
