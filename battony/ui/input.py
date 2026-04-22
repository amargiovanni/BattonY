"""Input widget with history and tab-completion of nicks / commands / channels."""
from __future__ import annotations

from typing import Callable

from textual import events
from textual.widgets import Input


class InputBar(Input):
    """Single-line prompt at the bottom of the screen."""

    DEFAULT_CSS = """
    InputBar {
        background: $surface;
        border: none;
        border-top: tall $primary-darken-2;
        padding: 0 1;
        height: 1;
    }
    InputBar > .input--placeholder { color: $text-muted; }
    InputBar:focus { border-top: tall $primary; }
    """

    def __init__(self, complete: Callable[[str], list[str]]) -> None:
        super().__init__(placeholder="Say something glorious… (/help for commands)", id="input")
        self._complete = complete
        self._history: list[str] = []
        self._history_index: int | None = None
        self._draft: str = ""
        self._completion_state: tuple[str, list[str], int, int] | None = None
        # (prefix_before, candidates, cursor_pos_at_prefix_end, chosen_index)

    def remember(self, line: str) -> None:
        if line and (not self._history or self._history[-1] != line):
            self._history.append(line)
        self._history_index = None
        self._draft = ""
        self._completion_state = None

    def _set_value(self, value: str, cursor: int | None = None) -> None:
        self.value = value
        self.cursor_position = cursor if cursor is not None else len(value)

    async def _on_key(self, event: events.Key) -> None:
        if event.key in {"up", "ctrl+p"} and not event.is_printable:
            if self._history:
                if self._history_index is None:
                    self._draft = self.value
                    self._history_index = len(self._history) - 1
                else:
                    self._history_index = max(0, self._history_index - 1)
                self._set_value(self._history[self._history_index])
                event.stop()
                event.prevent_default()
            return

        if event.key in {"down", "ctrl+n"} and not event.is_printable:
            if self._history_index is not None:
                self._history_index += 1
                if self._history_index >= len(self._history):
                    self._history_index = None
                    self._set_value(self._draft)
                else:
                    self._set_value(self._history[self._history_index])
                event.stop()
                event.prevent_default()
            return

        if event.key == "tab":
            self._handle_tab()
            event.stop()
            event.prevent_default()
            return

        # Any other keypress invalidates the tab cycle.
        self._completion_state = None

    def _handle_tab(self) -> None:
        value = self.value
        pos = self.cursor_position

        if self._completion_state is not None:
            prefix, candidates, cursor_at_prefix, idx = self._completion_state
            idx = (idx + 1) % len(candidates)
            chosen = candidates[idx]
            new_val = prefix + chosen + value[cursor_at_prefix:]
            self._completion_state = (prefix, candidates, cursor_at_prefix, idx)
            self._set_value(new_val, len(prefix) + len(chosen))
            return

        # Find word boundary going left.
        start = pos
        while start > 0 and value[start - 1] not in (" ", "\t"):
            start -= 1
        word = value[pos - (pos - start) : pos] if pos >= start else ""
        # Actually simpler:
        word = value[start:pos]
        if not word:
            return
        candidates = self._complete(word)
        if not candidates:
            return
        prefix_before = value[:start]
        chosen = candidates[0]
        self._completion_state = (prefix_before, candidates, pos, 0)
        new_val = prefix_before + chosen + value[pos:]
        self._set_value(new_val, len(prefix_before) + len(chosen))
