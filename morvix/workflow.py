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


class WorkflowRecorder:
    def __init__(self, name):
        self.name = name
        self.commands = []

    def add(self, command_line):
        self.commands.append(command_line)


def save_workflow(project, name, commands):
    raise NotImplementedError


def load_workflow(project, name):
    raise NotImplementedError


def list_workflows(project):
    raise NotImplementedError


def run_workflow(ctx, name, on_solution=None):
    raise NotImplementedError
