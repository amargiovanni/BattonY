"""Buffers — one per status window / channel / query / server."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from rich.text import Text

from .colors import highlight_urls, irc_to_rich, nick_color, styled_nick

if TYPE_CHECKING:
    from .irc.client import IRCClient


class BufferKind(Enum):
    STATUS = "status"    # per-server status/MOTD/server notices
    CHANNEL = "channel"  # #channel
    QUERY = "query"      # private message with one user


class Activity(Enum):
    NONE = 0
    EVENT = 1    # joins/parts/mode changes
    MESSAGE = 2  # regular chatter
    HIGHLIGHT = 3  # your nick was mentioned


@dataclass
class Line:
    ts: datetime
    text: Text
    kind: str = "msg"  # msg / action / event / error / info / self
    highlight: bool = False


@dataclass
class Buffer:
    name: str
    kind: BufferKind
    server: "IRCClient | None" = None
    target: str = ""       # channel name or nick — empty for STATUS
    lines: list[Line] = field(default_factory=list)
    activity: Activity = Activity.NONE
    unread: int = 0
    scroll_offset: int = 0  # 0 = pinned to bottom

    @property
    def title(self) -> str:
        return self.name

    def mark_read(self) -> None:
        self.activity = Activity.NONE
        self.unread = 0

    def bump(self, activity: Activity) -> None:
        if activity.value > self.activity.value:
            self.activity = activity
        self.unread += 1

    # ------------------------------------------------------ line builders

    def add_info(self, text: str | Text, *, style: str = "grey70 italic") -> None:
        t = text if isinstance(text, Text) else Text(text, style=style)
        self.lines.append(Line(ts=datetime.now(), text=t, kind="info"))

    def add_error(self, text: str) -> None:
        self.lines.append(
            Line(ts=datetime.now(), text=Text(text, style="bold red"), kind="error")
        )
        self.bump(Activity.HIGHLIGHT)

    def add_event(self, text: str | Text) -> None:
        t = text if isinstance(text, Text) else Text(text, style="grey58 italic")
        self.lines.append(Line(ts=datetime.now(), text=t, kind="event"))
        self.bump(Activity.EVENT)

    def add_raw(self, text: str) -> None:
        self.lines.append(
            Line(ts=datetime.now(), text=Text(text, style="grey50"), kind="info")
        )

    def add_message(
        self,
        nick: str,
        text: str,
        *,
        is_self: bool = False,
        is_action: bool = False,
        prefix: str = "",
        highlight_words: list[str] | None = None,
    ) -> None:
        body = irc_to_rich(text)
        highlight_urls(body)

        highlighted = False
        if highlight_words:
            plain = body.plain.lower()
            for word in highlight_words:
                if word and word.lower() in plain:
                    highlighted = True
                    break

        line = Text()
        if is_action:
            line.append("* ", style="bold orange3")
            line.append_text(styled_nick(nick, prefix))
            line.append(" ")
            line.append_text(body)
        else:
            line.append("<", style="grey50")
            line.append_text(styled_nick(nick, prefix))
            line.append("> ", style="grey50")
            if is_self:
                body.stylize("dim")
            line.append_text(body)
            if highlighted:
                line.stylize("on grey19")

        kind = "action" if is_action else ("self" if is_self else "msg")
        self.lines.append(
            Line(ts=datetime.now(), text=line, kind=kind, highlight=highlighted)
        )
        if is_self:
            return  # don't bump activity on our own messages
        self.bump(Activity.HIGHLIGHT if highlighted else Activity.MESSAGE)

    def add_notice(self, nick: str, text: str) -> None:
        body = irc_to_rich(text)
        highlight_urls(body)
        line = Text()
        line.append("-", style="grey50")
        line.append(nick, style=f"bold {nick_color(nick)}")
        line.append("- ", style="grey50")
        line.append_text(body)
        self.lines.append(Line(ts=datetime.now(), text=line, kind="notice"))
        self.bump(Activity.MESSAGE)
