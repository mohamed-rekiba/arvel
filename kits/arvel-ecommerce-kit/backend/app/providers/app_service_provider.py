"""AppServiceProvider — e-commerce kit application wiring."""

from __future__ import annotations

from arvel.providers.service_provider import ServiceProvider

from app.models.category import Category
from app.models.product import Product
from app.models.vendor import Vendor
from app.observers.product_observer import ProductObserver
from app.observers.products_catalog_refresh_observer import ProductsCatalogRefreshObserver


class AppServiceProvider(ServiceProvider):
    """Minimal provider for the e-commerce kit.

    Framework providers handle auth, mail, events, queue, storage,
    cache, and images. This provider is the extension point for
    kit-specific bindings.

    """

    def register(self) -> None:
        # Bind the kit's AuthController subclass so the DI container can
        # resolve it from routes. AuthServiceProvider already wired the
        # services; we just need to construct the subclass instance.
        import config.auth as auth_cfg  # noqa: PLC0415
        from arvel.auth.auth_service import AuthService  # noqa: PLC0415
        from arvel.auth.email_verification_service import EmailVerificationService  # noqa: PLC0415
        from arvel.auth.http.controller import CookieConfig  # noqa: PLC0415
        from arvel.auth.password_service import PasswordService  # noqa: PLC0415

        from app.http.controllers.auth import EcommerceAuthController  # noqa: PLC0415
        from app.http.resources.auth_resources import EcommerceUserResource  # noqa: PLC0415

        refresh = auth_cfg.refresh
        cookies = CookieConfig(
            refresh_cookie=str(refresh["cookie_name"]),
            csrf_cookie=str(refresh["csrf_cookie_name"]),
            refresh_ttl_seconds=int(refresh["ttl_seconds"]),  # type: ignore[arg-type]
            secure=bool(refresh["cookie_secure"]),
            user_resource_class=EcommerceUserResource,
        )
        ec = EcommerceAuthController(
            auth=self.container.make(AuthService),
            passwords=self.container.make(PasswordService),
            email_verification=self.container.make(EmailVerificationService),
            cookies=cookies,
        )
        self.container.instance(EcommerceAuthController, ec)

    async def boot(self) -> None:
        from arvel.auth.events import Registered  # noqa: PLC0415
        from arvel.events.dispatcher import EventDispatcher  # noqa: PLC0415

        from app.listeners.assign_customer_role import AssignCustomerRole  # noqa: PLC0415

        Product.observe(ProductObserver)

        # Refresh the products_catalog view after any change to the three
        # models that feed the materialized view.
        for model in (Product, Category, Vendor):
            model.observe(ProductsCatalogRefreshObserver)

        # Append (not replace) — AuthServiceProvider boots first and registers
        # SendVerificationEmail for Registered; this provider boots last, so both
        # listeners fire. Gives self-registered users the baseline customer role.
        if self.container.bound(EventDispatcher):
            self.container.make(EventDispatcher).listen(Registered, AssignCustomerRole)
