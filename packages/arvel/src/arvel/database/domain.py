"""Domain service pattern for read/write split.

Closes GAP-006 from ``.context/extras/framework-gaps.md``.

The canonical use case is checkout-style stock decrements: validate the resource
exists via a read model (e.g. ``PublishedProduct``), then acquire a write lock on
the write-side row (e.g. ``Product``) within an open transaction.

Example::

    class StockService(DomainService[PublishedProduct, Product]):
        read_model = PublishedProduct
        write_model = Product

    async def checkout(order_id: str, product_id: str) -> None:
        async with DB.transaction():
            product = await StockService.get_for_write(product_id)
            product.stock_qty -= 1
            await product.save()
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from arvel.database.exceptions import OutsideTransactionError, ReadModelNotFoundError
from arvel.database.session import get_optional_session

R = TypeVar("R")  # read model
W = TypeVar("W")  # write model


class DomainService(Generic[R, W]):
    """Base for services that split reads (via a view/read model) from writes (via the ORM row).

    Subclasses declare ``read_model`` and ``write_model`` as class attributes.
    ``get_for_write(pk)`` then:

    1. Validates the resource exists via ``read_model`` (fails fast, no lock).
    2. Acquires a ``SELECT … FOR UPDATE`` lock on ``write_model``.
    3. Returns the locked write-side instance ready for mutation.

    Must be called inside a ``DB.transaction()`` block — raises
    ``OutsideTransactionError`` otherwise.
    """

    read_model: ClassVar[Any]
    write_model: ClassVar[Any]

    @classmethod
    async def get_for_write(cls, pk: Any) -> Any:
        """Validate via the read model, then lock and return the write-side row.

        Raises ``OutsideTransactionError`` when called outside a transaction.
        Raises ``ReadModelNotFoundError`` when ``read_model`` has no row for ``pk``
        (e.g. resource is unpublished).  The write-side lock is never acquired in
        that case — no unnecessary contention.
        """
        if get_optional_session() is None:
            raise OutsideTransactionError

        read_model: Any = cls.read_model
        write_model: Any = cls.write_model
        read_model_name: str = getattr(read_model, "__name__", repr(read_model))
        write_model_name: str = getattr(write_model, "__name__", repr(write_model))

        # Step 1 — fast visibility check against the read model (no lock).
        exists = await read_model.find(pk)
        if exists is None:
            raise ReadModelNotFoundError(read_model_name, pk)

        # Step 2 — acquire write lock on the canonical row.
        locked: Any = (
            await write_model.query()
            .where_raw(
                f"{_pk_column(write_model)} = :pk",
                {"pk": str(pk)},
            )
            .lock_for_update()
            .first()
        )

        if locked is None:
            # Write row missing while read-model row exists — materialized view lag.
            raise ReadModelNotFoundError(write_model_name, pk)

        return locked


def _pk_column(model: Any) -> str:
    """Return the quoted primary-key column name for ``model``."""
    from sqlalchemy import inspect as sqla_inspect

    mapper = sqla_inspect(model)
    pk_col = mapper.primary_key[0]
    table = mapper.persist_selectable
    return f"{table.name}.{pk_col.key}"


__all__ = ["DomainService"]
