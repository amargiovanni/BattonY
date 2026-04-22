"""The main chat log viewer."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import RichLog

from ..buffer import Line

if TYPE_CHECKING:
    from ..buffer import Buffer


TIMESTAMP_STYLE = "grey42"


def _format_line(line: Line, show_ts: bool = True) -> RenderableType:
    text = Text()
    if show_ts:
        text.append(line.ts.strftime("%H:%M "), style=TIMESTAMP_STYLE)
    text.append_text(line.text)
    return text


class ChatView(RichLog):
    """RichLog-backed scrollable chat view, re-rendered when the active buffer changes."""

    DEFAULT_CSS = """
    ChatView {
        background: $surface;
        scrollbar-background: $surface;
        scrollbar-color: $primary;
        scrollbar-color-hover: $primary-lighten-1;
        padding: 0 1;
    }
    """

    show_timestamps: reactive[bool] = reactive(True)

    def __init__(self) -> None:
        super().__init__(highlight=False, markup=False, wrap=True, auto_scroll=True)
        self._buffer: Buffer | None = None

    def show_buffer(self, buf: "Buffer | None") -> None:
        self._buffer = buf
        self.clear()
        if buf is None:
            return
        for line in buf.lines:
            self.write(_format_line(line, self.show_timestamps))
        buf.mark_read()

    def append_line(self, line: Line) -> None:
        self.write(_format_line(line, self.show_timestamps))

    def append_renderable(self, renderable: RenderableType) -> None:
        self.write(renderable)
