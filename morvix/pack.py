# Generator-pack export/import (Section 13).
#
# A "pack" is a small, shareable .zip of an author's generator/grammar FILES -
# the recipes for making inputs, not inputs and never answers. Export bundles the
# selected files under .morvix/generators plus a tiny JSON manifest; import drops
# those files back into another project's .morvix/generators.
#
# Honesty is structural here: a pack carries CODE that PRODUCES inputs. Importing
# it only writes files to disk - it never executes the pack, never creates a test
# case, and never sets any expected_* field. A stray "*.py" that pretends to be a
# case is therefore harmless: it lands as one more generator file you can read
# before you ever choose to run it. Expected answers always come from
# gen --expected running your own solution.
#
# API:
#   export_pack(project, out_path, names=None, with_catalog=False) -> str
#   import_pack(project, path, force=False) -> ImportReport

import json
import os
import posixpath
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional

from morvix import layout
from morvix.errors import UserError

# The file kinds a pack carries: generator programs and declarative grammars.
# Anything else under generators/ is ignored on export (e.g. inferred schema
# sidecars are author-private and not portable recipes).
GENERATOR_EXTS = (".py",)
GRAMMAR_EXTS = (".gram",)
PACK_EXTS = GENERATOR_EXTS + GRAMMAR_EXTS

# Manifest filename inside the archive, and the format tag we stamp.
PACK_MANIFEST = "pack.json"
PACK_FORMAT = "morvix-pack/1"

# Where a pack's files live inside the archive (a flat subdir so the manifest
# sits cleanly beside them at the root).
PACK_PREFIX = "generators"


@dataclass
class ImportReport:
    """What an import did: which files landed, which were skipped, what was refused."""

    imported: List[str] = field(default_factory=list)  # relpaths written under generators/
    skipped: List[str] = field(default_factory=list)  # existed already (no --force)
    ignored: List[str] = field(default_factory=list)  # archive members we never write
    # Honesty bookkeeping: a pack must not try to ship cases or answers. Any such
    # member is recorded here and dropped - never acted on.
    dropped_answers: List[str] = field(default_factory=list)


def export_pack(
    project, out_path: str, names: Optional[List[str]] = None, with_catalog: bool = False
) -> str:
    """Bundle generator/grammar files under .morvix/generators into a .zip pack.

    names: an explicit list of file basenames (or relpaths) to include; default
    is every .py/.gram file in the generators dir. with_catalog also records the
    vetted catalog's entry names in the manifest (informational only - catalog
    code is never copied; the receiver has its own).

    Produces inputs-recipes only - no cases, no expected answers.
    """
    gens_dir = project.abspath(layout.GENERATORS_DIR)
    available = _list_generator_files(gens_dir)
    selected = _select(available, names)
    if not selected:
        raise UserError(
            "No generator or grammar files to pack.",
            hint="Write one with 'gen --new-generator' or 'gen --new-grammar' first.",
        )

    catalog_names = _catalog_names() if with_catalog else []
    man = {
        "format": PACK_FORMAT,
        "project": project.name,
        "files": list(selected),
        "catalog": catalog_names,
    }

    if not out_path.endswith(".zip"):
        out_path += ".zip"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(PACK_MANIFEST, json.dumps(man, indent=2) + "\n")
        for rel in selected:
            with open(os.path.join(gens_dir, rel), "rb") as f:
                zf.writestr(posixpath.join(PACK_PREFIX, rel), f.read())
    return out_path


def import_pack(project, path: str, force: bool = False) -> ImportReport:
    """Extract a pack's generator/grammar files into .morvix/generators.

    NEVER executes pack code, NEVER creates a test case, and NEVER sets any
    expected_* field. Only .py/.gram files are written; everything else in the
    archive (a stray .out/.ans, a nested case index, the manifest itself) is
    ignored. An existing same-named file is left alone unless force=True.
    """
    if not os.path.exists(path):
        raise UserError(f"No such pack: {path}")
    if not zipfile.is_zipfile(path):
        raise UserError(
            f"Not a pack archive: {path}",
            hint="A pack is a .zip made by 'gen --export-pack'.",
        )

    gens_dir = project.abspath(layout.GENERATORS_DIR)
    os.makedirs(gens_dir, exist_ok=True)
    report = ImportReport()

    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            member = info.filename
            if info.is_dir():
                continue
            rel = _safe_relname(member)
            if rel is None:
                report.ignored.append(member)
                continue
            # Honesty: a pack carries input recipes only. A member that looks
            # like a bundled answer is recorded and dropped, never written.
            if _looks_like_answer(rel):
                report.dropped_answers.append(member)
                continue
            # Only generator/grammar files are written. A stray "*.py" that is
            # dressed up as a case is still just written as a generator file -
            # it is never run and never becomes a case.
            if not rel.lower().endswith(PACK_EXTS):
                report.ignored.append(member)
                continue
            dest = os.path.join(gens_dir, rel)
            if os.path.exists(dest) and not force:
                report.skipped.append(rel)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as out:
                out.write(zf.read(member))
            report.imported.append(rel)
    return report


# --- internal helpers ---


def _list_generator_files(gens_dir: str) -> List[str]:
    """All .py/.gram files under generators/, as relpaths (sorted, recursive)."""
    out: List[str] = []
    if not os.path.isdir(gens_dir):
        return out
    for dirpath, _dirs, files in os.walk(gens_dir):
        for fn in files:
            if fn.lower().endswith(PACK_EXTS):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, gens_dir)
                out.append(rel.replace(os.sep, "/"))
    return sorted(out)


def _select(available: List[str], names: Optional[List[str]]) -> List[str]:
    """Resolve a requested name list against the available files.

    A name may be a full relpath, a bare basename, or carry no extension; the
    first match wins. An unmatched name is a UserError so a typo is loud.
    """
    if not names:
        return list(available)
    by_base = {os.path.basename(rel): rel for rel in available}
    chosen: List[str] = []
    for raw in names:
        want = raw.replace(os.sep, "/").strip()
        match = None
        if want in available:
            match = want
        elif want in by_base:
            match = by_base[want]
        else:
            # Allow naming without the extension (e.g. "mygen" -> "mygen.py").
            for ext in PACK_EXTS:
                if want + ext in by_base:
                    match = by_base[want + ext]
                    break
        if match is None:
            raise UserError(
                f"No such generator/grammar to pack: {raw}",
                hint="Names are files under .morvix/generators (e.g. mygen.py, mygram.gram).",
            )
        if match not in chosen:
            chosen.append(match)
    return chosen


def _safe_relname(member: str) -> Optional[str]:
    """Strip the pack prefix and reject unsafe paths; return a clean relpath.

    Guards against zip-slip: absolute paths, drive letters and "..". Members
    outside the pack's generators/ subdir are accepted as bare files too, so a
    pack written by another tool still imports its top-level *.py.
    """
    name = member.replace("\\", "/")
    if name.startswith(PACK_PREFIX + "/"):
        name = name[len(PACK_PREFIX) + 1 :]
    name = name.lstrip("/")
    if not name:
        return None
    if os.path.isabs(name) or ":" in name:
        return None
    parts = name.split("/")
    if any(p in ("", "..", ".") for p in parts):
        return None
    return "/".join(parts)


def _looks_like_answer(rel: str) -> bool:
    """True if a member looks like a bundled answer (it must never be written)."""
    lower = rel.lower()
    return lower.endswith((".out", ".ans", ".expected")) or "/expected/" in lower


def _catalog_names() -> List[str]:
    """The vetted catalog's entry names, if the catalog module is present.

    Informational only: the manifest records which catalog generators a pack was
    built alongside; the catalog code itself is never copied (the receiver has
    its own). Returns [] when no catalog is available.
    """
    try:
        from morvix import catalog
    except Exception:
        return []
    try:
        return sorted(e.name for e in catalog.list_entries())
    except Exception:
        return []
