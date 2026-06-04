# The correctness disclaimer is a default (Section 17.4) and defaults silently
# regress, so we assert it appears both in generated README text and in the
# README.md that actually ships inside a package.

import zipfile

from morvix.cases import TestCase
from morvix.project import Project
from morvix.readme import generate_readme
from morvix import packaging

DISCLAIMER = "does not prove correctness"


def test_generate_readme_includes_disclaimer(tmp_path):
    proj = Project.create(str(tmp_path), "r")
    assert DISCLAIMER in generate_readme(proj)


def test_packaged_readme_includes_disclaimer(tmp_path, make_ctx):
    proj = Project.create(str(tmp_path), "r")
    proj.language = "python"
    (tmp_path / "tests" / "baseline").mkdir(parents=True)
    (tmp_path / "expected" / "baseline").mkdir(parents=True)
    (tmp_path / "tests" / "baseline" / "a.in").write_text("1 2\n")
    (tmp_path / "expected" / "baseline" / "a.out").write_text("3\n")
    proj.add_case(TestCase(name="a", group="baseline", manual=True,
                           inputs={"stdin": "tests/baseline/a.in"},
                           expected_output="expected/baseline/a.out"))
    proj.save()
    ctx = make_ctx(tmp_path)
    ctx.project = proj
    out = str(tmp_path / "pkg.zip")
    packaging.build_package(ctx, proj, fmt="zip", out=out)
    with zipfile.ZipFile(out) as z:
        readme = z.read("README.md").decode("utf-8")
    assert DISCLAIMER in readme
