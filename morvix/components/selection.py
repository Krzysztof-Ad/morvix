# Selection list / multi-select (Section 6.1).
#
# Toggle several items out of many. Bulk operations are first-class because
# choosing among thousands of tests by hand is unacceptable: all / none /
# invert / by-group / type-to-filter, and a live count.

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

from morvix import theme


def select(ctx, title, items, preselected=None):
    # No terminal to draw on: behave like the flags-only path.
    if not ctx.interactive:
        if preselected is None:
            return [value for value, _, _ in items]
        return list(preselected)
    if not items:
        return list(preselected) if preselected is not None else []
    return _SelectionUI(title, items, preselected).run()


# Holds all of the mutable state for one interactive selection and builds the
# prompt_toolkit Application around it.
class _SelectionUI:
    def __init__(self, title, items, preselected):
        self.title = title
        self.items = list(items)  # (value, label, group)
        self.values = [v for v, _, _ in self.items]

        # Start with preselected (or everything) marked.
        if preselected is None:
            self.selected = set(self.values)
        else:
            self.selected = set(preselected)
        self.original = set(self.selected)  # restored on cancel

        self.cursor = 0  # index into items
        self.filtering = False  # in type-to-filter mode?
        self.query = ""  # current filter text
        self.result = None  # values list, set on confirm

    # The indexes of the items currently visible under the filter. When not
    # filtering this is simply every item.
    def visible(self):
        if not self.query:
            return list(range(len(self.items)))
        q = self.query.lower()
        out = []
        for i, (_, label, group) in enumerate(self.items):
            if q in label.lower() or q in group.lower():
                out.append(i)
        return out

    # Render the grouped list, drawing a header each time the group changes and
    # marking the cursor row and any selected rows.
    def _render_list(self):
        lines = []
        vis = self.visible()
        last_group = None
        for idx in vis:
            value, label, group = self.items[idx]
            if group != last_group:
                lines.append(("class:group", f"  {group}\n"))
                last_group = group
            mark = "[x]" if value in self.selected else "[ ]"
            is_cursor = idx == self.cursor
            pointer = ">" if is_cursor else " "
            text = f"{pointer} {mark} {label}\n"
            lines.append(("class:cursor" if is_cursor else "", text))
        if not lines:
            lines.append(("class:muted", "  (no matches)\n"))
        return lines

    def _render_header(self):
        return [("class:heading", f"{self.title}\n")]

    # Persistent count line plus the active hint row.
    def _render_footer(self):
        count = f"{len(self.selected)} of {len(self.items)} selected"
        if self.filtering:
            hint = f"filter: {self.query}_   (Enter/Esc to leave filter)"
        else:
            hint = "Space toggle  a all  n none  i invert  g group  / filter  Enter ok  Esc cancel"
        return [
            ("class:count", f"\n{count}\n"),
            ("class:hint", hint),
        ]

    # Move the cursor by delta within the currently visible items, clamped.
    def _move(self, delta):
        vis = self.visible()
        if not vis:
            return
        if self.cursor not in vis:
            self.cursor = vis[0]
            return
        pos = vis.index(self.cursor)
        pos = max(0, min(len(vis) - 1, pos + delta))
        self.cursor = vis[pos]

    def _build_keys(self):
        kb = KeyBindings()

        # --- type-to-filter mode: most keys feed the query ---
        @kb.add("<any>", filter=_when(self, True))
        def _type(event):
            ch = event.data
            if ch and ch.isprintable():
                self.query += ch
                self._move(0)  # keep cursor on a visible row

        @kb.add("backspace", filter=_when(self, True))
        def _backspace(event):
            self.query = self.query[:-1]
            self._move(0)

        # Enter or Esc leaves filter mode, keeping the narrowed query in effect.
        @kb.add("enter", filter=_when(self, True))
        @kb.add("escape", filter=_when(self, True))
        def _leave_filter(event):
            self.filtering = False

        # --- normal mode: navigation and bulk operations ---
        @kb.add("up", filter=_when(self, False))
        def _up(event):
            self._move(-1)

        @kb.add("down", filter=_when(self, False))
        def _down(event):
            self._move(1)

        # Space toggles the item under the cursor.
        @kb.add("space", filter=_when(self, False))
        def _toggle(event):
            self._toggle_index(self.cursor)

        # a/n/i operate on the visible set so they compose with the filter.
        @kb.add("a", filter=_when(self, False))
        def _all(event):
            for idx in self.visible():
                self.selected.add(self.values[idx])

        @kb.add("n", filter=_when(self, False))
        def _none(event):
            for idx in self.visible():
                self.selected.discard(self.values[idx])

        @kb.add("i", filter=_when(self, False))
        def _invert(event):
            for idx in self.visible():
                self._toggle_index(idx)

        # g toggles the whole group the cursor sits in: if every member is
        # already selected, clear it; otherwise select it.
        @kb.add("g", filter=_when(self, False))
        def _group(event):
            group = self.items[self.cursor][2]
            members = [self.values[i] for i, (_, _, gp) in enumerate(self.items) if gp == group]
            if all(v in self.selected for v in members):
                for v in members:
                    self.selected.discard(v)
            else:
                self.selected.update(members)

        # / enters type-to-filter mode.
        @kb.add("/", filter=_when(self, False))
        def _filter(event):
            self.filtering = True

        # Enter confirms and returns the selection.
        @kb.add("enter", filter=_when(self, False))
        def _confirm(event):
            self.result = [v for v in self.values if v in self.selected]
            event.app.exit()

        # Esc / Ctrl-C cancel: restore the original (preselected) set.
        @kb.add("escape", filter=_when(self, False))
        @kb.add("c-c")
        def _cancel(event):
            self.result = [v for v in self.values if v in self.original]
            event.app.exit()

        return kb

    def _toggle_index(self, idx):
        v = self.values[idx]
        if v in self.selected:
            self.selected.discard(v)
        else:
            self.selected.add(v)

    def run(self):
        body = Window(FormattedTextControl(self._render_list))
        header = Window(FormattedTextControl(self._render_header), height=1)
        footer = Window(FormattedTextControl(self._render_footer), height=3)
        layout = Layout(HSplit([header, body, footer]))

        style = Style.from_dict(
            {
                **theme.PROMPT_TOOLKIT_STYLE,
                "group": "bold",
                "count": "bold",
                "hint": "italic",
                "muted": "italic",
            }
        )
        app = Application(
            layout=layout,
            key_bindings=self._build_keys(),
            style=style,
            full_screen=True,
            mouse_support=False,
        )
        app.run()
        # If the app somehow exits without a binding firing, fall back to the
        # original set rather than losing the user's starting point.
        if self.result is None:
            return [v for v in self.values if v in self.original]
        return self.result


# A condition that enables a binding only in (or out of) filter mode.
def _when(ui, want_filtering):
    from prompt_toolkit.filters import Condition

    return Condition(lambda: ui.filtering == want_filtering)
