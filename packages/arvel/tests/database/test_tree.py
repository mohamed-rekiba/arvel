"""TreeNode value behavior."""

from __future__ import annotations

from arvel.database.tree import TreeNode


def test_tree_node_repr_equality_and_hash() -> None:
    child = TreeNode("child", depth=1)
    node = TreeNode("root", depth=0, children=[child])
    same = TreeNode("root", depth=0, children=[TreeNode("child", depth=1)])

    assert repr(node) == (
        "TreeNode(node='root', depth=0, children=[TreeNode(node='child', depth=1, children=[])])"
    )
    assert node == same
    assert node != object()
    assert hash(node) == id(node)
