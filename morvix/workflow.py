# Workflows: record and replay (Section 18).
#
# A workflow is just a recorded list of the command strings you would type,
# stored as JSON. Because it is recorded commands, anything Morvix can do is
# automatically workflow-able with no per-feature work. Replaying re-runs the
# commands in order, optionally against a freshly imported solution.
#
# API (implement in Workflow B):
#   class WorkflowRecorder: __init__(self, name); add(self, command_line); commands -> list[str]
#   save_workflow(project, name, commands) -> str
#   load_workflow(project, name) -> list[str]
#   list_workflows(project) -> list[str]
#   run_workflow(ctx, name, on_solution=None) -> int   # replays via registry.safe_dispatch_line

import json
import os
import shlex

from morvix import layout
from morvix.errors import UserError


class WorkflowRecorder:
    def __init__(self, name):
        self.name = name
        self.commands = []

    def add(self, command_line):
        self.commands.append(command_line)


# Write a workflow JSON file under <project.root>/workflows/<name>.json.
def save_workflow(project, name, commands):
    workflows_dir = os.path.join(project.root, layout.WORKFLOWS_DIR)
    os.makedirs(workflows_dir, exist_ok=True)
    path = os.path.join(workflows_dir, f"{name}.json")
    with open(path, "w") as f:
        json.dump({"name": name, "commands": list(commands)}, f, indent=2)
    return path


# Read back the commands list; raise UserError if the file does not exist.
def load_workflow(project, name):
    path = os.path.join(project.root, layout.WORKFLOWS_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise UserError(
            f"Workflow '{name}' not found.",
            hint="Use 'workflow list' to see available workflows.",
        )
    with open(path) as f:
        data = json.load(f)
    return data["commands"]


# Return the names of all saved workflows (without the .json extension).
def list_workflows(project):
    workflows_dir = os.path.join(project.root, layout.WORKFLOWS_DIR)
    if not os.path.isdir(workflows_dir):
        return []
    return [
        os.path.splitext(fname)[0]
        for fname in sorted(os.listdir(workflows_dir))
        if fname.endswith(".json")
    ]


# Replay a saved workflow command-by-command.
# - If on_solution is given, run "import <solution>" first.
# - Run each recorded command via safe_dispatch_line.
# - Stop on the first nonzero exit code and return it; otherwise return 0.
def run_workflow(ctx, name, on_solution=None):
    from morvix import registry  # local import avoids circular deps

    commands = load_workflow(ctx.project, name)

    if on_solution is not None:
        import_line = "import " + shlex.quote(on_solution)
        ctx.messenger.info(f"Running: {import_line}")
        code = registry.safe_dispatch_line(ctx, import_line)
        if code:
            return code

    for cmd in commands:
        ctx.messenger.info(f"Running: {cmd}")
        code = registry.safe_dispatch_line(ctx, cmd)
        if code:
            return code

    return 0
