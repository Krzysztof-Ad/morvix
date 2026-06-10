# The manifest, morvix.json (Section 20, Section 25.3).
#
# The manifest is the generated, shareable face of a project. It describes the
# whole harness - model, comparison, limits, locale, the case index, the runner
# definitions and the Author's own results - so that opening Morvix in the
# directory yields full understanding before any code is read. It is purely
# additive: a Receiver without Morvix never needs it, and it is regenerated from
# the editable config whenever the project is saved.

import json
import os
from typing import Optional

from morvix import layout, provenance
from morvix.cases import list_groups
from morvix.project import Project, Runner
from morvix.version import __version__


def build_manifest(project: Project) -> dict:
    """Assemble the manifest dict from live project state.

    Deliberately excludes the current solution path and any rival source paths:
    those are private and never travel in a package (Section 2.3).
    """
    return {
        "morvix": __version__,
        "name": project.name,
        "language": project.language,  # so the runner builds with the right toolchain
        "model": project.model,
        "locale": project.locale,
        "compare": project.compare,
        "limits": project.limits,
        "languages": project.languages,  # so a Receiver compiles with the same flags
        "raw_build": project.raw_build,
        "raw_run": project.raw_run,
        "interactor": project.interactor,  # judge program for the interactive model
        "groups": list_groups(project.cases),
        "cases": [c.to_dict() for c in project.cases],
        "runners": {name: r.to_dict() for name, r in project.runners.items()},
        # A read-only rollup of how each group was generated (each case also
        # carries its own provenance); omitted when there's nothing to describe.
        "recipes": provenance.group_recipes(project.cases),
        "author_results": _load_author_results(project.root),
    }


def write_manifest(project: Project) -> str:
    path = os.path.join(project.root, layout.MANIFEST)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_manifest(project), f, indent=2)
        f.write("\n")
    return path


def _load_author_results(root: str) -> Optional[dict]:
    # The Author's own per-case results power the Receiver's diff (Section 20.2).
    path = os.path.join(root, layout.RESULTS_DIR, "author.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def adopt_manifest(root: str) -> Project:
    """Turn a received package (manifest only) into an editable project.

    Reads morvix.json, reconstructs config + the case index + runner profiles,
    and writes them out so the Receiver can work with the harness directly
    (Section 19.4, Section 20.3).
    """
    with open(os.path.join(root, layout.MANIFEST), "r", encoding="utf-8") as f:
        m = json.load(f)

    project = Project(
        root=root,
        name=m.get("name", os.path.basename(os.path.abspath(root))),
        model=m.get("model", "stdio"),
        locale=m.get("locale", "C"),
        compare=m.get("compare", {}),
        limits=m.get("limits", {}),
        languages=m.get("languages", {}),
        raw_build=m.get("raw_build"),
        raw_run=m.get("raw_run"),
        language=m.get("language"),
        # Back-compat: older manifests stored the interactor in the languages map.
        interactor=m.get("interactor") or m.get("languages", {}).get("interactor"),
    )
    # Make sure the directories exist, then persist the adopted state.
    for d in layout.PROJECT_DIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)

    from morvix.cases import TestCase

    # A package's manifest stores case paths package-relative (tests/...); inside
    # a project they live under .morvix/, so re-prefix them as we adopt.
    cases = []
    for c in m.get("cases", []):
        tc = TestCase.from_dict(c)
        tc.inputs = {k: _under_state(v) for k, v in tc.inputs.items()}
        if tc.expected_output:
            tc.expected_output = _under_state(tc.expected_output)
        cases.append(tc)
    project.cases = cases
    project.runners = {name: Runner.from_dict(r) for name, r in m.get("runners", {}).items()}

    project.save()
    return project


def _under_state(p: str) -> str:
    """Make a package-relative path (tests/...) project-relative (.morvix/tests/...)."""
    if p.startswith(layout.STATE_DIR + os.sep) or p.startswith(layout.STATE_DIR + "/"):
        return p
    return os.path.join(layout.STATE_DIR, p)
