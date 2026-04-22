"""IRC message parsing and formatting (RFC 1459/2812 + IRCv3 message tags)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class Prefix:
    """The sender of an IRC message: nick!user@host or a server name."""

    raw: str
    nick: str = ""
    user: str = ""
    host: str = ""

    @property
    def is_server(self) -> bool:
        return "!" not in self.raw and "@" not in self.raw and "." in self.raw

    @classmethod
    def parse(cls, raw: str) -> "Prefix":
        nick = user = host = ""
        rest = raw
        if "@" in rest:
            rest, host = rest.split("@", 1)
        if "!" in rest:
            nick, user = rest.split("!", 1)
        else:
            nick = rest
        return cls(raw=raw, nick=nick, user=user, host=host)

    def __str__(self) -> str:
        return self.nick or self.raw


@dataclass
class Message:
    """A parsed IRC message."""

    raw: str = ""
    tags: dict[str, str] = field(default_factory=dict)
    prefix: Prefix | None = None
    command: str = ""
    params: list[str] = field(default_factory=list)

    @property
    def trailing(self) -> str:
        """Last parameter — usually the actual message text."""
        return self.params[-1] if self.params else ""

    @property
    def source(self) -> str:
        return self.prefix.nick if self.prefix else ""

    def param(self, index: int, default: str = "") -> str:
        return self.params[index] if index < len(self.params) else default

    @classmethod
    def parse(cls, line: str) -> "Message":
        raw = line
        line = line.rstrip("\r\n")

        tags: dict[str, str] = {}
        prefix: Prefix | None = None

        # IRCv3 message tags: @key=value;key2=value2
        if line.startswith("@"):
            tag_section, _, line = line.partition(" ")
            for tag in tag_section[1:].split(";"):
                if not tag:
                    continue
                k, _, v = tag.partition("=")
                tags[k] = _unescape_tag(v)

        # Prefix: :nick!user@host
        if line.startswith(":"):
            prefix_section, _, line = line.partition(" ")
            prefix = Prefix.parse(prefix_section[1:])

        # Command + params (trailing starts with :)
        params: list[str] = []
        command = ""
        if " :" in line:
            head, _, trailing = line.partition(" :")
            parts = head.split(" ")
            command = parts[0].upper()
            params = [p for p in parts[1:] if p] + [trailing]
        else:
            parts = line.split(" ")
            if parts:
                command = parts[0].upper()
                params = [p for p in parts[1:] if p]

        return cls(raw=raw, tags=tags, prefix=prefix, command=command, params=params)


_TAG_ESCAPES = {
    "\\:": ";",
    "\\s": " ",
    "\\\\": "\\",
    "\\r": "\r",
    "\\n": "\n",
}


def _unescape_tag(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            pair = value[i : i + 2]
            out.append(_TAG_ESCAPES.get(pair, value[i + 1]))
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def format_message(command: str, *params: str, trailing: str | None = None) -> str:
    """Build an IRC wire-format message (without CRLF)."""
    parts: list[str] = [command]
    for p in params:
        if " " in p or p.startswith(":"):
            raise ValueError(f"middle param cannot contain space or start with ':': {p!r}")
        parts.append(p)
    line = " ".join(parts)
    if trailing is not None:
        line += " :" + trailing
    return line


def split_message_text(text: str, max_len: int = 400) -> Iterable[str]:
    """Split long PRIVMSG/NOTICE text on word boundaries to fit IRC 512-byte limit."""
    if len(text) <= max_len:
        yield text
        return
    while text:
        if len(text) <= max_len:
            yield text
            return
        cut = text.rfind(" ", 0, max_len)
        if cut <= 0:
            cut = max_len
        yield text[:cut]
        text = text[cut:].lstrip()
