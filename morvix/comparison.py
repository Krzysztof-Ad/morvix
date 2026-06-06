# Running the solution against its rivals, and storing/loading precomputed rival
# results (Section: rival performance comparison).
#
# A rival is an alternative implementation kept only for performance comparison
# (see morvix.project.Rival) - it never affects the tests or the expected
# answers. This module runs them and gathers the per-solution RunResults; the
# rendering of the comparison lives in morvix.results (one source, mirrored in
# the shipped runner core).
#
# Fair performance needs the same machine, so by default we run sequentially
# (parallel skews time/memory through contention) and we can precompute rival
# numbers on a reference server to ship them code-free.

import json
import os
import socket
from datetime import datetime

from morvix import layout
from morvix.adapters import detect_language
from morvix.judge import judge
from morvix.results import RunResult, to_json

# Precomputed rival results live here (and ship code-free when packaged).
RIVALS_DIR = os.path.join(layout.STATE_DIR, "rivals")


def precompute_path(root, name):
    return os.path.join(root, RIVALS_DIR, name + ".json")


def env_label():
    """A short label for where numbers were measured, for honest comparison."""
    return "%s @ %s" % (socket.gethostname(), datetime.now().isoformat(timespec="seconds"))


def _run_rival(project, rival, cases, runner=None):
    language = detect_language(rival.path) or project.language
    return judge(project, rival.path, language, cases, runner=runner)


def selected_rivals(project, runner=None):
    """Which rivals a run compares against (all of them, for now)."""
    return list(project.rivals)


def compare_live(project, solution, language, cases, rivals, runner=None, parallel=False):
    """Run the solution then each rival; return (main_run, rival_cols).

    Sequential by default for accurate numbers. Parallel runs the rivals
    concurrently (faster, but the figures become approximate).
    """
    main = judge(project, solution, language, cases, runner=runner)
    cols = []
    if parallel and rivals:
        import concurrent.futures

        runs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(rivals))) as ex:
            futs = {ex.submit(_run_rival, project, r, cases, runner): r for r in rivals}
            for fut in concurrent.futures.as_completed(futs):
                runs[futs[fut].name] = fut.result()
        for r in rivals:
            cols.append({"label": r.name, "run": runs[r.name], "precomputed": False, "env": ""})
    else:
        for r in rivals:
            cols.append(
                {
                    "label": r.name,
                    "run": _run_rival(project, r, cases, runner),
                    "precomputed": False,
                    "env": "",
                }
            )
    return main, cols


def precompute_rivals(project, cases, runner=None):
    """Run every rival on this machine and store its results (for code-free shipping)."""
    label = env_label()
    done = {}
    for rival in project.rivals:
        run = _run_rival(project, rival, cases, runner)
        data = to_json(run)
        data["env"] = label
        path = precompute_path(project.root, rival.name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        done[rival.name] = run
    return done


def load_precomputed(root, name):
    """Load a rival's precomputed results: (RunResult, env_label) or None."""
    path = precompute_path(root, name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    return RunResult.from_json(d), d.get("env", "")
