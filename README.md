```
 ____        _   _             __   __
| __ )  __ _| |_| |_ ___  _ __ \ \ / /
|  _ \ / _` | __| __/ _ \| '_ \ \ V /
| |_) | (_| | |_| || (_) | | | | | |
|____/ \__,_|\__|\__\___/|_| |_| |_|
```

# BattonY

> **a modern, glorious, BitchX-inspired IRC client for the terminal**

BattonY is IRC the way it should feel in 2026: smooth, colorful, keyboard-first,
zero cruft. A single-binary Python app that drops you into a 4-pane cockpit
(servers ▸ chat ▸ nicks + topic + status), speaks IRCv3, renders mIRC colors,
auto-colors nicks, and only ever leaves your terminal.

No Electron. No web. No tracking. Just the protocol, the people, and the glow of
ANSI on a dark background.

---

## ✨ features

- **Modern TUI** built on [Textual](https://textual.textualize.io/) — smooth,
  mouse + keyboard, resizable, themeable.
- **IRCv3 ready** — CAP negotiation, message tags, `server-time`, `away-notify`,
  `account-tag`, `chghost`, `extended-join`, `multi-prefix`, `userhost-in-names`,
  `echo-message`.
- **SASL PLAIN** authentication out of the box.
- **TLS by default** (port 6697); plain TCP available with `--no-tls`.
- **Multi-server, multi-channel, multi-query** — one tree, infinite buffers.
- **mIRC color codes** rendered faithfully (`\x03fg,bg`, `\x02` bold, `\x1f`
  underline, `\x1d` italic, `\x16` reverse, `\x1e` strike, `\x0f` reset).
- **Deterministic nick coloring** — the same nick is always the same color,
  everywhere, forever.
- **Highlights & bell** when your nick (or any configured word) is mentioned.
- **URL highlighting** — links become underlined and clickable where your
  terminal supports it.
- **BitchX-style nick completion** with Tab (cycles through matches, appends
  `: ` at the start of the line).
- **Command history** — up/down arrows (or `Ctrl-P`/`Ctrl-N` inside input).
- **A glorious ASCII splash** on start, because an IRC client should make an
  entrance.
- **Status bar & topic bar** with live clock, current nick, server, buffer and
  channel modes.
- **Activity indicators** in the sidebar — subtle for joins/parts, bright for
  messages, neon for mentions.
- **Logging** to `~/.config/battony/logs/battony.log` for debugging.
- **TOML config**, auto-created on first run.

---

## 🚀 quick start

```bash
# clone and install
git clone https://github.com/amargiovanni/battony.git
cd battony
pip install -e .

# run
battony
# or: python -m battony
```

First run creates a sample config at `~/.config/battony/config.toml`.
Edit it to add your servers, then relaunch — BattonY will autoconnect and
autojoin.

### Zero-config trial

Don't want to edit anything? Just run `battony` and type:

```
/connect irc.libera.chat
/join #battony
```

---

## ⌨️ keybindings

| key               | does                                 |
|-------------------|--------------------------------------|
| `F1`              | toggle the glorious help screen      |
| `Ctrl+N` / `Ctrl+P` | next / previous buffer             |
| `Ctrl+L`          | clear current buffer                 |
| `Ctrl+W`          | close current buffer                 |
| `Ctrl+Q`          | quit (disconnects all servers)       |
| `Tab`             | complete nick / command / channel    |
| `↑` / `↓`         | input history                        |
| `PgUp` / `PgDn`   | scroll chat                          |
| mouse-click       | switch buffer in the tree            |

---

## 💬 slash commands

```
/help [cmd]                   show help (or detail for a specific command)
/connect host[:port] [--no-tls] [--name NAME]
/disconnect [reason]          leave the current server
/quit [reason]                quit all servers and exit
/join #chan [key]             (alias /j)
/part [#chan] [reason]        (alias /leave)
/msg <target> <text>          (alias /m)
/query <nick> [text]          (alias /q) — open a PM buffer
/me <action>                  CTCP ACTION
/nick <newnick>
/topic <text>                 set current channel's topic
/whois <nick>
/list [pattern]
/away [reason]                (no args to unmark yourself)
/raw <irc line>               (alias /quote)
/clear                        clear current buffer
/close                        close current buffer (alias /wc)
/next /prev                   cycle buffers
```

Start a message with `//` to send a literal line beginning with `/`.

---

## 🛠️ configuration

The file lives at `~/.config/battony/config.toml` (or whatever
`platformdirs.user_config_dir("battony")` resolves to on your OS).

```toml
[user]
nick = "yournick"
user = "yournick"
realname = "your name"
highlights = ["yournick", "yourothernick", "keyword"]

[[servers]]
name = "libera"
host = "irc.libera.chat"
port = 6697
tls = true
autojoin = ["#battony", "##programming"]
# SASL (optional):
# sasl_user = "yournick"
# sasl_pass = "yourpass"

[[servers]]
name = "oftc"
host = "irc.oftc.net"
port = 6697
tls = true
autojoin = []
```

Add as many `[[servers]]` blocks as you like — BattonY will autoconnect to all
of them when it launches.

Logs live at `~/.config/battony/logs/battony.log`. Run with `-v` for debug
level.

---

## 🏗️ architecture

```
battony/
├── __main__.py         entry point (argparse + run)
├── app.py              Textual App — glues everything
├── splash.py           the ASCII welcome panel
├── buffer.py           in-memory buffers (status / channel / query)
├── colors.py           mIRC code → Rich Text, deterministic nick colors
├── commands.py         slash-command registry & dispatcher
├── config.py           TOML config loading
├── battony.tcss        Textual CSS theme
├── irc/
│   ├── client.py       async IRC client (TLS, CAP, SASL, autoreconnect)
│   ├── message.py      RFC 1459/2812 + IRCv3 tag parser
│   └── numerics.py     named numeric reply codes
└── ui/
    ├── chatview.py     scrollable chat log
    ├── sidebar.py      tree of servers/channels/queries
    ├── nicklist.py     right-side user list
    ├── input.py        input bar with history + Tab completion
    ├── statusbar.py    top topic bar + bottom status bar
    └── help.py         modal help screen
```

The IRC client is a clean, testable `asyncio` layer that knows nothing about
the UI. The UI subscribes via `client.on(handler)` and translates wire events
into buffer updates. You could drive a bot off the same `IRCClient` class.

---

## 🧪 development

```bash
# install dev deps
pip install -e '.[dev]'

# quick sanity checks
python -m py_compile battony/*.py battony/*/*.py
python -c "from battony.irc.message import Message; print(Message.parse(':n!u@h PRIVMSG #c :hi'))"

# headless Textual smoke test
python -c "
import asyncio; from battony.app import BattonYApp
from battony.config import AppConfig, UserConfig
async def go():
    app = BattonYApp(AppConfig(user=UserConfig(nick='t')))
    async with app.run_test() as pilot:
        await pilot.press('f1'); await pilot.press('escape')
asyncio.run(go())
"
```

---

## 🗺️ roadmap

- DCC SEND / CHAT
- SASL EXTERNAL (client-cert auth)
- Auto-reconnect with exponential backoff
- Per-network profiles with hotkeys (`Alt-1..9` to jump between servers)
- Scrollback search (`/` inside a buffer)
- Scriptable events (`~/.config/battony/scripts/*.py`)
- Channel logging to disk
- Per-channel themes & BitchX-style `/fish` easter eggs 🐠

PRs welcome. The architecture is small; the vibe is large.

---

## 📜 license

MIT. Do what you want, just keep the glory alive.

---

<sub>BattonY is not affiliated with, endorsed by, or descended from the
original BitchX. It's a love letter, not a fork. The terminal remembers.</sub>
