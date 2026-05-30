"""TreeNode — generic class for recursive CTE tree assembly."""

from __future__ import annotations

from typing import Generic, TypeVar, cast

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


__all__ = ["TreeNode"]
