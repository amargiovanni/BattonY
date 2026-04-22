"""The main Textual app — wires IRC clients, buffers, UI widgets and commands together."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Input

from .buffer import Activity, Buffer, BufferKind
from .colors import irc_to_rich, nick_color, styled_nick
from .commands import build_registry, parse_command_line
from .config import AppConfig
from .irc.client import IRCClient, ServerConfig
from .irc.message import Message
from .splash import build_splash
from .ui.chatview import ChatView
from .ui.help import HelpScreen
from .ui.input import InputBar
from .ui.nicklist import NickList
from .ui.sidebar import BufferTree
from .ui.statusbar import StatusBar, TopicBar

log = logging.getLogger(__name__)


class BattonYApp(App[None]):
    """The glorious TUI."""

    TITLE = "BattonY"
    SUB_TITLE = "glorious terminal IRC"
    CSS_PATH = "battony.tcss"

    BINDINGS = [
        Binding("f1", "help", "help", show=True),
        Binding("ctrl+n", "next_buffer", "next", show=True),
        Binding("ctrl+p", "prev_buffer", "prev", show=True),
        Binding("ctrl+l", "clear_buffer", "clear"),
        Binding("ctrl+w", "close_buffer", "close"),
        Binding("ctrl+q", "quit_app", "quit"),
        Binding("pageup", "scroll_up", "scroll up", show=False),
        Binding("pagedown", "scroll_down", "scroll down", show=False),
    ]

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.commands = build_registry()
        self.clients: dict[str, IRCClient] = {}
        self.buffers: list[Buffer] = []
        self.current_buffer: Buffer | None = None
        self.welcome_buffer: Buffer = Buffer(name="BattonY", kind=BufferKind.STATUS)

    def _q(self, cls):
        """Widget lookup that always targets the base screen, tolerating teardown."""
        for screen in self.screen_stack:
            try:
                return screen.query_one(cls)
            except NoMatches:
                continue
        return None

    # -------------------------------------------------------- composition

    def compose(self) -> ComposeResult:
        with Vertical(id="main"):
            yield TopicBar(id="topic")
            with Horizontal(id="main-row"):
                yield BufferTree()
                with Vertical(id="chat-wrap"):
                    yield ChatView()
                yield NickList()
            yield StatusBar(id="status")
            yield InputBar(self._complete)

    async def on_mount(self) -> None:
        self.theme = "textual-dark"
        self.buffers.append(self.welcome_buffer)
        tree = self._q(BufferTree)
        tree.add_status_buffer(self.welcome_buffer)
        self._splash_buffer()
        self.activate_buffer(self.welcome_buffer)
        self._q(InputBar).focus()

        # Auto-connect to configured servers.
        for server_cfg in self.config.servers:
            asyncio.create_task(self.connect_server(server_cfg))

    def _splash_buffer(self) -> None:
        panel = build_splash()
        chat = self._q(ChatView)
        chat.append_renderable(panel)
        self.welcome_buffer.add_info(
            "Welcome. Type /help for a command reference, or /connect <host> to get started.",
        )

    # ------------------------------------------------------- buffer mgmt

    def _get_status_buffer(self, client: IRCClient) -> Buffer:
        for b in self.buffers:
            if b.kind == BufferKind.STATUS and b.server is client:
                return b
        status = Buffer(name=client.config.name, kind=BufferKind.STATUS, server=client)
        self.buffers.append(status)
        self._q(BufferTree).add_status_buffer(status)
        return status

    def _get_channel_buffer(self, client: IRCClient, channel: str) -> Buffer:
        key = channel.lower()
        for b in self.buffers:
            if (
                b.kind == BufferKind.CHANNEL
                and b.server is client
                and b.target.lower() == key
            ):
                return b
        buf = Buffer(name=channel, kind=BufferKind.CHANNEL, server=client, target=channel)
        self.buffers.append(buf)
        status = self._get_status_buffer(client)
        self._q(BufferTree).add_child_buffer(status, buf)
        return buf

    def get_or_create_query(self, client: IRCClient, nick: str) -> Buffer:
        for b in self.buffers:
            if b.kind == BufferKind.QUERY and b.server is client and b.target.lower() == nick.lower():
                return b
        buf = Buffer(name=nick, kind=BufferKind.QUERY, server=client, target=nick)
        self.buffers.append(buf)
        status = self._get_status_buffer(client)
        self._q(BufferTree).add_child_buffer(status, buf)
        return buf

    def activate_buffer(self, buf: Buffer) -> None:
        self.current_buffer = buf
        buf.mark_read()
        chat = self._q(ChatView)
        if chat is None:
            # UI not yet mounted (or being torn down) — state is still updated,
            # but skip widget refresh to avoid NoMatches.
            return
        chat.show_buffer(buf)
        tree = self._q(BufferTree)
        if tree is not None:
            tree.refresh_buffer(buf)
            tree.focus_buffer(buf)
        self._refresh_nicklist()
        topic = self._q(TopicBar)
        if topic is not None:
            topic.show_buffer(buf)
        self._update_status()

    def _refresh_nicklist(self) -> None:
        nicklist = self._q(NickList)
        if nicklist is None:
            return
        buf = self.current_buffer
        if buf and buf.kind == BufferKind.CHANNEL and buf.server is not None:
            chan = buf.server.channels.get(buf.target.lower())
            nicklist.show_channel(chan)
            nicklist.display = True
        else:
            nicklist.show_channel(None)
            nicklist.display = False

    def _update_status(self) -> None:
        status = self._q(StatusBar)
        if status is None:
            return
        buf = self.current_buffer
        if buf is None:
            status.nick = "-"
            status.server_name = "-"
            status.buffer_name = "-"
            status.mode = ""
            return
        status.nick = buf.server.nick if buf.server else self.config.user.nick
        status.server_name = buf.server.config.name if buf.server else "local"
        status.buffer_name = buf.name
        status.mode = ""

    def cycle_buffer(self, direction: int) -> None:
        if not self.buffers:
            return
        try:
            idx = self.buffers.index(self.current_buffer) if self.current_buffer else -1
        except ValueError:
            idx = -1
        idx = (idx + direction) % len(self.buffers)
        self.activate_buffer(self.buffers[idx])

    async def close_current_buffer(self) -> None:
        buf = self.current_buffer
        if buf is None or buf is self.welcome_buffer:
            self.status_write("cannot close this buffer", error=True)
            return

        if buf.kind == BufferKind.CHANNEL and buf.server is not None and buf.server.connected:
            try:
                await buf.server.part(buf.target, "closing")
            except Exception:
                pass

        self.buffers.remove(buf)
        self._q(BufferTree).remove_buffer(buf)
        if self.buffers:
            self.activate_buffer(self.buffers[-1])
        else:
            self.current_buffer = None
            self._update_status()

    # --------------------------------------------------------- server mgmt

    async def connect_server(self, cfg: ServerConfig) -> None:
        client = IRCClient(cfg)
        self.clients[cfg.name] = client
        client.on(self._on_irc_event)
        status = self._get_status_buffer(client)
        status.add_info(f"connecting to {cfg.host}:{cfg.port} (tls={cfg.tls})…")
        self.activate_buffer(status)
        try:
            await client.connect()
        except Exception as exc:
            status.add_error(f"connection failed: {exc}")
            self._refresh_ui_for(status)

    async def disconnect_server(self, client: IRCClient, reason: str) -> None:
        await client.disconnect(reason)
        status = self._get_status_buffer(client)
        status.add_info(f"disconnected: {reason}")
        self._refresh_ui_for(status)

    async def quit_all(self, reason: str) -> None:
        await asyncio.gather(*(c.disconnect(reason) for c in self.clients.values()), return_exceptions=True)
        self.exit()

    # -------------------------------------------------------- IRC events

    async def _on_irc_event(self, client: IRCClient, msg: Message) -> None:
        cmd = msg.command

        if cmd == "*CONNECTED*":
            self._get_status_buffer(client).add_info("socket connected — registering…")
            self._refresh_ui_for(self._get_status_buffer(client))
            return
        if cmd == "*DISCONNECTED*":
            self._get_status_buffer(client).add_error("disconnected from server")
            self._refresh_ui_for(self._get_status_buffer(client))
            return

        if cmd == "PRIVMSG":
            self._handle_privmsg(client, msg)
            return

        if cmd == "NOTICE":
            self._handle_notice(client, msg)
            return

        if cmd == "JOIN":
            self._handle_join(client, msg)
            return

        if cmd == "PART":
            self._handle_part(client, msg)
            return

        if cmd == "QUIT":
            self._handle_quit(client, msg)
            return

        if cmd == "NICK":
            self._handle_nick(client, msg)
            return

        if cmd == "KICK":
            self._handle_kick(client, msg)
            return

        if cmd == "TOPIC":
            channel = msg.params[0] if msg.params else ""
            buf = self._get_channel_buffer(client, channel)
            setter = msg.source or "server"
            buf.add_event(Text.assemble(
                ("» ", "bold bright_yellow"),
                (setter, f"bold {nick_color(setter)}"),
                (" changed topic to: ", "grey70"),
            ))
            buf.lines[-1].text.append_text(irc_to_rich(msg.trailing))
            self._refresh_ui_for(buf)
            if buf is self.current_buffer:
                self._q(TopicBar).show_buffer(buf)
            return

        if cmd == "332":  # RPL_TOPIC
            channel = msg.params[1] if len(msg.params) > 1 else ""
            buf = self._get_channel_buffer(client, channel)
            t = Text.assemble(("topic: ", "grey70"))
            t.append_text(irc_to_rich(msg.trailing))
            buf.add_info(t)
            if buf is self.current_buffer:
                self._q(TopicBar).show_buffer(buf)
            self._refresh_ui_for(buf)
            return

        if cmd in {"372", "375", "376"}:
            self._get_status_buffer(client).add_info(msg.trailing, style="grey70")
            self._refresh_ui_for(self._get_status_buffer(client))
            return

        if cmd in {"903", "904", "905", "906", "907"}:
            await client.sasl_done()
            status = self._get_status_buffer(client)
            if cmd == "903":
                status.add_info("SASL: authenticated")
            else:
                status.add_error(f"SASL failed ({cmd}): {msg.trailing}")
            self._refresh_ui_for(status)
            return

        if cmd == "433":  # nickname in use
            status = self._get_status_buffer(client)
            status.add_error(f"nickname in use: {msg.param(1)}")
            if not client.registered:
                alt = client.config.nick + "_"
                await client.set_nick(alt)
                status.add_info(f"trying {alt}")
            self._refresh_ui_for(status)
            return

        if cmd.isdigit():
            status = self._get_status_buffer(client)
            text = " ".join(msg.params[1:] if len(msg.params) > 1 else msg.params)
            status.add_info(f"[{cmd}] {text}", style="grey58")
            self._refresh_ui_for(status)
            return

    def _handle_privmsg(self, client: IRCClient, msg: Message) -> None:
        target = msg.param(0)
        text = msg.trailing
        nick = msg.source or "?"
        is_action = text.startswith("\x01ACTION ") and text.endswith("\x01")
        if is_action:
            text = text[len("\x01ACTION ") : -1]

        if target.lower() == client.nick.lower():
            # Query (PM).
            buf = self.get_or_create_query(client, nick)
        else:
            buf = self._get_channel_buffer(client, target)

        prefix = ""
        if buf.kind == BufferKind.CHANNEL and buf.server is not None:
            chan = buf.server.channels.get(buf.target.lower())
            if chan and nick in chan.members:
                prefix = chan.members[nick][:1]

        highlights = [client.nick] + self.config.user.highlights
        buf.add_message(
            nick,
            text,
            is_action=is_action,
            prefix=prefix,
            highlight_words=highlights,
        )
        self._refresh_ui_for(buf)
        if buf.lines and buf.lines[-1].highlight:
            self.bell()

    def _handle_notice(self, client: IRCClient, msg: Message) -> None:
        target = msg.param(0)
        nick = msg.source or "server"
        buf = self._get_status_buffer(client)
        if target and target.startswith(("#", "&", "!", "+")):
            buf = self._get_channel_buffer(client, target)
        buf.add_notice(nick, msg.trailing)
        self._refresh_ui_for(buf)

    def _handle_join(self, client: IRCClient, msg: Message) -> None:
        channel = msg.param(0) or msg.trailing
        nick = msg.source or ""
        buf = self._get_channel_buffer(client, channel)
        if nick.lower() == client.nick.lower():
            buf.add_info(f"you joined {channel}", style="bold bright_green")
            self.activate_buffer(buf)
        else:
            t = Text.assemble(
                ("→ ", "bold bright_green"),
                (nick, f"bold {nick_color(nick)}"),
                (" joined ", "grey70"),
                (channel, "bright_cyan"),
            )
            buf.add_event(t)
        self._refresh_ui_for(buf)

    def _handle_part(self, client: IRCClient, msg: Message) -> None:
        channel = msg.param(0)
        nick = msg.source or ""
        buf = self._get_channel_buffer(client, channel)
        reason = msg.trailing
        t = Text.assemble(
            ("← ", "bold bright_red"),
            (nick, f"bold {nick_color(nick)}"),
            (" left ", "grey70"),
            (channel, "bright_cyan"),
        )
        if reason:
            t.append(f" ({reason})", style="grey50")
        buf.add_event(t)
        self._refresh_ui_for(buf)

    def _handle_kick(self, client: IRCClient, msg: Message) -> None:
        channel = msg.param(0)
        victim = msg.param(1)
        by = msg.source or ""
        buf = self._get_channel_buffer(client, channel)
        t = Text.assemble(
            ("✖ ", "bold bright_red"),
            (victim, f"bold {nick_color(victim)}"),
            (" kicked by ", "grey70"),
            (by, f"bold {nick_color(by)}"),
        )
        if msg.trailing:
            t.append(f" ({msg.trailing})", style="grey50")
        buf.add_event(t)
        self._refresh_ui_for(buf)

    def _handle_quit(self, client: IRCClient, msg: Message) -> None:
        nick = msg.source or ""
        reason = msg.trailing
        for buf in self.buffers:
            if buf.server is client and buf.kind == BufferKind.CHANNEL:
                chan = client.channels.get(buf.target.lower())
                # Only log on channels that contained the user (channels state was
                # already cleared by the client, so check by name via recent events).
                t = Text.assemble(
                    ("⚡ ", "bold bright_red"),
                    (nick, f"bold {nick_color(nick)}"),
                    (" quit", "grey70"),
                )
                if reason:
                    t.append(f" ({reason})", style="grey50")
                buf.add_event(t)
                self._refresh_ui_for(buf)

    def _handle_nick(self, client: IRCClient, msg: Message) -> None:
        old = msg.source
        new = msg.trailing or msg.param(0)
        if not old or not new:
            return
        for buf in self.buffers:
            if buf.server is not client:
                continue
            if buf.kind == BufferKind.CHANNEL:
                chan = client.channels.get(buf.target.lower())
                if chan and new in chan.members:
                    t = Text.assemble(
                        ("↻ ", "bold bright_yellow"),
                        (old, f"bold {nick_color(old)}"),
                        (" is now ", "grey70"),
                        (new, f"bold {nick_color(new)}"),
                    )
                    buf.add_event(t)
                    self._refresh_ui_for(buf)
            elif buf.kind == BufferKind.QUERY and buf.target.lower() == old.lower():
                buf.target = new
                buf.name = new
                self._q(BufferTree).refresh_buffer(buf)

    # ---------------------------------------------------------- self echo

    def on_self_message(self, client: IRCClient, target: str, text: str) -> None:
        if target.startswith(("#", "&", "!", "+")):
            buf = self._get_channel_buffer(client, target)
        else:
            buf = self.get_or_create_query(client, target)
        buf.add_message(client.nick, text, is_self=True)
        self._refresh_ui_for(buf)

    def on_self_action(self, client: IRCClient, target: str, text: str) -> None:
        if target.startswith(("#", "&", "!", "+")):
            buf = self._get_channel_buffer(client, target)
        else:
            buf = self.get_or_create_query(client, target)
        buf.add_message(client.nick, text, is_self=True, is_action=True)
        self._refresh_ui_for(buf)

    # --------------------------------------------------------- UI helpers

    def _refresh_ui_for(self, buf: Buffer) -> None:
        tree = self._q(BufferTree)
        if tree is not None:
            tree.refresh_buffer(buf)
        if buf is self.current_buffer:
            chat = self._q(ChatView)
            if chat is not None and buf.lines:
                chat.append_line(buf.lines[-1])
            if buf.kind == BufferKind.CHANNEL:
                self._refresh_nicklist()
            topic = self._q(TopicBar)
            if topic is not None:
                topic.show_buffer(buf)
            buf.mark_read()
            if tree is not None:
                tree.refresh_buffer(buf)
        self._update_status()

    def refresh_chat(self) -> None:
        if self.current_buffer:
            chat = self._q(ChatView)
            if chat is not None:
                chat.show_buffer(self.current_buffer)

    def status_write(self, text: str, *, error: bool = False) -> None:
        buf = self.current_buffer or self.welcome_buffer
        if error:
            buf.add_error(text)
        else:
            buf.add_info(text)
        self._refresh_ui_for(buf)

    # ----------------------------------------------------------- input

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value
        input_bar = self._q(InputBar)
        if input_bar is not None:
            input_bar.remember(value)
            input_bar.value = ""
        if not value:
            return
        if value.startswith("/") and not value.startswith("//"):
            await self._run_command(value)
        else:
            text = value[1:] if value.startswith("//") else value
            await self._send_to_current(text)

    async def _run_command(self, line: str) -> None:
        ctx = parse_command_line(line)
        fn = self.commands.resolve(ctx.name)
        if fn is None:
            self.status_write(f"unknown command: /{ctx.name}", error=True)
            return
        try:
            await fn(self, ctx)
        except Exception as exc:
            log.exception("command failed")
            self.status_write(f"/{ctx.name}: {exc}", error=True)

    async def _send_to_current(self, text: str) -> None:
        buf = self.current_buffer
        if buf is None or buf.kind not in (BufferKind.CHANNEL, BufferKind.QUERY):
            self.status_write("no channel or query active — use /msg or /join", error=True)
            return
        if buf.server is None or not buf.server.connected:
            self.status_write("not connected", error=True)
            return
        await buf.server.send_privmsg(buf.target, text)
        self.on_self_message(buf.server, buf.target, text)

    # -------------------------------------------------------- completion

    def _complete(self, word: str) -> list[str]:
        if word.startswith("/"):
            prefix = word[1:].lower()
            return ["/" + n for n in self.commands.names() if n.startswith(prefix)]
        if word.startswith("#"):
            suggestions: set[str] = set()
            for c in self.clients.values():
                for chan in c.channels:
                    if chan.startswith(word.lower()):
                        suggestions.add(c.channels[chan].name)
            return sorted(suggestions)
        # nick completion for current channel
        buf = self.current_buffer
        if buf and buf.kind == BufferKind.CHANNEL and buf.server is not None:
            chan = buf.server.channels.get(buf.target.lower())
            if chan is not None:
                lower = word.lower()
                matches = [n for n in chan.members if n.lower().startswith(lower)]
                matches.sort(key=str.lower)
                if matches:
                    input_bar = self._q(InputBar)
                    value = input_bar.value if input_bar is not None else ""
                    # BitchX-style: append ": " when completing at start of input.
                    at_start = value.lstrip().startswith(word)
                    suffix = ": " if at_start else " "
                    return [m + suffix for m in matches]
        return []

    # ----------------------------------------------------------- actions

    async def on_buffer_tree_buffer_selected(
        self, message: "BufferTree.BufferSelected"
    ) -> None:
        self.activate_buffer(message.buffer)
        input_bar = self._q(InputBar)
        if input_bar is not None:
            input_bar.focus()

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self.commands.all_help()))

    def action_next_buffer(self) -> None:
        self.cycle_buffer(1)

    def action_prev_buffer(self) -> None:
        self.cycle_buffer(-1)

    def action_clear_buffer(self) -> None:
        if self.current_buffer:
            self.current_buffer.lines.clear()
            self.refresh_chat()

    async def action_close_buffer(self) -> None:
        await self.close_current_buffer()

    async def action_quit_app(self) -> None:
        await self.quit_all("BattonY — fades into static")

    def action_scroll_up(self) -> None:
        chat = self._q(ChatView)
        if chat is not None:
            chat.scroll_page_up()

    def action_scroll_down(self) -> None:
        chat = self._q(ChatView)
        if chat is not None:
            chat.scroll_page_down()
