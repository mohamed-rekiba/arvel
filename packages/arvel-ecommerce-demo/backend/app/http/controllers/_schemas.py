"""Pydantic request-body schemas shared across controllers."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    email: str
    password: str


class RegisterPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    email: str
    password: str


class AddCartItemPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    product_id: str
    quantity: Annotated[int, Field(ge=1)] = 1


class UpdateCartItemPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    quantity: Annotated[int, Field(ge=1)]


class CheckoutPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    shipping_address: dict[str, Any]


class CreateProductPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: dict[str, str]
    slug: dict[str, str] = {}
    description: dict[str, str] = {}
    price: float
    stock_qty: int = 0
    category_id: str
    vendor_id: str = ""


class UpdateProductPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: dict[str, str] | None = None
    slug: dict[str, str] | None = None
    description: dict[str, str] | None = None
    price: float | None = None
    stock_qty: int | None = None


class CreateCategoryPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: dict[str, str]
    slug: dict[str, str]
    parent_id: str | None = None
    status: str = "draft"
    published_at: datetime | None = None


class UpdateCategoryPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: dict[str, str] | None = None
    slug: dict[str, str] | None = None
    parent_id: str | None = None
    status: str | None = None
    published_at: datetime | None = None


class CreateVendorPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    slug: str
    description: str | None = None
    status: str = "draft"
    published_at: datetime | None = None


class UpdateVendorPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    status: str | None = None
    published_at: datetime | None = None


class AssignRolePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    role: str


class GrantPermissionPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    permission: str


class UpdateOrderStatusPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: Literal["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
