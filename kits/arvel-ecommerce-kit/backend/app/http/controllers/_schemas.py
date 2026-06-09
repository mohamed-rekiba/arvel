"""Pydantic request-body schemas shared across controllers."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

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


class ShippingAddress(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=200)]
    street: Annotated[str, Field(min_length=1, max_length=200)]
    city: Annotated[str, Field(min_length=1, max_length=120)]
    country: Annotated[str, Field(min_length=1, max_length=120)]


class CheckoutPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    shipping_address: ShippingAddress


class CreateProductPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: dict[str, str]
    slug: dict[str, str] = {}
    description: dict[str, str] = {}
    price: Annotated[float, Field(ge=0)]
    stock_qty: Annotated[int, Field(ge=0)] = 0
    category_id: str
    vendor_id: str = ""


class UpdateProductPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: dict[str, str] | None = None
    slug: dict[str, str] | None = None
    description: dict[str, str] | None = None
    price: Annotated[float, Field(ge=0)] | None = None
    stock_qty: Annotated[int, Field(ge=0)] | None = None
    category_id: str | None = None
    vendor_id: str | None = None


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
