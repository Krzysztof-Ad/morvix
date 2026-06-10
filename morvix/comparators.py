# Additional comparison strategies: float-tolerant, hash, and checker (special judge).
#
# Each function is registered at the bottom so compare.py can find them by name.
# See Section 14 of the design for how comparators fit into the overall judge pipeline.

import hashlib
import os
import tempfile

from morvix.compare import CompareInput, Verdict, make_diff, register_comparator

# --- float (Section 14.3) ---
#
# Tokenise both sides by whitespace and compare pairwise:
# - numeric pairs: pass if within eps_abs OR within eps_rel * max(|a|, |b|)
# - non-numeric pairs: must be byte-for-byte equal
# - token-count mismatch: immediate failure


def _float(ci: CompareInput) -> Verdict:
    eps_abs = ci.params.get("epsilon_abs", 1e-6)
    eps_rel = ci.params.get("epsilon_rel", 1e-9)

    obs_tokens = ci.observed.decode("utf-8", "replace").split()
    exp_tokens = ci.expected.decode("utf-8", "replace").split()

    if len(obs_tokens) != len(exp_tokens):
        detail = f"token count mismatch: expected {len(exp_tokens)}, got {len(obs_tokens)}"
        return Verdict(False, detail, diff=make_diff(ci.expected, ci.observed))

    for i, (a_tok, b_tok) in enumerate(zip(exp_tokens, obs_tokens)):
        # Fast path: identical strings always match (handles inf, nan, -inf, 1e400, etc.)
        if a_tok == b_tok:
            continue
        try:
            a = float(a_tok)
            b = float(b_tok)
            diff = abs(a - b)
            scale = max(abs(a), abs(b))
            if diff <= eps_abs or (scale > 0 and diff <= eps_rel * scale):
                continue
            detail = f"token {i}: expected {a_tok!r}, got {b_tok!r} (diff {diff})"
            return Verdict(False, detail, diff=make_diff(ci.expected, ci.observed))
        except ValueError:
            # Non-numeric: require exact equality.
            if a_tok != b_tok:
                detail = f"token {i}: expected {a_tok!r}, got {b_tok!r}"
                return Verdict(False, detail, diff=make_diff(ci.expected, ci.observed))

    return Verdict(True)


# --- hash (Section 14.5) ---
#
# Compute sha256 of the observed bytes; compare against case.expected_hash.
# No diff is produced for hash comparisons.


def _hash(ci: CompareInput) -> Verdict:
    observed_hex = hashlib.sha256(ci.observed).hexdigest()
    expected_hex = ci.case.expected_hash or ""
    if observed_hex == expected_hex:
        return Verdict(True)
    detail = f"hash mismatch: expected {expected_hex[:12]}..., got {observed_hex[:12]}..."
    return Verdict(False, detail)


# --- checker (Section 14.4) ---
#
# Delegate to an external special-judge program. The checker receives:
#   [checker_path, input_file, observed_file]
# Exit 0 means accepted; any other exit means rejected. The checker gets 4x the
# case's wall limit (the same headroom valgrind gets) so a looping checker can
# never hang the whole run.


def _checker_wall(params: dict) -> float:
    return (params.get("_wall") or 10) * 4


def _checker(ci: CompareInput) -> Verdict:
    checker_path = ci.params.get("checker")
    if not checker_path:
        return Verdict(False, "no checker configured")

    from morvix.process import run

    # Resolve the input file relative to the project root (may be None).
    input_rel = ci.case.primary_input()
    if input_rel is not None and ci.project is not None:
        input_file = os.path.join(ci.project.root, input_rel)
    else:
        input_file = os.devnull

    # Write observed bytes to a temporary file for the checker to read.
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="morvix-checker-")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(ci.observed)
        result = run([checker_path, input_file, tmp_path], wall_limit=_checker_wall(ci.params))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if result.timed_out:
        return Verdict(False, "checker timed out")
    if result.exit_code == 0:
        return Verdict(True)
    return Verdict(False, "checker rejected")


register_comparator("float", _float)
register_comparator("hash", _hash)
register_comparator("checker", _checker)
