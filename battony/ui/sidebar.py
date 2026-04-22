"""Left-side tree of servers → channels/queries."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from ..buffer import Activity, BufferKind

if TYPE_CHECKING:
    from ..buffer import Buffer


ACTIVITY_STYLE = {
    Activity.NONE: "grey70",
    Activity.EVENT: "grey82",
    Activity.MESSAGE: "bold bright_cyan",
    Activity.HIGHLIGHT: "bold bright_magenta",
}


class BufferTree(Tree[object]):
    DEFAULT_CSS = """
    BufferTree {
        background: $panel;
        width: 22;
        border-right: tall $primary-darken-2;
        padding: 0 1;
    }
    BufferTree > .tree--cursor {
        background: $primary 30%;
    }
    """

    class BufferSelected(Message):
        def __init__(self, buffer: "Buffer") -> None:
            self.buffer = buffer
            super().__init__()

    def __init__(self) -> None:
        super().__init__("BattonY", id="buffer-tree")
        self.show_root = True
        self.show_guides = True
        self.guide_depth = 2
        self._server_nodes: dict[str, TreeNode[object]] = {}
        self._buffer_nodes: dict[int, TreeNode[object]] = {}  # id(buffer) -> node

    def add_status_buffer(self, buf: "Buffer") -> None:
        if buf.server is None:
            node = self.root.add(self._label_for(buf), data=buf, expand=True)
        else:
            server_name = buf.name
            node = self.root.add(self._label_for(buf), data=buf, expand=True)
            self._server_nodes[server_name] = node
        self._buffer_nodes[id(buf)] = node

    def add_child_buffer(self, parent_status: "Buffer", buf: "Buffer") -> None:
        parent_node = self._buffer_nodes.get(id(parent_status))
        if parent_node is None:
            parent_node = self.root
        node = parent_node.add_leaf(self._label_for(buf), data=buf)
        self._buffer_nodes[id(buf)] = node
        parent_node.expand()

    def remove_buffer(self, buf: "Buffer") -> None:
        node = self._buffer_nodes.pop(id(buf), None)
        if node is not None:
            node.remove()

    def refresh_buffer(self, buf: "Buffer") -> None:
        node = self._buffer_nodes.get(id(buf))
        if node is not None:
            node.set_label(self._label_for(buf))

    def refresh_all(self) -> None:
        for buf_id, node in self._buffer_nodes.items():
            buf = node.data
            if buf is not None:
                node.set_label(self._label_for(buf))

    def _label_for(self, buf: "Buffer") -> Text:
        style = ACTIVITY_STYLE.get(buf.activity, "grey70")
        icon = {
            BufferKind.STATUS: "◆",
            BufferKind.CHANNEL: "#",
            BufferKind.QUERY: "@",
        }[buf.kind]
        label = Text()
        label.append(f"{icon} ", style=style)
        display_name = buf.name
        if buf.kind == BufferKind.CHANNEL and display_name.startswith("#"):
            display_name = display_name[1:]
        label.append(display_name, style=style)
        if buf.unread and buf.activity in (Activity.MESSAGE, Activity.HIGHLIGHT):
            label.append(f" ({buf.unread})", style="bold bright_yellow")
        return label

    def on_tree_node_selected(self, event: Tree.NodeSelected[object]) -> None:
        buf = event.node.data
        if buf is not None:
            self.post_message(self.BufferSelected(buf))

    def focus_buffer(self, buf: "Buffer") -> None:
        node = self._buffer_nodes.get(id(buf))
        if node is not None:
            self.select_node(node)
