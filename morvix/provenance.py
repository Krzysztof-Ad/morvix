# Provenance: how a case was made, and which solution froze its answer.
#
# Every generated case carries a small "recipe" (mode + the seed/shape/params/
# generator that produced it) plus a hash of its input bytes, so a teammate - or
# a future you - can re-derive it and detect drift. The answer-side fingerprint
# records WHICH program's output was frozen as the expected answer, so a stale
# answer is visible after the solution changes. This module is the single home
# for that bookkeeping; generators stamp it, the manifest rolls it up.

import hashlib
import json
import os
from typing import Dict, List, Optional


def hash_bytes(data: bytes) -> str:
    """The sha256 hex digest of some bytes - the content address we use everywhere."""
    return hashlib.sha256(data).hexdigest()


def case_input_bytes(case, root: str) -> Optional[bytes]:
    """The raw bytes of a case's primary input file, or None if it has none."""
    rel = case.primary_input()
    if not rel:
        return None
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def compute_input_hash(case, root: str) -> Optional[str]:
    """sha256 of the case's primary input, or None when there is no input file."""
    data = case_input_bytes(case, root)
    return hash_bytes(data) if data is not None else None


def ensure_input_hash(project, case) -> Optional[str]:
    """Compute and store the case's input hash on it; return the hash."""
    case.input_hash = compute_input_hash(case, project.root)
    return case.input_hash


def make_record(mode: str, **kw) -> Dict:
    """A provenance dict for one case: the mode plus whichever keys are set.

    None-valued keys are dropped so the stored recipe stays minimal.
    """
    rec = {"mode": mode}
    for key, value in kw.items():
        if value is not None:
            rec[key] = value
    return rec


def solution_fingerprint(project) -> str:
    """A stable id for the answer-producing program + how it is built/run.

    Changes whenever the solution source or its build/run configuration changes,
    so a frozen answer can be recognised as stale after the solution is edited.
    """
    from morvix.adapters import detect_language

    sol = project.solution
    if not sol:
        return ""
    try:
        with open(project.abspath(sol) if not os.path.isabs(sol) else sol, "rb") as f:
            src = hash_bytes(f.read())
    except OSError:
        src = ""
    language = project.language or detect_language(sol) or ""
    parts = [
        src,
        language,
        project.raw_build or "",
        project.raw_run or "",
        project.lang_config(language) if language else {},
    ]
    return "sha256:" + hash_bytes(json.dumps(parts, sort_keys=True).encode("utf-8"))


def group_recipes(cases: List) -> Dict:
    """A read-only per-group rollup of how each group's cases were generated.

    Best-effort: summarises the dominant mode, shape, base seed and count so the
    manifest can describe a group's origin without storing every case's recipe
    twice (each case already carries its own provenance).
    """
    recipes: Dict[str, Dict] = {}
    for case in cases:
        prov = getattr(case, "provenance", None)
        if not prov or case.manual:
            continue
        g = case.group
        roll = recipes.setdefault(g, {"count": 0})
        roll["count"] += 1
        for key in (
            "mode",
            "shape",
            "generator",
            "generator_hash",
            "grammar",
            "source_hash",
            "lib",
        ):
            if key in prov and key not in roll:
                roll[key] = prov[key]
        if "params" in prov and "params" not in roll:
            roll["params"] = prov["params"]
        seed = prov.get("seed")
        if isinstance(seed, int):
            roll["base_seed"] = min(roll.get("base_seed", seed), seed)
    return recipes
