# Architectural guard: input-only generation modules must NEVER set an expected
# answer. The sole writer of expected_* is generators.gen_expected (plus the
# documented stress-oracle / shrink carve-outs inside generators.py). This is a
# static source check, so a future change that quietly sets an expectation in an
# input-only module fails CI.

import pathlib
import re

MORVIX = pathlib.Path(__file__).resolve().parent.parent / "morvix"

# Modules that produce or handle INPUTS only - they must not assign any
# expected_* field on a case.
INPUT_ONLY_MODULES = [
    "importers",
    "assist",
    "fuzz",
    "properties",
    "metamorphic",
    "inference",
    "mutate",
    "schema",
    "catalog",
    "genlib",
    "distributions",
    "adversaries",
    "boundary",
    "enumerate_inputs",
    "combinatorial",
    "multitest",
    "snapshots",
    "hygiene",
    "grammar",
    "boundspec",
    "shapes",
    "pack",
]

_ASSIGN = re.compile(r"\.expected_(output|hash|exit|signal|files)\s*=")


def test_input_only_modules_never_set_expectations():
    offenders = []
    for name in INPUT_ONLY_MODULES:
        src = (MORVIX / f"{name}.py").read_text()
        if _ASSIGN.search(src):
            offenders.append(name)
    assert not offenders, f"input-only modules must not set expectations: {offenders}"


def test_only_gen_expected_and_carveouts_write_answers_in_generators():
    # In generators.py, expectations are written only by gen_expected and the
    # documented carve-outs (the stress oracle and shrink re-derive from the same
    # authority). Guard that no NEW driver starts writing them: the count of
    # functions that assign expected_* stays small and known.
    src = (MORVIX / "generators.py").read_text()
    funcs_with_expected = set()
    current = None
    for line in src.splitlines():
        m = re.match(r"def (\w+)\(", line)
        if m:
            current = m.group(1)
        if _ASSIGN.search(line) and current:
            funcs_with_expected.add(current)
    allowed = {
        "gen_expected",  # the sole legitimate answer source
        "_save_regression",  # stress: the oracle is the trusted authority
        "_set_observed_expectation",  # shrink: re-derives the solution's own observed exit/signal
        "_shrink_against_oracle",  # shrink: re-derives from the stress oracle
    }
    assert funcs_with_expected <= allowed, (
        f"unexpected functions write expected_*: {funcs_with_expected - allowed}"
    )
