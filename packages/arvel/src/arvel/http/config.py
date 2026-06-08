"""HTTP-layer configuration (general request path)."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import NoDecode

from arvel.config.no_prefix import NoPrefix
from arvel.config.settings import ArvelSettings


class HttpConfig(ArvelSettings):
    """Settings for the general HTTP request path.

    - ``TRUSTED_PROXIES`` (CSV): IPs/CIDRs of reverse proxies whose
      ``X-Forwarded-*`` headers are honored. ``*`` trusts every peer (only safe
      when the LB is the sole ingress and the app port is firewalled). Empty
      (default) means forwarded headers are ignored — the TCP peer is the client.
    """

    __config_path__ = "http"

    # NoDecode so pydantic doesn't JSON-decode the env string before our CSV split.
    trusted_proxies: Annotated[list[str], NoPrefix, NoDecode] = Field(default_factory=list)

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


__all__ = ["HttpConfig"]
