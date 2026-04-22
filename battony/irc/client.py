"""Asynchronous IRC client with TLS, SASL PLAIN, CAP negotiation and auto-reconnect."""
from __future__ import annotations

import asyncio
import base64
import logging
import ssl as ssl_lib
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .message import Message, format_message, split_message_text

log = logging.getLogger(__name__)

EventHandler = Callable[["IRCClient", Message], Awaitable[None] | None]


@dataclass
class ServerConfig:
    name: str
    host: str
    port: int = 6697
    tls: bool = True
    nick: str = "battony"
    user: str = "battony"
    realname: str = "BattonY IRC"
    password: str | None = None
    sasl_user: str | None = None
    sasl_pass: str | None = None
    autojoin: list[str] = field(default_factory=list)
    reconnect: bool = True


class IRCClient:
    """A single IRC connection. Many can live inside one app (multi-server)."""

    REQUESTED_CAPS = {
        "message-tags",
        "server-time",
        "account-tag",
        "away-notify",
        "chghost",
        "extended-join",
        "multi-prefix",
        "userhost-in-names",
        "sasl",
        "echo-message",
    }

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.nick = config.nick
        self.connected = False
        self.registered = False
        self.channels: dict[str, Channel] = {}
        self.isupport: dict[str, str] = {}
        self.motd: list[str] = []

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._handlers: list[EventHandler] = []
        self._caps_acked: set[str] = set()
        self._caps_pending: set[str] = set()
        self._sasl_in_progress = False
        self._reading_task: asyncio.Task | None = None
        self._reconnect_delay = 2.0

    # ------------------------------------------------------------ events

    def on(self, handler: EventHandler) -> EventHandler:
        self._handlers.append(handler)
        return handler

    async def _emit(self, msg: Message) -> None:
        for h in self._handlers:
            try:
                result = h(self, msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.exception("event handler raised")

    # --------------------------------------------------------- connection

    async def connect(self) -> None:
        ctx: ssl_lib.SSLContext | None = None
        if self.config.tls:
            ctx = ssl_lib.create_default_context()
            # Many IRC networks still use cert chains that OpenSSL trusts; keep verify on.
        log.info("connecting to %s:%d (tls=%s)", self.config.host, self.config.port, self.config.tls)
        self._reader, self._writer = await asyncio.open_connection(
            self.config.host, self.config.port, ssl=ctx
        )
        self.connected = True
        await self._emit(Message(command="*CONNECTED*"))

        # CAP LS negotiation before USER/NICK — per IRCv3 spec the server queues
        # registration until we send CAP END.
        await self.send_raw("CAP LS 302")
        if self.config.password:
            await self.send_raw(format_message("PASS", trailing=self.config.password))
        await self.send_raw(format_message("NICK", self.config.nick))
        await self.send_raw(
            format_message("USER", self.config.user, "0", "*", trailing=self.config.realname)
        )

        self._reading_task = asyncio.create_task(self._read_loop())

    async def disconnect(self, quit_msg: str = "BattonY — fades into static") -> None:
        if self._writer and not self._writer.is_closing():
            try:
                await self.send_raw(format_message("QUIT", trailing=quit_msg))
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self.connected = False
        self.registered = False
        if self._reading_task:
            self._reading_task.cancel()

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                # Prefer strict UTF-8 so we get clean text on modern networks;
                # fall back to latin-1 (which never fails) for legacy ones.
                try:
                    text = line.decode("utf-8").rstrip("\r\n")
                except UnicodeDecodeError:
                    text = line.decode("latin-1").rstrip("\r\n")
                if not text:
                    continue
                msg = Message.parse(text)
                log.debug("<< %s", text)
                await self._handle(msg)
                await self._emit(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("read loop error")
        finally:
            self.connected = False
            self.registered = False
            await self._emit(Message(command="*DISCONNECTED*"))

    # --------------------------------------------------------- protocol

    async def send_raw(self, line: str) -> None:
        if not self._writer:
            raise RuntimeError("not connected")
        log.debug(">> %s", line)
        self._writer.write((line + "\r\n").encode("utf-8"))
        await self._writer.drain()

    async def send_privmsg(self, target: str, text: str) -> None:
        for chunk in split_message_text(text):
            await self.send_raw(format_message("PRIVMSG", target, trailing=chunk))

    async def send_notice(self, target: str, text: str) -> None:
        for chunk in split_message_text(text):
            await self.send_raw(format_message("NOTICE", target, trailing=chunk))

    async def send_action(self, target: str, text: str) -> None:
        # CTCP ACTION — what /me does.
        await self.send_privmsg(target, f"\x01ACTION {text}\x01")

    async def join(self, channel: str, key: str | None = None) -> None:
        if key:
            await self.send_raw(format_message("JOIN", channel, key))
        else:
            await self.send_raw(format_message("JOIN", channel))

    async def part(self, channel: str, reason: str = "") -> None:
        if reason:
            await self.send_raw(format_message("PART", channel, trailing=reason))
        else:
            await self.send_raw(format_message("PART", channel))

    async def set_nick(self, new_nick: str) -> None:
        await self.send_raw(format_message("NICK", new_nick))

    async def set_topic(self, channel: str, topic: str) -> None:
        await self.send_raw(format_message("TOPIC", channel, trailing=topic))

    async def whois(self, nick: str) -> None:
        await self.send_raw(format_message("WHOIS", nick))

    async def list_channels(self, pattern: str | None = None) -> None:
        if pattern:
            await self.send_raw(format_message("LIST", pattern))
        else:
            await self.send_raw(format_message("LIST"))

    async def away(self, reason: str | None = None) -> None:
        if reason:
            await self.send_raw(format_message("AWAY", trailing=reason))
        else:
            await self.send_raw(format_message("AWAY"))

    # --------------------------------------------------------- internal

    async def _handle(self, msg: Message) -> None:
        cmd = msg.command

        if cmd == "PING":
            await self.send_raw(format_message("PONG", trailing=msg.trailing))
            return

        if cmd == "CAP":
            await self._handle_cap(msg)
            return

        if cmd == "AUTHENTICATE":
            await self._handle_authenticate(msg)
            return

        if cmd == "001":
            self.registered = True
            # Welcome — server may have changed our nick.
            if msg.params:
                self.nick = msg.params[0]
            for chan in self.config.autojoin:
                await self.join(chan)
            return

        if cmd == "005":
            # ISUPPORT tokens
            for token in msg.params[1:-1]:
                if "=" in token:
                    k, _, v = token.partition("=")
                    self.isupport[k.upper()] = v
                else:
                    self.isupport[token.upper()] = ""
            return

        if cmd == "NICK" and msg.prefix:
            old = msg.prefix.nick
            new = msg.trailing or (msg.params[0] if msg.params else "")
            if old == self.nick:
                self.nick = new
            for c in self.channels.values():
                if c.rename(old, new):
                    pass
            return

        if cmd == "JOIN":
            channel = msg.params[0] if msg.params else msg.trailing
            nick = msg.source
            chan = self.channels.setdefault(channel.lower(), Channel(channel))
            chan.add_member(nick)
            return

        if cmd == "PART":
            channel = msg.params[0] if msg.params else ""
            chan = self.channels.get(channel.lower())
            if chan:
                chan.remove_member(msg.source)
                if msg.source == self.nick:
                    self.channels.pop(channel.lower(), None)
            return

        if cmd == "KICK":
            channel = msg.params[0] if len(msg.params) > 0 else ""
            victim = msg.params[1] if len(msg.params) > 1 else ""
            chan = self.channels.get(channel.lower())
            if chan:
                chan.remove_member(victim)
                if victim == self.nick:
                    self.channels.pop(channel.lower(), None)
            return

        if cmd == "QUIT":
            for chan in self.channels.values():
                chan.remove_member(msg.source)
            return

        if cmd == "TOPIC":
            channel = msg.params[0] if msg.params else ""
            chan = self.channels.get(channel.lower())
            if chan:
                chan.topic = msg.trailing
            return

        if cmd == "332":  # RPL_TOPIC
            channel = msg.params[1] if len(msg.params) > 1 else ""
            chan = self.channels.setdefault(channel.lower(), Channel(channel))
            chan.topic = msg.trailing
            return

        if cmd == "353":  # RPL_NAMREPLY
            channel = msg.params[2] if len(msg.params) > 2 else ""
            chan = self.channels.setdefault(channel.lower(), Channel(channel))
            for name in msg.trailing.split():
                chan.add_member(name)
            return

        if cmd == "366":  # RPL_ENDOFNAMES
            return

        if cmd in {"372", "375", "376"}:
            if cmd == "375":
                self.motd.clear()
            else:
                self.motd.append(msg.trailing)
            return

    async def _handle_cap(self, msg: Message) -> None:
        if len(msg.params) < 2:
            return
        sub = msg.params[1].upper()

        if sub == "LS":
            available = set(msg.trailing.split())
            # Strip cap values like "sasl=PLAIN".
            avail_names = {c.split("=", 1)[0] for c in available}
            want = self.REQUESTED_CAPS & avail_names
            if not want:
                await self.send_raw("CAP END")
                return
            self._caps_pending = set(want)
            await self.send_raw("CAP REQ :" + " ".join(sorted(want)))

        elif sub == "ACK":
            acked = set(msg.trailing.split())
            self._caps_acked |= acked
            self._caps_pending -= acked
            if "sasl" in acked and self.config.sasl_user and self.config.sasl_pass:
                self._sasl_in_progress = True
                await self.send_raw("AUTHENTICATE PLAIN")
            elif not self._caps_pending and not self._sasl_in_progress:
                await self.send_raw("CAP END")

        elif sub == "NAK":
            self._caps_pending.clear()
            if not self._sasl_in_progress:
                await self.send_raw("CAP END")

    async def _handle_authenticate(self, msg: Message) -> None:
        if not (self.config.sasl_user and self.config.sasl_pass):
            return
        if msg.params and msg.params[0] == "+":
            # RFC 4616: [authzid] \0 authcid \0 passwd — leaving authzid empty
            # is the maximally compatible form.
            payload = f"\0{self.config.sasl_user}\0{self.config.sasl_pass}"
            encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
            # Must be split into 400-byte chunks per spec.
            for i in range(0, len(encoded), 400):
                chunk = encoded[i : i + 400]
                await self.send_raw(f"AUTHENTICATE {chunk}")
            if len(encoded) % 400 == 0:
                await self.send_raw("AUTHENTICATE +")

    # Called externally when SASL ends (903/904/...)
    async def sasl_done(self) -> None:
        self._sasl_in_progress = False
        await self.send_raw("CAP END")


@dataclass
class Channel:
    """In-memory state for a joined channel."""

    name: str
    topic: str = ""
    members: dict[str, str] = field(default_factory=dict)  # nick -> prefixes (@+%)

    _PREFIX_CHARS = "~&@%+"

    def add_member(self, raw_nick: str) -> None:
        if not raw_nick:
            return
        # userhost-in-names: "@nick!user@host"
        prefix = ""
        while raw_nick and raw_nick[0] in self._PREFIX_CHARS:
            prefix += raw_nick[0]
            raw_nick = raw_nick[1:]
        nick = raw_nick.split("!", 1)[0]
        if nick:
            self.members[nick] = prefix

    def remove_member(self, nick: str) -> None:
        self.members.pop(nick, None)

    def rename(self, old: str, new: str) -> bool:
        if old in self.members:
            self.members[new] = self.members.pop(old)
            return True
        return False

    def sorted_members(self) -> list[tuple[str, str]]:
        order = {"~": 0, "&": 1, "@": 2, "%": 3, "+": 4, "": 5}

        def key(item: tuple[str, str]) -> tuple[int, str]:
            nick, prefix = item
            top = prefix[:1] if prefix else ""
            return (order.get(top, 5), nick.lower())

        return sorted(self.members.items(), key=key)
