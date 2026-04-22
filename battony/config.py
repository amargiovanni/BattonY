"""TOML-based configuration for BattonY."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_config_dir

from .irc.client import ServerConfig

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


CONFIG_DIR = Path(user_config_dir("battony"))
CONFIG_PATH = CONFIG_DIR / "config.toml"
LOG_DIR = CONFIG_DIR / "logs"

DEFAULT_CONFIG = """\
# ~ BattonY configuration ~
# Your terminal, your IRC, your vibe.

[user]
nick = "battony"
user = "battony"
realname = "BattonY — glorious IRC"

# Words that will light up messages when they appear.
highlights = ["battony"]

[[servers]]
name = "libera"
host = "irc.libera.chat"
port = 6697
tls = true
autojoin = ["#battony"]
# sasl_user = "yournick"
# sasl_pass = "yourpass"

# [[servers]]
# name = "oftc"
# host = "irc.oftc.net"
# port = 6697
# tls = true
# autojoin = []
"""


@dataclass
class UserConfig:
    nick: str = "battony"
    user: str = "battony"
    realname: str = "BattonY IRC"
    highlights: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    user: UserConfig = field(default_factory=UserConfig)
    servers: list[ServerConfig] = field(default_factory=list)


def ensure_config() -> Path:
    """Create default config file on first run."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        # The config may hold SASL passwords — restrict to the current user.
        CONFIG_PATH.touch(mode=0o600)
        CONFIG_PATH.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return CONFIG_PATH


def load_config(path: Path | None = None) -> AppConfig:
    path = path or ensure_config()
    with path.open("rb") as fp:
        data = tomllib.load(fp)

    user_data = data.get("user", {})
    user = UserConfig(
        nick=user_data.get("nick", "battony"),
        user=user_data.get("user", user_data.get("nick", "battony")),
        realname=user_data.get("realname", "BattonY IRC"),
        highlights=list(user_data.get("highlights", [])),
    )

    servers: list[ServerConfig] = []
    for s in data.get("servers", []):
        servers.append(
            ServerConfig(
                name=s.get("name", s.get("host", "server")),
                host=s["host"],
                port=int(s.get("port", 6697)),
                tls=bool(s.get("tls", True)),
                nick=s.get("nick", user.nick),
                user=s.get("user", user.user),
                realname=s.get("realname", user.realname),
                password=s.get("password"),
                sasl_user=s.get("sasl_user"),
                sasl_pass=s.get("sasl_pass"),
                autojoin=list(s.get("autojoin", [])),
                reconnect=bool(s.get("reconnect", True)),
            )
        )

    return AppConfig(user=user, servers=servers)
