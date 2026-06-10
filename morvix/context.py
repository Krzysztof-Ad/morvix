# The runtime context handed to every command.
#
# Instead of threading the console, the project, flags and so on through every
# function, we bundle them here and pass one object. A command reads ctx.project,
# prints through ctx.messenger, and checks ctx.interactive to decide whether to
# open a component or read flags.

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from rich.console import Console

from morvix import layout
from morvix.errors import UserError
from morvix.messages import Messenger
from morvix.project import Project, load_global_config

if TYPE_CHECKING:
    from morvix.workflow import WorkflowRecorder


@dataclass
class Context:
    root: str
    console: Console
    messenger: Messenger
    interactive: bool
    project: Optional[Project] = None
    project_error: Optional[str] = None  # why a present-but-broken project failed to load
    global_config: dict = field(default_factory=dict)
    debug: bool = False
    recorder: Optional["WorkflowRecorder"] = None  # set while a workflow is recording
    should_exit: bool = False  # set by the exit command; the shell loop checks it
    last_result: object = None  # the most recent RunResult, for the result command

    @classmethod
    def create(
        cls, root: str, interactive: bool, console: Console, debug: bool = False
    ) -> "Context":
        ctx = cls(
            root=root,
            console=console,
            messenger=Messenger(console),
            interactive=interactive,
            global_config=load_global_config(),
            debug=debug,
        )
        if layout.is_project(root):
            try:
                ctx.project = Project.load(root)
            except Exception as exc:
                # A project IS here but would not load (corrupt JSON, bad
                # permissions, ...). Saying "no project, run init" would
                # mislead - and init could pave over a recoverable state - so
                # remember the real cause and surface it.
                ctx.project = None
                ctx.project_error = f"{type(exc).__name__}: {exc}"
                ctx.messenger.warning(
                    f"A Morvix project is here but failed to load ({ctx.project_error}).",
                    hint="The state under .morvix/config/ is plain JSON - fix or restore it.",
                )
        return ctx

    def require_project(self) -> Project:
        if self.project is None:
            if self.project_error:
                raise UserError(
                    f"The Morvix project here failed to load: {self.project_error}",
                    hint="The state under .morvix/config/ is plain JSON - fix or restore it.",
                )
            raise UserError(
                "No Morvix project here.",
                hint="Run 'init' to create one in this directory.",
            )
        return self.project

    def reload_project(self) -> None:
        if layout.is_project(self.root):
            self.project = Project.load(self.root)

    def save_project(self) -> None:
        """Persist config + regenerate the manifest so the directory stays in sync."""
        if self.project is None:
            return
        self.project.save()
        from morvix.manifest import write_manifest

        write_manifest(self.project)

    def record(self, command: str) -> None:
        """If a workflow is recording, capture this command line."""
        if self.recorder is not None:
            self.recorder.add(command)
