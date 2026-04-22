"""Slash command dispatcher — /join, /msg, /quit, etc."""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from .buffer import BufferKind
from .irc.client import IRCClient, ServerConfig

if TYPE_CHECKING:
    from .app import BattonYApp


CommandFn = Callable[["BattonYApp", "CommandContext"], Awaitable[None]]


@dataclass
class CommandContext:
    raw: str           # full line after the slash
    name: str          # command name, lowercased
    args: list[str]    # shell-split args (for commands that want them parsed)
    rest: str          # everything after the command name, unparsed


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, CommandFn] = {}
        self._aliases: dict[str, str] = {}
        self._help: dict[str, str] = {}

    def register(
        self, name: str, fn: CommandFn, *, help: str = "", aliases: tuple[str, ...] = ()
    ) -> None:
        self._commands[name.lower()] = fn
        self._help[name.lower()] = help
        for alias in aliases:
            self._aliases[alias.lower()] = name.lower()

    def resolve(self, name: str) -> CommandFn | None:
        key = name.lower()
        key = self._aliases.get(key, key)
        return self._commands.get(key)

    def names(self) -> list[str]:
        return sorted(self._commands)

    def help_for(self, name: str) -> str:
        key = self._aliases.get(name.lower(), name.lower())
        return self._help.get(key, "")

    def all_help(self) -> list[tuple[str, str]]:
        return [(n, self._help.get(n, "")) for n in self.names()]


def _require_server(app: "BattonYApp") -> IRCClient | None:
    buf = app.current_buffer
    if buf and buf.server:
        return buf.server
    if app.clients:
        return next(iter(app.clients.values()))
    app.status_write("no server — use /connect host[:port] first", error=True)
    return None


def _require_channel_target(app: "BattonYApp") -> str | None:
    buf = app.current_buffer
    if buf and buf.kind in (BufferKind.CHANNEL, BufferKind.QUERY):
        return buf.target
    app.status_write("this command needs an active channel or query", error=True)
    return None


async def cmd_help(app: "BattonYApp", ctx: CommandContext) -> None:
    if ctx.args:
        name = ctx.args[0].lstrip("/")
        help_text = app.commands.help_for(name)
        if help_text:
            app.status_write(f"/{name} — {help_text}")
        else:
            app.status_write(f"no such command: {name}", error=True)
        return
    app.status_write("commands:")
    for name, text in app.commands.all_help():
        app.status_write(f"  /{name:<10} {text}")


async def cmd_connect(app: "BattonYApp", ctx: CommandContext) -> None:
    if not ctx.args:
        app.status_write("usage: /connect <host[:port]> [--tls/--no-tls] [--name NAME]", error=True)
        return
    hostport = ctx.args[0]
    # IPv6 literals must be bracketed when a port is attached: [2001:db8::1]:6697
    if hostport.startswith("["):
        host, sep, rest = hostport[1:].partition("]")
        port_s = rest[1:] if sep and rest.startswith(":") else ""
    else:
        host, _, port_s = hostport.partition(":")
    port = int(port_s) if port_s else 6697
    tls = True
    name = host
    i = 1
    while i < len(ctx.args):
        a = ctx.args[i]
        if a == "--no-tls":
            tls = False
            if not port_s:
                port = 6667
        elif a == "--tls":
            tls = True
        elif a == "--name" and i + 1 < len(ctx.args):
            name = ctx.args[i + 1]
            i += 1
        i += 1

    cfg = ServerConfig(
        name=name,
        host=host,
        port=port,
        tls=tls,
        nick=app.config.user.nick,
        user=app.config.user.user,
        realname=app.config.user.realname,
    )
    await app.connect_server(cfg)


async def cmd_disconnect(app: "BattonYApp", ctx: CommandContext) -> None:
    client = _require_server(app)
    if not client:
        return
    reason = ctx.rest or "BattonY — fades into static"
    await app.disconnect_server(client, reason)


async def cmd_quit(app: "BattonYApp", ctx: CommandContext) -> None:
    reason = ctx.rest or "BattonY — fades into static"
    await app.quit_all(reason)


async def cmd_join(app: "BattonYApp", ctx: CommandContext) -> None:
    if not ctx.args:
        app.status_write("usage: /join #channel [key]", error=True)
        return
    client = _require_server(app)
    if not client:
        return
    channel = ctx.args[0]
    if not channel.startswith(("#", "&", "!", "+")):
        channel = "#" + channel
    key = ctx.args[1] if len(ctx.args) > 1 else None
    await client.join(channel, key)


async def cmd_part(app: "BattonYApp", ctx: CommandContext) -> None:
    client = _require_server(app)
    if not client:
        return
    channel = ctx.args[0] if ctx.args else _require_channel_target(app)
    if not channel:
        return
    reason = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else "leaving"
    await client.part(channel, reason)


async def cmd_msg(app: "BattonYApp", ctx: CommandContext) -> None:
    if len(ctx.args) < 1 or not ctx.rest:
        app.status_write("usage: /msg <nick|#channel> <text>", error=True)
        return
    client = _require_server(app)
    if not client:
        return
    target = ctx.args[0]
    text = ctx.rest.split(None, 1)[1] if " " in ctx.rest else ""
    if not text:
        app.status_write("no message text", error=True)
        return
    await client.send_privmsg(target, text)
    app.on_self_message(client, target, text)


async def cmd_query(app: "BattonYApp", ctx: CommandContext) -> None:
    if not ctx.args:
        app.status_write("usage: /query <nick> [text]", error=True)
        return
    client = _require_server(app)
    if not client:
        return
    nick = ctx.args[0]
    buf = app.get_or_create_query(client, nick)
    app.activate_buffer(buf)
    if len(ctx.args) > 1:
        text = ctx.rest.split(None, 1)[1]
        await client.send_privmsg(nick, text)
        app.on_self_message(client, nick, text)


async def cmd_me(app: "BattonYApp", ctx: CommandContext) -> None:
    client = _require_server(app)
    target = _require_channel_target(app)
    if not client or not target:
        return
    text = ctx.rest
    if not text:
        app.status_write("usage: /me <action>", error=True)
        return
    await client.send_action(target, text)
    app.on_self_action(client, target, text)


async def cmd_nick(app: "BattonYApp", ctx: CommandContext) -> None:
    if not ctx.args:
        app.status_write("usage: /nick <newnick>", error=True)
        return
    client = _require_server(app)
    if not client:
        return
    await client.set_nick(ctx.args[0])


async def cmd_topic(app: "BattonYApp", ctx: CommandContext) -> None:
    client = _require_server(app)
    target = _require_channel_target(app)
    if not client or not target:
        return
    if not ctx.rest:
        app.status_write("usage: /topic <new topic>", error=True)
        return
    await client.set_topic(target, ctx.rest)


async def cmd_whois(app: "BattonYApp", ctx: CommandContext) -> None:
    if not ctx.args:
        app.status_write("usage: /whois <nick>", error=True)
        return
    client = _require_server(app)
    if not client:
        return
    await client.whois(ctx.args[0])


async def cmd_list(app: "BattonYApp", ctx: CommandContext) -> None:
    client = _require_server(app)
    if not client:
        return
    pattern = ctx.args[0] if ctx.args else None
    await client.list_channels(pattern)


async def cmd_away(app: "BattonYApp", ctx: CommandContext) -> None:
    client = _require_server(app)
    if not client:
        return
    await client.away(ctx.rest or None)


async def cmd_raw(app: "BattonYApp", ctx: CommandContext) -> None:
    client = _require_server(app)
    if not client or not ctx.rest:
        return
    await client.send_raw(ctx.rest)


async def cmd_clear(app: "BattonYApp", ctx: CommandContext) -> None:
    if app.current_buffer:
        app.current_buffer.lines.clear()
        app.refresh_chat()


async def cmd_close(app: "BattonYApp", ctx: CommandContext) -> None:
    await app.close_current_buffer()


async def cmd_next(app: "BattonYApp", ctx: CommandContext) -> None:
    app.cycle_buffer(1)


async def cmd_prev(app: "BattonYApp", ctx: CommandContext) -> None:
    app.cycle_buffer(-1)


def build_registry() -> CommandRegistry:
    r = CommandRegistry()
    r.register("help", cmd_help, help="show this help", aliases=("h", "?"))
    r.register("connect", cmd_connect, help="connect to a server: /connect host[:port]", aliases=("server",))
    r.register("disconnect", cmd_disconnect, help="disconnect from current server")
    r.register("quit", cmd_quit, help="quit all servers and exit", aliases=("exit",))
    r.register("join", cmd_join, help="join a channel: /join #chan [key]", aliases=("j",))
    r.register("part", cmd_part, help="leave a channel: /part [#chan] [reason]", aliases=("leave",))
    r.register("msg", cmd_msg, help="send a message: /msg <target> <text>", aliases=("m",))
    r.register("query", cmd_query, help="open a query window: /query <nick> [text]", aliases=("q",))
    r.register("me", cmd_me, help="CTCP ACTION: /me <text>", aliases=("action",))
    r.register("nick", cmd_nick, help="change nick: /nick <newnick>")
    r.register("topic", cmd_topic, help="set channel topic")
    r.register("whois", cmd_whois, help="query user info")
    r.register("list", cmd_list, help="list channels on server")
    r.register("away", cmd_away, help="mark yourself away (no args to return)")
    r.register("raw", cmd_raw, help="send raw IRC line (advanced)", aliases=("quote",))
    r.register("clear", cmd_clear, help="clear current buffer")
    r.register("close", cmd_close, help="close current buffer", aliases=("wc",))
    r.register("next", cmd_next, help="next buffer")
    r.register("prev", cmd_prev, help="previous buffer")
    return r


def parse_command_line(line: str) -> CommandContext:
    body = line[1:] if line.startswith("/") else line
    name, _, rest = body.partition(" ")
    try:
        args = shlex.split(rest) if rest else []
    except ValueError:
        # unbalanced quotes — fall back to simple split
        args = rest.split()
    return CommandContext(raw=body, name=name.lower(), args=args, rest=rest)
