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

from morvix.theme import GLYPHS, PROMPT_TOOLKIT_STYLE


@dataclass
class Field:
    name: str
    label: str
    kind: str = "text"          # text | int | float | choice | bool | path
    choices: Optional[List] = None   # for kind=choice: list of (value, label) or list of str
    default: Any = None
    help: str = ""
    required: bool = False


# A choice's options may be plain strings or (value, label) pairs; normalise to
# pairs so the rest of the code can treat them uniformly.
def _normalize_choices(choices):
    pairs = []
    for c in choices or []:
        if isinstance(c, (tuple, list)):
            pairs.append((c[0], str(c[1])))
        else:
            pairs.append((c, str(c)))
    return pairs


# Per-field editable state for the running form. Choice/bool track an index or
# flag; the typed kinds keep their text in a prompt_toolkit Buffer.
class _FieldState:
    def __init__(self, field):
        from prompt_toolkit.buffer import Buffer

        self.field = field
        self.choices = _normalize_choices(field.choices) if field.kind == "choice" else []
        self.index = 0          # selected option for kind=choice
        self.bool_value = False  # current value for kind=bool
        self.buffer = None       # Buffer for text/int/float/path
        self._init_from_default(Buffer)

    def _init_from_default(self, Buffer):
        f = self.field
        if f.kind == "choice":
            for i, (value, _) in enumerate(self.choices):
                if value == f.default:
                    self.index = i
                    break
        elif f.kind == "bool":
            self.bool_value = bool(f.default)
        else:
            text = "" if f.default is None else str(f.default)
            self.buffer = Buffer(document=_document(text))

    # The raw value as it stands now, before validation/parsing.
    def raw_value(self):
        f = self.field
        if f.kind == "choice":
            return self.choices[self.index][0] if self.choices else None
        if f.kind == "bool":
            return self.bool_value
        return self.buffer.text


def _document(text):
    from prompt_toolkit.document import Document

    return Document(text, cursor_position=len(text))


# Turn a field's current raw value into its final typed value, or raise
# ValueError with a human message. Empty required fields and bad numbers fail.
def _parse_value(field, raw):
    if field.kind in ("int", "float", "text", "path"):
        text = (raw or "").strip()
        if not text:
            if field.required:
                raise ValueError("required")
            return field.default if field.kind in ("int", "float") else text
        if field.kind == "int":
            try:
                return int(text)
            except ValueError:
                raise ValueError("not a whole number")
        if field.kind == "float":
            try:
                return float(text)
            except ValueError:
                raise ValueError("not a number")
        return text
    if field.kind == "choice":
        if raw is None and field.required:
            raise ValueError("required")
        return raw
    if field.kind == "bool":
        return bool(raw)
    return raw


def run_form(ctx, title, fields):
    # Non-interactive: no terminal to drive, so hand back the defaults as-is.
    if not ctx.interactive:
        return {f.name: f.default for f in fields}
    return _interactive_form(ctx, title, fields)


def _interactive_form(ctx, title, fields):
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    states = [_FieldState(f) for f in fields]
    active = {"row": 0}        # which field is highlighted
    error = {"text": ""}       # inline validation error, shown under the form

    # Move the highlight, wrapping around the ends.
    def move(delta):
        error["text"] = ""
        active["row"] = (active["row"] + delta) % len(states)

    # Render the whole form: every field on its own line, the active one marked,
    # plus the active field's help and any validation error.
    def render():
        lines = [("class:prompt", f"{title}\n\n")]
        for i, st in enumerate(states):
            current = i == active["row"]
            marker = GLYPHS["prompt"] if current else " "
            label_style = "class:selected" if current else ""
            lines.append((label_style, f"{marker} {st.field.label}: "))
            lines.extend(_render_value(st, current))
            lines.append(("", "\n"))
        help_text = states[active["row"]].field.help
        if help_text:
            lines.append(("class:muted", f"\n  {help_text}\n"))
        if error["text"]:
            lines.append(("class:error", f"\n{GLYPHS['error']} {error['text']}\n"))
        lines.append(("class:muted", "\n  Up/Down move • Left/Right or Space change • Enter submit • Esc cancel\n"))
        return lines

    # The value cell for one field; choice shows arrows, bool a checkbox, typed
    # fields show their buffer text with a cursor when active.
    def _render_value(st, current):
        f = st.field
        if f.kind == "choice":
            label = st.choices[st.index][1] if st.choices else "(no choices)"
            return [("class:accent" if current else "", f"< {label} >")]
        if f.kind == "bool":
            box = "[x]" if st.bool_value else "[ ]"
            return [("class:accent" if current else "", box)]
        text = st.buffer.text
        if current:
            return [("class:cursor", text + " ")]
        return [("", text or "(empty)")]

    control = FormattedTextControl(render, focusable=True)
    body = Window(control, wrap_lines=True)
    layout = Layout(HSplit([body]))

    kb = KeyBindings()

    # Up/Down and Tab/Shift-Tab move between fields.
    @kb.add("up")
    @kb.add("s-tab")
    def _(event):
        move(-1)

    @kb.add("down")
    @kb.add("tab")
    def _(event):
        move(1)

    # Left/Right cycle a choice field's options.
    @kb.add("left")
    def _(event):
        st = states[active["row"]]
        if st.field.kind == "choice" and st.choices:
            error["text"] = ""
            st.index = (st.index - 1) % len(st.choices)

    @kb.add("right")
    def _(event):
        st = states[active["row"]]
        if st.field.kind == "choice" and st.choices:
            error["text"] = ""
            st.index = (st.index + 1) % len(st.choices)

    # Space toggles a bool; for choice it also advances (a handy alternative).
    @kb.add("space")
    def _(event):
        st = states[active["row"]]
        if st.field.kind == "bool":
            error["text"] = ""
            st.bool_value = not st.bool_value
        elif st.field.kind == "choice" and st.choices:
            error["text"] = ""
            st.index = (st.index + 1) % len(st.choices)
        else:
            st.buffer.insert_text(" ")

    # Typing edits the active text/int/float/path field; backspace and the
    # in-buffer arrows are handled here so editing feels normal.
    @kb.add("backspace")
    def _(event):
        st = states[active["row"]]
        if st.field.kind not in ("choice", "bool"):
            error["text"] = ""
            st.buffer.delete_before_cursor()

    @kb.add("<any>")
    def _(event):
        st = states[active["row"]]
        if st.field.kind not in ("choice", "bool"):
            text = event.data
            if text and text.isprintable():
                error["text"] = ""
                st.buffer.insert_text(text)

    # Enter validates every field and submits; the first bad field is selected
    # and its error shown, blocking the submit until it is fixed.
    @kb.add("enter")
    def _(event):
        result = {}
        for i, st in enumerate(states):
            try:
                result[st.field.name] = _parse_value(st.field, st.raw_value())
            except ValueError as exc:
                active["row"] = i
                error["text"] = f"{st.field.label}: {exc}"
                return
        event.app.exit(result=result)

    # Esc cancels the whole form.
    @kb.add("escape", eager=True)
    def _(event):
        event.app.exit(result=None)

    style = Style.from_dict(PROMPT_TOOLKIT_STYLE)
    app = Application(layout=layout, key_bindings=kb, style=style, full_screen=True)
    return app.run()
