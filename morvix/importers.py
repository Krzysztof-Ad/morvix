# Corpus import: turn existing input files into cases - and strip any answers.
#
# A student often already has a folder of test inputs (a downloaded archive, a
# pile of .in files, a contest's sample tests). This module ingests those as
# input-only cases so they can be judged against the solution. It accepts a
# directory, a glob, or a .zip and walks it, treating .in/.txt as inputs.
#
# HONESTY (the load-bearing rule): a corpus often ships the author's answers
# alongside the inputs (.out/.ans/.exp). Those are someone else's claim about the
# right answer, not an authority - so we DROP them. They are recorded in the
# summary so the user knows what was discarded, and with --keep-answers they are
# parked in an inert 'imported_advisory/' folder for human reference ONLY. This
# module NEVER sets an expected_* field on a case; the sole writer of expected
# answers is gen --expected, which runs the student's own solution.

import os
import zipfile
from dataclasses import dataclass, field
from glob import glob
from typing import List, Optional, Tuple

from morvix import hygiene, layout, provenance
from morvix.cases import TestCase, default_input_relpath
from morvix.errors import UserError

# Extensions we treat as program INPUTS.
INPUT_EXTS = {".in", ".txt", ".dat", ".input"}

# Extensions we treat as bundled ANSWERS - always stripped, never an expectation.
ANSWER_EXTS = {".out", ".ans", ".exp", ".expected", ".sol", ".output"}

# Where an inert copy of a stripped answer lands under --keep-answers. It sits
# under the project's generators tree (author-side, never shipped in a package)
# and is plain reference material - nothing reads it back as an expectation.
ADVISORY_DIRNAME = "imported_advisory"


@dataclass
class ImportSummary:
    """What an import did, for the report and for tests to assert against."""

    created: List[TestCase] = field(default_factory=list)  # cases actually written
    stripped_answers: List[str] = field(default_factory=list)  # answer files we dropped
    advisory_written: List[str] = field(default_factory=list)  # inert copies, if --keep-answers
    skipped_duplicates: int = 0  # inputs dropped as byte-identical
    skipped_empty: int = 0  # input files that were empty/whitespace
    split_files: int = 0  # multi-test files we split apart
    sub_cases: int = 0  # sub-inputs produced by splitting
    source: Optional[str] = None  # the resolved source path
    group: str = "imported"  # destination group
    dry_run: bool = False

    @property
    def created_count(self) -> int:
        return len(self.created)


def import_corpus(
    ctx,
    project,
    path,
    group="imported",
    split=False,
    keep_answers=False,
    dry_run=False,
    dedup=True,
):
    """Import inputs from a directory, glob, or .zip as input-only cases.

    - .in/.txt-style files become cases (inputs only, no expected_*).
    - .out/.ans-style files are DROPPED (honesty); recorded in stripped_answers,
      and with keep_answers copied into an inert advisory folder.
    - split=True breaks a 'T then T sub-inputs' multi-test file into one case each.
    - dedup=True skips inputs byte-identical to one already imported or present.
    - dry_run=True previews everything without writing a single file.

    Returns an ImportSummary. The caller saves the project (skipped on dry_run).
    """
    summary = ImportSummary(source=str(path), group=group, dry_run=dry_run)

    members = _resolve_members(path)
    if not members:
        raise UserError(
            f"Nothing to import from: {path}",
            hint="Point at a directory, a glob (e.g. tests/*.in), or a .zip archive.",
        )

    # Seed the dedup set with inputs already in the project so a re-import of the
    # same corpus does not create twins.
    seen = hygiene.existing_input_hashes(project) if dedup else set()

    # Track the next free case index so generated names never collide on disk.
    counter = [_next_index(project, group)]

    for relname, data in members:
        ext = _ext(relname)
        if ext in ANSWER_EXTS:
            # An answer file: drop it, record it, optionally park an inert copy.
            summary.stripped_answers.append(relname)
            if keep_answers and not dry_run:
                advisory_rel = _write_advisory(project, group, relname, data)
                summary.advisory_written.append(advisory_rel)
            continue
        if ext not in INPUT_EXTS:
            # Not an input we recognise and not an answer - ignore quietly.
            continue

        text = _decode(data)
        if split:
            subinputs = _split_multitest(text)
            if len(subinputs) > 1:
                summary.split_files += 1
                for sub in subinputs:
                    _ingest_one(project, group, sub, summary, seen, dedup, dry_run, counter)
                    summary.sub_cases += 1
                continue
        _ingest_one(project, group, text, summary, seen, dedup, dry_run, counter)

    return summary


# Take one input text and (unless it is empty or a duplicate) write it as a case.
def _ingest_one(project, group, text, summary, seen, dedup, dry_run, counter):
    if not text.strip():
        summary.skipped_empty += 1
        return None
    h = hygiene.content_hash(text)
    if dedup and h in seen:
        summary.skipped_duplicates += 1
        return None
    seen.add(h)

    name = f"imp{counter[0]}"
    counter[0] += 1
    rel = default_input_relpath(group, name)
    case = TestCase(
        name=name,
        group=group,
        manual=False,
        inputs={"stdin": rel},
        tags=["import"],
        provenance=provenance.make_record("import"),
    )
    if dry_run:
        # Preview only: stamp the hash from the in-memory text, write nothing.
        case.input_hash = h
        summary.created.append(case)
        return case
    _write(project.abspath(rel), text)
    provenance.ensure_input_hash(project, case)
    project.add_case(case)
    summary.created.append(case)
    return case


# ---------------------------------------------------------------------------
# Source resolution: directory, glob, or .zip -> list of (name, bytes)
# ---------------------------------------------------------------------------


def _resolve_members(path) -> List[Tuple[str, bytes]]:
    """Read every candidate file from a directory, glob, or .zip into memory.

    Returns (display-name, raw-bytes) pairs, sorted by name for determinism.
    """
    path = str(path)
    if path.lower().endswith(".zip") and os.path.isfile(path):
        return _read_zip(path)
    if os.path.isdir(path):
        return _read_tree(path)
    matches = sorted(glob(path))
    if matches:
        return [(os.path.basename(p), _read_file(p)) for p in matches if os.path.isfile(p)]
    if os.path.isfile(path):
        return [(os.path.basename(path), _read_file(path))]
    return []


def _read_tree(root) -> List[Tuple[str, bytes]]:
    out: List[Tuple[str, bytes]] = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            out.append((rel, _read_file(full)))
    out.sort(key=lambda pair: pair[0])
    return out


def _read_zip(path) -> List[Tuple[str, bytes]]:
    out: List[Tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                out.append((info.filename, zf.read(info)))
    except zipfile.BadZipFile as e:
        raise UserError(f"Not a readable .zip: {path}", hint="Check the archive is intact.") from e
    out.sort(key=lambda pair: pair[0])
    return out


def _read_file(path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _ext(name) -> str:
    return os.path.splitext(name)[1].lower()


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _split_multitest(text) -> List[str]:
    """Split a 'T then T sub-inputs' file into its sub-inputs (best-effort).

    Reads the first token as the test count T, then takes the next T non-empty
    lines as one sub-input each. This matches the common one-line-per-test corpus
    layout; a file whose first token is not a sane T is returned whole (one item).
    """
    lines = text.splitlines()
    if not lines:
        return [text]
    head = lines[0].split()
    if not head:
        return [text]
    try:
        t = int(head[0])
    except ValueError:
        return [text]
    rest = [ln for ln in lines[1:] if ln.strip()]
    if t < 1 or t != len(rest):
        # Not a clean one-line-per-test file - leave it intact rather than guess.
        return [text]
    return rest


def _write(abspath, text) -> None:
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "w", encoding="utf-8") as f:
        f.write(text)


def _write_advisory(project, group, relname, data) -> str:
    """Park a stripped answer in an inert advisory folder. Returns its relpath.

    This is reference material for a human only: it lives under the author-side
    generators tree (excluded from packages) and is NEVER read as an expectation.
    """
    safe = relname.replace(os.sep, "_").replace("/", "_")
    rel = os.path.join(layout.GENERATORS_DIR, ADVISORY_DIRNAME, group, safe)
    abspath = project.abspath(rel)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "wb") as f:
        f.write(data)
    return rel


def _next_index(project, group) -> int:
    """The next free 'impN' index in a group, so re-imports do not clobber files."""
    top = -1
    for case in project.cases:
        if case.group == group and case.name.startswith("imp"):
            tail = case.name[3:]
            if tail.isdigit():
                top = max(top, int(tail))
    return top + 1


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report_import(ctx, summary: ImportSummary) -> None:
    """Print a human summary of an import - always with the honesty note."""
    m = ctx.messenger
    verb = "Would import" if summary.dry_run else "Imported"
    m.success(f"{verb} {summary.created_count} case(s) into group '{summary.group}'.")

    if summary.split_files:
        m.info(
            f"Split {summary.split_files} multi-test file(s) into {summary.sub_cases} sub-case(s)."
        )
    if summary.skipped_duplicates:
        m.info(f"Skipped {summary.skipped_duplicates} byte-identical duplicate input(s).")
    if summary.skipped_empty:
        m.info(f"Skipped {summary.skipped_empty} empty input file(s).")

    # The mandatory honesty disclosure about dropped answers.
    if summary.stripped_answers:
        n = len(summary.stripped_answers)
        m.warning(
            f"Stripped {n} bundled answer file(s) - they are NOT used as expected answers.",
            hint="Answers come only from your own solution: run gen --expected.",
        )
        if summary.advisory_written:
            where = os.path.join(layout.GENERATORS_DIR, ADVISORY_DIRNAME, summary.group)
            m.info(f"Kept inert copies under {where}/ for reference only (never judged).")

    if not summary.dry_run and summary.created:
        m.info("Run gen --expected to compute answers from your solution.")
