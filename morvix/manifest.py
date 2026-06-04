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

from morvix import layout
from morvix.cases import list_groups, save_cases
from morvix.project import Project, Runner
from morvix.version import __version__


def build_manifest(project: Project) -> dict:
    """Assemble the manifest dict from live project state.

    Deliberately excludes the reference, brute-force and current solution paths:
    those are private and never travel in a package (Section 2.3).
    """
    return {
        "morvix": __version__,
        "name": project.name,
        "model": project.model,
        "locale": project.locale,
        "compare": project.compare,
        "limits": project.limits,
        "languages": project.languages,     # so a Receiver compiles with the same flags
        "raw_build": project.raw_build,
        "raw_run": project.raw_run,
        "groups": list_groups(project.cases),
        "cases": [c.to_dict() for c in project.cases],
        "runners": {name: r.to_dict() for name, r in project.runners.items()},
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
    )
    # Make sure the directories exist, then persist the adopted state.
    for d in layout.PROJECT_DIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)

    from morvix.cases import TestCase
    project.cases = [TestCase.from_dict(c) for c in m.get("cases", [])]
    project.runners = {name: Runner.from_dict(r) for name, r in m.get("runners", {}).items()}

    project.save()
    return project
