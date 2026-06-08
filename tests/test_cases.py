# Tests for the TestCase data model, focused on the additive provenance fields.

from morvix.cases import TestCase


def test_testcase_roundtrip_preserves_new_fields():
    c = TestCase(
        name="a",
        group="g",
        inputs={"stdin": ".morvix/tests/g/a.in"},
        tags=["random:ints", "edge"],
        note="why this exists",
        input_hash="deadbeef",
        provenance={"mode": "random", "seed": 7, "shape": "ints"},
    )
    back = TestCase.from_dict(c.to_dict())
    assert back.tags == ["random:ints", "edge"]
    assert back.note == "why this exists"
    assert back.input_hash == "deadbeef"
    assert back.provenance == {"mode": "random", "seed": 7, "shape": "ints"}


def test_to_dict_omits_empty_new_fields():
    d = TestCase(name="a", group="g").to_dict()
    for key in ("tags", "note", "input_hash", "provenance"):
        assert key not in d  # empty defaults stay out of the JSON


def test_old_cases_json_loads_with_defaults():
    # A pre-provenance case dict must load cleanly with empty defaults.
    old = {"name": "a", "group": "baseline", "manual": True, "inputs": {"stdin": "x.in"}}
    c = TestCase.from_dict(old)
    assert c.tags == [] and c.note is None and c.input_hash is None and c.provenance == {}
    # And it round-trips byte-stable (no new keys leak in).
    assert c.to_dict() == old
