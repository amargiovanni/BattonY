"""mIRC color codes, nick coloring, URL detection — everything that makes IRC pretty."""
from __future__ import annotations

import hashlib
import re

from rich.text import Text

# mIRC color palette (0-15) approximated with ANSI-friendly names Rich understands.
MIRC_COLORS: dict[int, str] = {
    0: "white",
    1: "black",
    2: "blue",
    3: "green",
    4: "red",
    5: "dark_red",
    6: "magenta",
    7: "orange3",
    8: "yellow",
    9: "bright_green",
    10: "cyan",
    11: "bright_cyan",
    12: "bright_blue",
    13: "bright_magenta",
    14: "grey50",
    15: "grey70",
}

# Nick color palette — picked to look great on a dark terminal, avoiding
# hard-to-read or stop-sign reds.
NICK_PALETTE: tuple[str, ...] = (
    "bright_cyan",
    "bright_magenta",
    "bright_green",
    "bright_yellow",
    "cyan",
    "magenta",
    "green",
    "orange3",
    "spring_green2",
    "deep_pink3",
    "dark_orange",
    "medium_purple",
    "sky_blue1",
    "light_coral",
    "pale_turquoise1",
    "plum2",
)

# IRC formatting control codes.
C_COLOR = "\x03"
C_BOLD = "\x02"
C_ITALIC = "\x1d"
C_UNDERLINE = "\x1f"
C_REVERSE = "\x16"
C_RESET = "\x0f"
C_MONO = "\x11"
C_STRIKE = "\x1e"

_COLOR_RE = re.compile(r"\x03(\d{1,2})?(?:,(\d{1,2}))?")
_URL_RE = re.compile(r"""(https?://[^\s<>"'`()\[\]{}]+)""")


def nick_color(nick: str) -> str:
    """Deterministic color for a nick — same nick → same color every run."""
    if not nick:
        return "white"
    digest = hashlib.sha1(nick.lower().encode("utf-8")).digest()
    idx = digest[0] % len(NICK_PALETTE)
    return NICK_PALETTE[idx]


def strip_formatting(text: str) -> str:
    """Remove all IRC formatting codes, leaving plain text."""
    text = _COLOR_RE.sub("", text)
    for ch in (C_BOLD, C_ITALIC, C_UNDERLINE, C_REVERSE, C_RESET, C_MONO, C_STRIKE):
        text = text.replace(ch, "")
    return text


def irc_to_rich(text: str) -> Text:
    """Convert an IRC message with mIRC/control codes into a Rich Text instance."""
    out = Text()
    fg: str | None = None
    bg: str | None = None
    bold = italic = underline = reverse = strike = False

    def current_style() -> str:
        parts: list[str] = []
        if bold:
            parts.append("bold")
        if italic:
            parts.append("italic")
        if underline:
            parts.append("underline")
        if strike:
            parts.append("strike")
        effective_fg = fg
        effective_bg = bg
        if reverse:
            effective_fg, effective_bg = bg or "black", fg or "white"
        if effective_fg:
            parts.append(effective_fg)
        if effective_bg:
            parts.append(f"on {effective_bg}")
        return " ".join(parts)

    i = 0
    buf: list[str] = []

    def flush() -> None:
        if buf:
            out.append("".join(buf), style=current_style() or None)
            buf.clear()

    while i < len(text):
        ch = text[i]
        if ch == C_COLOR:
            flush()
            match = _COLOR_RE.match(text, i)
            if match and (match.group(1) or match.group(2)):
                fg_num = match.group(1)
                bg_num = match.group(2)
                if fg_num is not None:
                    fg = MIRC_COLORS.get(int(fg_num) % 16, "white")
                if bg_num is not None:
                    bg = MIRC_COLORS.get(int(bg_num) % 16, "black")
                i = match.end()
            else:
                fg = None
                bg = None
                i += 1
            continue
        if ch == C_BOLD:
            flush()
            bold = not bold
            i += 1
            continue
        if ch == C_ITALIC:
            flush()
            italic = not italic
            i += 1
            continue
        if ch == C_UNDERLINE:
            flush()
            underline = not underline
            i += 1
            continue
        if ch == C_REVERSE:
            flush()
            reverse = not reverse
            i += 1
            continue
        if ch == C_STRIKE:
            flush()
            strike = not strike
            i += 1
            continue
        if ch == C_RESET:
            flush()
            fg = bg = None
            bold = italic = underline = reverse = strike = False
            i += 1
            continue
        if ch == C_MONO:
            flush()
            i += 1
            continue
        if ch == "\x01":  # CTCP marker — let the caller handle it.
            i += 1
            continue
        buf.append(ch)
        i += 1

    flush()
    return out


def highlight_urls(text: Text, style: str = "underline cyan") -> Text:
    """In-place-style: underline URLs inside a Rich Text."""
    plain = text.plain
    for m in _URL_RE.finditer(plain):
        text.stylize(style, m.start(), m.end())
    return text


def styled_nick(nick: str, prefix: str = "") -> Text:
    """Render a nick with its deterministic color and optional prefix (@+%)."""
    t = Text()
    if prefix:
        t.append(prefix, style="bold orange3")
    t.append(nick, style=f"bold {nick_color(nick)}")
    return t
