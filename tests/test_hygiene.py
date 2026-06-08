# Tests for suite hygiene: content-hash dedup and the WL graph-iso key.

from morvix import hygiene
from morvix.cases import TestCase
from morvix.generators import gen_random


def test_content_hash_stable():
    # Stable across calls, equal for str and its utf-8 bytes, distinct for
    # different content, and the well-known sha256 of the empty input.
    assert hygiene.content_hash("hello") == hygiene.content_hash("hello")
    assert hygiene.content_hash("hello") == hygiene.content_hash(b"hello")
    assert hygiene.content_hash("hello") != hygiene.content_hash("world")
    assert (
        hygiene.content_hash(b"")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_dedup_pool_removes_byte_identical_generated(py_project):
    ctx, proj = py_project
    # 'int' with lo==hi yields the same bytes for every seed, so all five
    # generated cases are byte-identical: dedup keeps exactly one.
    gen_random(ctx, proj, "int", count=5, seed=1, group="baseline", params={"lo": 7, "hi": 7})
    assert len(proj.cases) == 5

    removed = hygiene.dedup_pool(proj)
    assert removed == 4
    assert len(proj.cases) == 1

    # The deleted cases' input files are gone; the survivor's remains.
    survivor = proj.cases[0]
    import os

    assert os.path.exists(os.path.join(proj.root, survivor.primary_input()))


def test_dedup_keeps_manual(py_project):
    ctx, proj = py_project
    # A manual case and several generated twins all share the same input bytes.
    manual = TestCase(
        name="hand",
        group="baseline",
        manual=True,
        inputs={"stdin": _write_input(proj, "hand", "7")},
    )
    manual.input_hash = hygiene.content_hash("7")
    proj.add_case(manual)
    gen_random(ctx, proj, "int", count=3, seed=1, group="baseline", params={"lo": 7, "hi": 7})

    removed = hygiene.dedup_pool(proj)
    # All three generated twins drop (they match the manual's bytes too); the
    # manual case survives untouched.
    assert removed == 3
    names = [c.name for c in proj.cases]
    assert "hand" in names
    assert sum(1 for c in proj.cases if not c.manual) == 0


def test_dedup_pool_group_scoped(py_project):
    ctx, proj = py_project
    gen_random(ctx, proj, "int", count=3, seed=1, group="alpha", params={"lo": 7, "hi": 7})
    gen_random(ctx, proj, "int", count=3, seed=1, group="beta", params={"lo": 7, "hi": 7})

    removed = hygiene.dedup_pool(proj, group="alpha")
    assert removed == 2
    assert sum(1 for c in proj.cases if c.group == "alpha") == 1
    assert sum(1 for c in proj.cases if c.group == "beta") == 3


def test_canonical_graph_key_path_vs_star():
    # A path 1-2-3-4-5 and a star (1 connected to 2..5) have the same n and m
    # but different structure, so their WL keys differ.
    path = "5\n1 2\n2 3\n3 4\n4 5"
    star = "5\n1 2\n1 3\n1 4\n1 5"
    assert hygiene.canonical_graph_key(path, True) != hygiene.canonical_graph_key(star, True)


def test_canonical_graph_key_relabel_invariant():
    # The same path written with the vertices renamed must yield the same key.
    path_a = "4\n1 2\n2 3\n3 4"
    path_b = "4\n4 3\n3 2\n2 1"  # reversed labelling of the same path
    path_c = "4\n2 1\n2 3\n3 4"  # another relabelling
    key = hygiene.canonical_graph_key(path_a, True)
    assert hygiene.canonical_graph_key(path_b, True) == key
    assert hygiene.canonical_graph_key(path_c, True) == key

    # A genuinely different shape (a triangle plus a pendant) does NOT collide.
    other = "4\n1 2\n2 3\n3 1\n3 4"
    assert hygiene.canonical_graph_key(other, False) != key


def test_existing_input_hashes(py_project):
    ctx, proj = py_project
    gen_random(ctx, proj, "int", count=2, seed=1, group="baseline", params={"lo": 7, "hi": 7})
    hashes = hygiene.existing_input_hashes(proj)
    # Both cases share the same input bytes, so exactly one distinct hash.
    assert hashes == {hygiene.content_hash("7")}


def _write_input(proj, name, text):
    import os

    from morvix.cases import default_input_relpath

    rel = default_input_relpath("baseline", name)
    path = os.path.join(proj.root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return rel
