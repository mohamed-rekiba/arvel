"""TreeNode — generic class for recursive CTE tree assembly."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar, cast

T = TypeVar("T")


class TreeNode(Generic[T]):
    """A node in a tree assembled from a recursive CTE result set.

    Single-pass O(n) assembly: one dict lookup per row, no recursive re-scanning.
    """

    __slots__ = ("children", "depth", "node")

    def __init__(
        self,
        node: T,
        depth: int,
        children: list[TreeNode[T]] | None = None,
    ) -> None:
        self.node = node
        self.depth = depth
        self.children: list[TreeNode[T]] = children if children is not None else []

    def __repr__(self) -> str:
        return f"TreeNode(node={self.node!r}, depth={self.depth}, children={self.children!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TreeNode):
            return NotImplemented
        typed = cast("TreeNode[T]", other)
        return (
            self.node == typed.node
            and self.depth == typed.depth
            and self.children == typed.children
        )

    def __hash__(self) -> int:
        return id(self)


def assemble_forest(
    items: Sequence[T],
    *,
    id_key: str,
    parent_key: str,
    root_depth: int = 0,
) -> list[TreeNode[T]]:
    """Build a TreeNode forest from a flat row set, single-pass O(n).

    A row becomes a root when its ``parent_key`` value is missing from the set,
    so a subtree's direct members surface as roots. Depth is derived from the
    structure (roots at ``root_depth``), not from any CTE column — so it works
    the same for freshly queried rows and cached eager-loaded slices.
    """
    nodes: dict[Any, TreeNode[T]] = {}
    ordered: list[Any] = []
    for obj in items:
        pk = getattr(obj, id_key)
        nodes[pk] = TreeNode(node=obj, depth=root_depth, children=[])
        ordered.append(pk)

    roots: list[TreeNode[T]] = []
    for pk in ordered:
        node = nodes[pk]
        parent_pk = getattr(node.node, parent_key, None)
        parent_node = nodes.get(parent_pk) if parent_pk is not None else None
        if parent_node is None:
            roots.append(node)
        else:
            parent_node.children.append(node)

    for root in roots:
        stack: list[tuple[TreeNode[T], int]] = [(root, root_depth)]
        while stack:
            node, depth = stack.pop()
            node.depth = depth
            stack.extend((child, depth + 1) for child in node.children)

    return roots


__all__ = ["TreeNode", "assemble_forest"]
