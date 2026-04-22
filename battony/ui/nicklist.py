"""Right-side list of users in the current channel."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ..colors import nick_color

if TYPE_CHECKING:
    from ..irc.client import Channel


_PREFIX_STYLE = {
    "~": "bold bright_red",       # owner
    "&": "bold bright_magenta",   # admin
    "@": "bold bright_green",     # op
    "%": "bold bright_yellow",    # halfop
    "+": "bold bright_cyan",      # voice
    "":  "",
}


class NickList(OptionList):
    DEFAULT_CSS = """
    NickList {
        background: $panel;
        width: 22;
        border-left: tall $primary-darken-2;
        padding: 0 1;
    }
    NickList > .option-list--option-highlighted {
        background: $primary 30%;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="nicklist")

    def show_channel(self, channel: "Channel | None") -> None:
        self.clear_options()
        if channel is None:
            return
        items: list[Option] = []
        for nick, prefix in channel.sorted_members():
            p = prefix[:1] if prefix else ""
            text = Text()
            if p:
                text.append(p, style=_PREFIX_STYLE.get(p, ""))
            text.append(nick, style=nick_color(nick))
            items.append(Option(text, id=nick))
        self.add_options(items)
        self.border_title = f"[{len(channel.members)}]"
