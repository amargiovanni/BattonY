"""Top/bottom status bars — the ones that make BitchX feel like a dashboard."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from ..buffer import Buffer


class TopicBar(Static):
    """Shows the topic of the active channel (or server/query info)."""

    DEFAULT_CSS = """
    TopicBar {
        background: $primary-darken-3;
        color: $text;
        height: 1;
        padding: 0 1;
    }
    """

    def show_buffer(self, buf: "Buffer | None") -> None:
        if buf is None:
            self.update(Text(" BattonY — no buffer ", style="bold"))
            return
        from ..buffer import BufferKind

        if buf.kind == BufferKind.CHANNEL:
            chan = None
            if buf.server is not None:
                chan = buf.server.channels.get(buf.target.lower())
            topic = chan.topic if chan else ""
            t = Text()
            t.append(f" {buf.name} ", style="bold bright_cyan")
            if topic:
                from ..colors import irc_to_rich

                t.append("│ ", style="grey50")
                t.append_text(irc_to_rich(topic))
            else:
                t.append("│ no topic set", style="grey50")
            self.update(t)
        elif buf.kind == BufferKind.QUERY:
            t = Text()
            t.append(f" query: {buf.name} ", style="bold bright_magenta")
            self.update(t)
        else:
            server = buf.server
            label = f" {buf.name}"
            if server is not None and server.isupport:
                network = server.isupport.get("NETWORK", "")
                if network:
                    label += f"  ·  {network}"
            self.update(Text(label, style="bold"))


class StatusBar(Widget):
    """Bottom status line with time, current buffer, lag, activity hints."""

    DEFAULT_CSS = """
    StatusBar {
        background: $primary-darken-2;
        color: $text;
        height: 1;
    }
    StatusBar Static { height: 1; background: transparent; padding: 0 1; }
    #status-left  { width: 1fr; }
    #status-mid   { width: auto; content-align: center middle; }
    #status-right { width: auto; content-align: right middle; padding-right: 1; }
    """

    nick: reactive[str] = reactive("-")
    buffer_name: reactive[str] = reactive("·")
    server_name: reactive[str] = reactive("·")
    mode: reactive[str] = reactive("")
    lag_ms: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(id="status-left")
            yield Static(id="status-mid")
            yield Static(id="status-right")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)
        self._tick()

    def _tick(self) -> None:
        now = datetime.now().strftime("%H:%M:%S")

        left = Text()
        left.append(" [", style="grey50")
        left.append(self.nick, style="bold bright_magenta")
        left.append("] ", style="grey50")
        left.append("on ", style="grey50")
        left.append(self.server_name, style="bold bright_cyan")
        left.append(" · ", style="grey50")
        left.append(self.buffer_name, style="bold bright_green")
        if self.mode:
            left.append(" (+", style="grey50")
            left.append(self.mode, style="bold bright_yellow")
            left.append(")", style="grey50")
        self.query_one("#status-left", Static).update(left)

        mid = Text()
        mid.append("BattonY", style="bold bright_magenta")
        self.query_one("#status-mid", Static).update(mid)

        right = Text()
        right.append(now, style="bold grey82")
        self.query_one("#status-right", Static).update(right)
