# Translate generated text into the non-stdio execution-model case shapes.
#
# Generation only ever emits a single text blob (one input per case). The args
# and file models, though, want something different: argv tokens for the args
# model, and a set of named input files (plus the names of the files the program
# will write) for the file model. This module is the small adapter that turns a
# generated blob into those shapes - and nothing more.
#
# Honesty boundary: everything here is INPUTS only. We set inputs/args and, for
# the file model, the NAMES of the output files to capture later - but never any
# expected content. The sole writer of expected answers is gen_expected, which
# runs the solution and freezes its observed output files.

import os

from morvix import layout, provenance
from morvix.cases import TestCase
from morvix.generators import _finalize_case, _write_text

# The default separator used when a generator emits several logical files in one
# blob. A line that is exactly this marker plus a name introduces the next file.
FILE_MARKER = "==="


# Split one multi-file blob into {logical name -> content} on a header marker.
#
# A blob looks like:
#     === input.txt ===
#     <content of input.txt>
#     === config.ini ===
#     <content of config.ini>
# The marker line is "<FILE_MARKER> <name> <FILE_MARKER>" (the trailing marker is
# optional). file_keys is the ordered list of names we expect; it lets us fall
# back gracefully (and assign a sole unmarked blob to the first key) so a plain
# single-file generator still works.
def split_named_files(text, file_keys):
    keys = list(file_keys)
    files = {}
    current = None
    buf = []

    def flush():
        if current is not None:
            files[current] = "\n".join(buf)

    for line in text.split("\n"):
        name = _marker_name(line)
        if name is not None:
            flush()
            current = name
            buf = []
        elif current is None:
            # Text before any marker: if exactly one key is expected, the whole
            # blob is that file; otherwise it is preamble and ignored.
            if len(keys) == 1:
                current = keys[0]
                buf = [line]
        else:
            buf.append(line)
    flush()

    # Guarantee every requested key is present (empty if the blob never named it).
    for key in keys:
        files.setdefault(key, "")
    return files


# The logical name on a marker line, or None if the line is not a marker.
def _marker_name(line):
    s = line.strip()
    if not s.startswith(FILE_MARKER):
        return None
    inner = s[len(FILE_MARKER) :].strip()
    if inner.endswith(FILE_MARKER):
        inner = inner[: -len(FILE_MARKER)].strip()
    return inner or None


# Turn generated text into a list of argv tokens.
#
# One token per non-empty line keeps tokens that themselves contain spaces; a
# single-line blob is split on whitespace instead, so both "one arg per line"
# and "all args on one line" generators do the natural thing.
def args_from_text(text):
    lines = [ln.strip() for ln in text.split("\n")]
    nonempty = [ln for ln in lines if ln]
    if len(nonempty) <= 1:
        return text.split()
    return nonempty


# Save an args-model case: argv only, no input files, no expected answer.
def write_args_case(project, group, name, argv):
    case = TestCase(
        name=name,
        group=group,
        manual=False,
        args=list(argv),
        tags=["model:args"],
        provenance=provenance.make_record("random"),
    )
    _finalize_case(project, case)
    return case


# Save a file-model case: write each named input file under tests/, and record
# the output file NAMES to capture later. Sets NO expected content - gen_expected
# runs the solution and freezes whatever it writes to those names.
def write_files_case(project, group, name, files, out_files):
    # One subdirectory per case so each file keeps its literal logical name on
    # disk; the file model copies it into the workdir under that same name.
    inputs = {}
    for logical, content in files.items():
        rel = os.path.join(layout.TESTS_DIR, group, name, logical)
        _write_text(project.abspath(rel), content)
        inputs[logical] = rel
    case = TestCase(
        name=name,
        group=group,
        manual=False,
        inputs=inputs,
        tags=["model:file"],
        provenance=provenance.make_record("random", out_files=list(out_files) or None),
    )
    _finalize_case(project, case)
    return case
