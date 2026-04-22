"""BitchX-style ASCII splash screen — because an IRC client should make an entrance."""
from __future__ import annotations

import random
from datetime import datetime

from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

BANNER = r"""
 ____        _   _             __   __
| __ )  __ _| |_| |_ ___  _ __ \ \ / /
|  _ \ / _` | __| __/ _ \| '_ \ \ V /
| |_) | (_| | |_| || (_) | | | | | |
|____/ \__,_|\__|\__\___/|_| |_| |_|
"""

TAGLINES = (
    "the terminal is a cathedral — worship begins now",
    "fewer pixels, more presence",
    "IRC is not dead, it is asleep, and we are the dream",
    "glorious as a CRT in a dark room",
    "be excellent to each other, /quit gracefully",
    "60 fps of pure ASCII",
    "channels are the original timelines",
    "latency is measured in heartbeats",
)

PALETTE = (
    "bright_magenta",
    "bright_cyan",
    "bright_green",
    "bright_yellow",
    "magenta",
    "cyan",
)


def build_splash(version: str = "0.1.0") -> Panel:
    colors = random.sample(PALETTE, k=4)

    banner = Text()
    lines = [ln for ln in BANNER.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        banner.append(line + "\n", style=f"bold {colors[i % len(colors)]}")

    sub = Text()
    sub.append("BattonY ", style=f"bold {colors[0]}")
    sub.append(f"v{version}", style=f"bold {colors[1]}")
    sub.append("  —  ", style="grey50")
    sub.append(random.choice(TAGLINES), style=f"italic {colors[2]}")

    now = datetime.now().strftime("%A, %d %B %Y — %H:%M:%S")
    meta = Text(now, style="grey50", justify="center")

    tips = Text()
    tips.append("F1", style=f"bold {colors[0]}")
    tips.append(" help   ", style="grey70")
    tips.append("Ctrl-N", style=f"bold {colors[1]}")
    tips.append(" next buffer   ", style="grey70")
    tips.append("Ctrl-P", style=f"bold {colors[2]}")
    tips.append(" prev buffer   ", style="grey70")
    tips.append("/connect /join /msg /quit", style=f"bold {colors[3]}")

    body = Group(
        Align.center(banner),
        Align.center(sub),
        Text(""),
        Align.center(meta),
        Text(""),
        Align.center(tips),
    )

    return Panel(
        body,
        border_style=colors[0],
        title=f"[bold {colors[1]}]— welcome —[/]",
        subtitle=f"[{colors[3]}]type /help or /connect <server>[/]",
        padding=(1, 2),
    )
