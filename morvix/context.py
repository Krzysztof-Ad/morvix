# The runtime context handed to every command.
#
# Instead of threading the console, the project, flags and so on through every
# function, we bundle them here and pass one object. A command reads ctx.project,
# prints through ctx.messenger, and checks ctx.interactive to decide whether to
# open a component or read flags.

import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

from rich.console import Console

from morvix import layout
from morvix.errors import UserError
from morvix.messages import Messenger
from morvix.project import Project, load_global_config


@dataclass
class Context:
    root: str
    console: Console
    messenger: Messenger
    interactive: bool
    project: Optional[Project] = None
    global_config: dict = field(default_factory=dict)
    debug: bool = False
    recorder: object = None          # a WorkflowRecorder while recording; else None

    @classmethod
    def create(cls, root: str, interactive: bool, console: Console, debug: bool = False) -> "Context":
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
            except Exception:
                ctx.project = None
        return ctx

    def require_project(self) -> Project:
        if self.project is None:
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
