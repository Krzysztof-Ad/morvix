# Guided form / multi-field navigable prompt (Section 6.3).
#
# For setup that asks several related questions at once (config <language>,
# runner new, init). The user moves freely: Left/Right between fields, Up/Down
# to change a choice, free text or numbers otherwise, Enter to submit, Esc to
# cancel. One implementation; every configuration screen reuses it.
#
# API (implement in Workflow B):
#   run_form(ctx, title: str, fields: list[Field]) -> dict | None
#       Returns {field.name: value}, or None if cancelled.
#       Non-interactive: returns {f.name: f.default for f in fields} with no prompt.

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class Field:
    name: str
    label: str
    kind: str = "text"          # text | int | float | choice | bool | path
    choices: Optional[List] = None   # for kind=choice: list of (value, label) or list of str
    default: Any = None
    help: str = ""
    required: bool = False


def run_form(ctx, title, fields):
    raise NotImplementedError
