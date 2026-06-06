# workflow command: record, replay and manage workflows (Section 18).
#
# A workflow captures a sequence of commands and replays them on demand,
# optionally against a fresh solution. Actions:
#   record [name]  - start capturing subsequent commands
#   stop           - stop recording and save to disk
#   run NAME       - replay a saved workflow (--on SOL to import first)
#   list           - show saved workflow names
#   show NAME      - print the commands in a saved workflow
#   edit NAME      - print the path so the user can hand-edit the JSON

import os

from morvix import workflow as wf
from morvix.errors import UserError

NAME = "workflow"

ACTIONS = ["record", "stop", "run", "list", "show", "edit"]


def configure(parser):
    parser.add_argument(
        "action",
        choices=ACTIONS,
        help="record | stop | run | list | show | edit",
    )
    parser.add_argument(
        "name",
        nargs="?",
        help="workflow name (required for run, show, edit; optional for record)",
    )
    parser.add_argument(
        "--on",
        metavar="SOLUTION",
        help="with run: import this solution before replaying",
    )


def run(ctx, args) -> int:
    project = ctx.require_project()
    action = args.action
    name = args.name

    if action == "record":
        return _record(ctx, name)
    if action == "stop":
        return _stop(ctx, project)
    if action == "run":
        return _run(ctx, project, name, args.on)
    if action == "list":
        return _list(ctx, project)
    if action == "show":
        return _show(ctx, project, name)
    if action == "edit":
        return _edit(ctx, project, name)

    raise UserError(f"Unknown action '{action}'.", hint="Use one of: " + ", ".join(ACTIONS))


# --- action handlers ---


def _record(ctx, name):
    wf_name = name or "workflow"
    ctx.recorder = wf.WorkflowRecorder(wf_name)
    ctx.messenger.success(f"Recording workflow '{wf_name}'.")
    ctx.messenger.info("Subsequent commands are captured. Run 'workflow stop' to save.")
    return 0


def _stop(ctx, project):
    if ctx.recorder is None:
        ctx.messenger.info("Nothing is being recorded.")
        return 0
    recorder = ctx.recorder
    path = wf.save_workflow(project, recorder.name, recorder.commands)
    count = len(recorder.commands)
    ctx.recorder = None
    ctx.messenger.success(
        f"Saved workflow '{recorder.name}' ({count} command{'s' if count != 1 else ''})."
    )
    ctx.messenger.info(f"Saved to: {path}")
    return 0


def _run(ctx, project, name, on_solution):
    if not name:
        raise UserError("workflow run needs a name.", hint="Try:  workflow run <name>")
    return wf.run_workflow(ctx, name, on_solution=on_solution)


def _list(ctx, project):
    names = wf.list_workflows(project)
    if not names:
        ctx.messenger.info("No workflows saved yet.")
        ctx.messenger.plain("Start recording with:  workflow record [name]")
        return 0
    ctx.messenger.heading("Saved workflows")
    for n in names:
        ctx.messenger.plain(f"  {n}")
    return 0


def _show(ctx, project, name):
    if not name:
        raise UserError("workflow show needs a name.", hint="Try:  workflow show <name>")
    commands = wf.load_workflow(project, name)
    ctx.messenger.heading(f"Workflow '{name}'")
    for i, cmd in enumerate(commands, 1):
        ctx.messenger.plain(f"  {i:3}.  {cmd}")
    return 0


def _edit(ctx, project, name):
    if not name:
        raise UserError("workflow edit needs a name.", hint="Try:  workflow edit <name>")
    # Check it exists first so the user gets a friendly error.
    wf.load_workflow(project, name)
    path = os.path.join(project.root, "workflows", f"{name}.json")
    ctx.messenger.plain(f"{path}")
    return 0


# --- autocomplete ---


def complete(ctx, prev_words, word):
    # - first meaningful token after "workflow": suggest actions
    # - second token (after an action that takes a name): suggest workflow names
    stripped = [w for w in prev_words if w != "workflow"]
    names = wf.list_workflows(ctx.project) if ctx.project else []

    if not stripped:
        out = [(a, "action") for a in ACTIONS if a.startswith(word or "")]
        out += [(n, "workflow") for n in names if n.startswith(word or "")]
        return out

    action = stripped[0]
    if action in ("run", "show", "edit", "record"):
        return [(n, "workflow") for n in names if n.startswith(word or "")]
    return []
