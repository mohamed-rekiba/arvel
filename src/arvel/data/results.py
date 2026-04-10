"""Typed result wrappers for queries that extend the base model shape.

``WithCount[T]`` wraps models returned by ``with_count()`` queries,
replacing the untyped ``setattr`` approach.

``TreeNode[T]`` wraps rows from recursive CTE queries.  It's a Pydantic
``BaseModel`` so ``model_dump()`` / ``model_dump_json()`` work out of the
box — consistent with ``ArvelModel``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase


@dataclass
class WithCount[T: DeclarativeBase]:
    """Typed wrapper for query results that include relationship counts.

    Access the original model instance via ``.instance`` and counts
    via ``.counts``::

        results: list[WithCount[User]] = await User.query(s).with_count("posts").all()
        for r in results:
            user = r.instance
            n_posts = r.counts["posts"]
            # or use the convenience accessor:
            n_posts = r.posts_count  # equivalent to r.counts["posts"]
    """

    instance: T
    counts: dict[str, int] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        if name.endswith("_count"):
            rel_name = name.removesuffix("_count")
            if rel_name in self.counts:
                return self.counts[rel_name]
        raise AttributeError(f"'{type(self).__name__}' has no attribute {name!r}")


class TreeNode[T: DeclarativeBase](BaseModel):
    """Nested tree wrapper for recursive CTE query results.

    Rows returned by a recursive CTE are flat; ``build_tree`` assembles
    them into a proper nested structure using the parent FK column::

        roots = await Category.query(s).descendants(1).all()
        for node in roots:
            print(node.model_dump_json(indent=2))
    """

    model_config = {"arbitrary_types_allowed": True}

    data: dict[str, Any]
    depth: int
    children: list[TreeNode[T]] = []

    @classmethod
    def from_row(cls, row: tuple[Any, ...], column_names: list[str]) -> TreeNode[T]:
        """Build a flat ``TreeNode`` from a raw CTE result row.

        The last element is always the ``depth`` column added by the
        recursive builder.
        """
        depth = int(row[-1])
        data = dict(zip(column_names, row[:-1], strict=False))
        return cls(data=data, depth=depth)

    @classmethod
    def build_tree(
        cls,
        flat_nodes: list[TreeNode[T]],
        *,
        id_key: str = "id",
        parent_key: str = "parent_id",
    ) -> list[TreeNode[T]]:
        """Assemble flat nodes into a nested tree.

        Returns the root nodes with ``children`` populated recursively.
        Nodes whose parent is missing from the set are treated as roots.
        """
        by_id: dict[Any, TreeNode[T]] = {}
        for node in flat_nodes:
            node.children = []
            by_id[node.data.get(id_key)] = node

        roots: list[TreeNode[T]] = []
        for node in flat_nodes:
            parent_id = node.data.get(parent_key)
            parent = by_id.get(parent_id)
            if parent is not None and parent is not node:
                parent.children.append(node)
            else:
                roots.append(node)
        return roots

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Flatten ``data`` into the top level and nest children."""
        result: dict[str, Any] = {**self.data, "depth": self.depth}
        if self.children:
            result["children"] = [child.model_dump(**kwargs) for child in self.children]
        return result

    def __str__(self) -> str:
        return self.model_dump_json(indent=2)

    def __repr__(self) -> str:
        return f"TreeNode(depth={self.depth}, data={self.data!r})"
