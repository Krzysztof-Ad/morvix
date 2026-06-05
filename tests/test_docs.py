# Tests for the generated user guide (morvix/docs.py + the docs command).
#
# The point of the feature is that the guide is generated from the single
# sources, so these tests assert it actually covers the live command surface,
# and that the --check freshness gate works.

from morvix import docs, registry
from morvix.context import Context
from morvix.theme import make_console


def _ctx(tmp_path):
    return Context.create(str(tmp_path), interactive=False, console=make_console(force_plain=True))


def test_full_markdown_lists_every_command():
    md = docs.full_markdown()
    for name in registry.command_names():
        if name == "quit":            # an alias, not its own entry
            continue
        assert "`%s`" % name in md, f"guide is missing command: {name}"
    assert "## Command reference" in md
    for cap in ("Languages", "Execution models", "Comparison strategies", "Random shapes"):
        assert cap in md


def test_topic_md_known_and_unknown():
    assert docs.topic_md("generators") is not None    # a concept
    assert docs.topic_md("run") is not None           # a command
    assert docs.topic_md("not-a-real-topic") is None


def test_docs_check_detects_staleness(tmp_path):
    ctx = _ctx(tmp_path)
    guide = tmp_path / "GUIDE.md"
    assert registry.safe_dispatch(ctx, ["docs", "--out", str(guide)]) == 0
    # Fresh file matches the generated output.
    assert registry.safe_dispatch(ctx, ["docs", "--check", "--out", str(guide)]) == 0
    # A stale file is detected and reported as a failure.
    guide.write_text("stale\n")
    assert registry.safe_dispatch(ctx, ["docs", "--check", "--out", str(guide)]) == 1
