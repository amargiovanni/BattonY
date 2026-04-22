"""Modal help screen."""
from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static


class HelpScreen(ModalScreen[None]):
    BINDINGS = [("escape", "dismiss", "close"), ("f1", "dismiss", "close"), ("q", "dismiss", "close")]

    def __init__(self, commands: list[tuple[str, str]]) -> None:
        super().__init__()
        self._commands = commands

    def compose(self) -> ComposeResult:
        table = Table(box=None, show_header=True, header_style="bold bright_magenta", padding=(0, 1))
        table.add_column("command", style="bold bright_cyan", no_wrap=True)
        table.add_column("what it does", style="grey82")
        for name, text in self._commands:
            table.add_row(f"/{name}", text)

        keys = Table(box=None, show_header=True, header_style="bold bright_magenta", padding=(0, 1))
        keys.add_column("key", style="bold bright_yellow", no_wrap=True)
        keys.add_column("action", style="grey82")
        for key, desc in (
            ("F1", "toggle this help"),
            ("Ctrl+N / Ctrl+P", "next / previous buffer"),
            ("Ctrl+L", "clear current buffer"),
            ("Ctrl+W", "close current buffer"),
            ("Ctrl+Q", "quit"),
            ("Tab", "complete nick / command / channel"),
            ("↑ / ↓", "input history"),
            ("PgUp / PgDn", "scroll chat"),
        ):
            keys.add_row(key, desc)

        body = Group(
            Text("BattonY — keybindings", style="bold bright_magenta"),
            keys,
            Text(""),
            Text("slash commands", style="bold bright_magenta"),
            table,
            Text(""),
            Text("press Esc or q to close", style="italic grey58"),
        )

        yield Container(
            Static(Panel(body, border_style="bright_magenta", padding=(1, 2))),
            id="help-panel",
        )

    def action_dismiss(self, *_: object) -> None:
        self.app.pop_screen()
