# Packaging and the package format (Section 19).
#
# Assembles a single shareable archive with everything a Receiver needs and
# nothing the Author wants kept private: tests, expected answers, the runner,
# the generated README and the manifest - but never the solution source or the
# brute-force reference.
#
# The archive is FLAT: run.sh, README.md, morvix.json, tests/, expected/ and
# runner/ all sit at the archive root, so a Receiver sees the harness directly.
# (A project hides its state under .morvix/; a package does not - it is the
# deliverable.) Case paths in the manifest are written package-relative, with
# the .morvix/ prefix stripped.
#
# API:
#   build_package(ctx, project, fmt="zip", runners=None,
#                 include_generators=False, out=None) -> str   # archive path
#   estimate_size(project) -> int   # bytes, for the large-package suggestion

import json
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile

from morvix import layout, manifest
from morvix.errors import UserError
from morvix.readme import generate_readme

# Map format names to (file extension, tarfile mode or None-for-zip)
_FORMATS = {
    "zip":    (".zip",    None),
    "tar":    (".tar",    "w"),
    "tar.gz": (".tar.gz", "w:gz"),
    "tar.xz": (".tar.xz", "w:xz"),
}


def build_package(ctx, project, fmt="zip", runners=None, include_generators=False, out=None):
    """Assemble a shareable archive of the project.

    Stages tests/, expected/, the manifest, the runner core, run.sh, and the
    README into a temp dir, then archives it. Solutions, config and brute-force
    are intentionally excluded (Section 2.3, 19.2).

    Returns the path to the created archive.
    """
    if fmt not in _FORMATS:
        raise ValueError(f"Unknown package format: {fmt!r}. Choose from: {', '.join(_FORMATS)}")

    ext, tar_mode = _FORMATS[fmt]

    # Default output path: <project.name>.<ext> in cwd
    if out is None:
        out = os.path.join(os.getcwd(), project.name + ext)

    # Validate and resolve requested runner names before touching the filesystem.
    if runners is not None:
        unknown = [n for n in runners if n not in project.runners]
        if unknown:
            available = ", ".join(sorted(project.runners)) or "(none)"
            raise UserError(
                f"Unknown runner(s): {', '.join(unknown)}. "
                f"Available: {available}."
            )

    with tempfile.TemporaryDirectory() as staging:
        _stage(project, staging, include_generators, runners)
        _archive(staging, out, fmt, tar_mode)

    return out


def estimate_size(project):
    """Sum byte sizes of tests/ and expected/ trees (used for large-package suggestions)."""
    total = 0
    for d in (layout.TESTS_DIR, layout.EXPECTED_DIR):
        tree = os.path.join(project.root, d)
        if not os.path.isdir(tree):
            continue
        for dirpath, _dirs, files in os.walk(tree):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fn))
                except OSError:
                    pass
    return total


# --- internal helpers ---

def _stage(project, staging, include_generators, runners=None):
    """Copy everything that belongs in the package into the staging dir, flat."""
    root = project.root

    # Build the manifest dict (optionally limited to selected runners), flatten
    # its case paths to package-relative, and write it at the archive root.
    if runners is not None:
        original_runners = project.runners
        project.runners = {n: v for n, v in original_runners.items() if n in runners}
        try:
            m = manifest.build_manifest(project)
        finally:
            project.runners = original_runners
    else:
        m = manifest.build_manifest(project)
    _flatten_manifest_paths(m)
    with open(os.path.join(staging, "morvix.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)
        f.write("\n")

    # - tests/ and expected/ trees, flattened to the archive root
    _copy_tree(os.path.join(root, layout.TESTS_DIR), os.path.join(staging, "tests"))
    _copy_tree(os.path.join(root, layout.EXPECTED_DIR), os.path.join(staging, "expected"))

    # - runner core -> runner/morvix_runner.py
    runner_dir = os.path.join(staging, "runner")
    os.makedirs(runner_dir, exist_ok=True)
    core_src = os.path.join(os.path.dirname(__file__), "runner_core", "morvix_runner.py")
    shutil.copy2(core_src, os.path.join(runner_dir, "morvix_runner.py"))

    # - run.sh at the archive ROOT (so ./run.sh works from the unpacked root)
    runsh_src = os.path.join(os.path.dirname(__file__), "runner_core", "run.sh")
    runsh_dst = os.path.join(staging, "run.sh")
    shutil.copy2(runsh_src, runsh_dst)
    os.chmod(runsh_dst, 0o755)

    # - generated README.md
    try:
        readme_text = generate_readme(project)
    except NotImplementedError:
        # Minimal fallback - must still carry the honesty disclaimer so a
        # Receiver is never misled into thinking test passage equals correctness.
        readme_text = (
            f"# {project.name}\n\n"
            "Note: passing all tests does not prove correctness.\n"
        )
    with open(os.path.join(staging, layout.README), "w", encoding="utf-8") as f:
        f.write(readme_text)

    # - generators/ only if requested
    if include_generators:
        gen_src = os.path.join(root, layout.GENERATORS_DIR)
        if os.path.isdir(gen_src):
            _copy_tree(gen_src, os.path.join(staging, "generators"))


def _flatten_manifest_paths(m):
    """Strip the .morvix/ prefix from case paths so they resolve in a flat package."""
    prefixes = (layout.STATE_DIR + os.sep, layout.STATE_DIR + "/")

    def strip(p):
        for pre in prefixes:
            if p.startswith(pre):
                return p[len(pre):]
        return p

    for c in m.get("cases", []):
        if c.get("inputs"):
            c["inputs"] = {k: strip(v) for k, v in c["inputs"].items()}
        if c.get("expected_output"):
            c["expected_output"] = strip(c["expected_output"])
        if c.get("expected_files"):
            c["expected_files"] = {k: strip(v) for k, v in c["expected_files"].items()}


def _copy_tree(src, dst):
    """Copy a directory tree if the source exists; silently skip missing dirs."""
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)


def _archive(staging, out, fmt, tar_mode):
    """Write the staging directory into the output archive."""
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    if fmt == "zip":
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _dirs, files in os.walk(staging):
                for fn in files:
                    abs_path = os.path.join(dirpath, fn)
                    arcname = os.path.relpath(abs_path, staging)
                    zf.write(abs_path, arcname)
    else:
        with tarfile.open(out, tar_mode) as tf:
            tf.add(staging, arcname=".")
