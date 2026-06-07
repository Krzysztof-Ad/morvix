# Multi-test wrapper: assemble several sub-inputs into one T-headed file.
#
# Many judges read a single file that starts with a test count T and is followed
# by T independent sub-inputs back to back. This module just does the packaging:
# given a list of already-generated input strings, emit the combined text with
# the right header. It produces INPUTS only and never touches expected answers.
#
# Two layouts:
#   t-first   T on its own line, then each sub-input kept intact (one block per
#             test, each newline-terminated). This is the common case where a
#             sub-input may itself span several lines (e.g. an array length then
#             the array).
#   per-line  T on its own line, then one sub-input per line, each stripped to a
#             single token/line. For problems where every test is a one-liner.
#
# auto_t_sizes picks a few useful T values (1 / a small T / the max T) so callers
# can emit smoke (T=1), typical, and stress (max-T) variants of a multi-test file.

from typing import List


def wrap(subinputs: List[str], layout: str = "t-first") -> str:
    """Combine sub-inputs into one multi-test file with a 'T' header.

    The header is the number of sub-inputs. 't-first' keeps each sub-input intact
    and newline-terminated; 'per-line' puts one stripped sub-input per line.
    """
    t = len(subinputs)
    if layout == "per-line":
        lines = [str(t)] + [s.strip() for s in subinputs]
        return "\n".join(lines) + "\n" if subinputs else f"{t}\n"
    if layout == "t-first":
        # - each block is the sub-input with exactly one trailing newline
        blocks = [s if s.endswith("\n") else s + "\n" for s in subinputs]
        return f"{t}\n" + "".join(blocks)
    raise ValueError(f"Unknown multi-test layout '{layout}'. Choose: t-first, per-line.")


def auto_t_sizes(max_t: int) -> List[int]:
    """A small set of T values to emit variants for: 1, a small T, and max_t.

    Values are clamped to >= 1, de-duplicated and sorted. The 'small' rung is a
    tenth of max_t (at least 2) so it sits between the smoke and stress sizes.
    """
    top = max(1, int(max_t))
    small = max(2, top // 10)
    sizes = {1, small, top}
    # - never propose a T above the requested maximum
    return sorted(s for s in sizes if 1 <= s <= top)
