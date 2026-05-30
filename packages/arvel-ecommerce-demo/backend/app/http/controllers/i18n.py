"""i18n catalogue controller."""

from __future__ import annotations

import hashlib
import json as _json

from arvel.http import Request
from arvel.http.controller import Controller
from starlette.responses import Response

_CATALOGUES: dict[str, dict[str, str]] = {
    "en": {
        "nav.home": "Home",
        "nav.products": "Products",
        "nav.cart": "Cart",
        "nav.orders": "Orders",
        "nav.dashboard": "Dashboard",
        "nav.customers": "Customers",
        "nav.categories": "Categories",
        "nav.vendors": "Vendors",
        "nav.analytics": "Analytics",
        "nav.settings": "Settings",
        "auth.logout": "Sign out",
        "common.view_all": "View all",
        "flash_sale.ends_in": "Ends in {hh}:{mm}:{ss}",
        "flash_sale.expired": "Sale ended",
        "product.add_to_cart": "Add to Cart",
        "product.out_of_stock": "Out of Stock",
        "product.price": "Price",
        "checkout.title": "Checkout",
        "checkout.place_order": "Place Order",
        "order.status.pending": "Pending",
        "order.status.processing": "Processing",
        "order.status.shipped": "Shipped",
        "order.status.delivered": "Delivered",
        "order.status.cancelled": "Cancelled",
        "dashboard.recent_orders": "Recent Orders",
        "dashboard.view_all_orders": "View all orders",
        "order.id": "Order ID",
        "order.customer": "Customer",
        "order.date": "Date",
        "order.total": "Total",
        "error.not_found": "Not found",
        "error.unauthorized": "Unauthorized",
    },
    "ar": {
        "nav.home": "الرئيسية",
        "nav.products": "المنتجات",
        "nav.cart": "السلة",
        "nav.orders": "الطلبات",
        "nav.dashboard": "لوحة التحكم",
        "nav.customers": "العملاء",
        "nav.categories": "الفئات",
        "nav.vendors": "البائعون",
        "nav.analytics": "التحليلات",
        "nav.settings": "الإعدادات",
        "auth.logout": "تسجيل الخروج",
        "common.view_all": "عرض الكل",
        "flash_sale.ends_in": "ينتهي خلال {hh}:{mm}:{ss}",
        "flash_sale.expired": "انتهى العرض",
        "product.add_to_cart": "أضف إلى السلة",
        "product.out_of_stock": "نفذت الكمية",
        "product.price": "السعر",
        "checkout.title": "الدفع",
        "checkout.place_order": "تأكيد الطلب",
        "order.status.pending": "قيد الانتظار",
        "order.status.processing": "قيد المعالجة",
        "order.status.shipped": "تم الشحن",
        "order.status.delivered": "تم التسليم",
        "order.status.cancelled": "ملغي",
        "dashboard.recent_orders": "الطلبات الأخيرة",
        "dashboard.view_all_orders": "عرض كل الطلبات",
        "order.id": "رقم الطلب",
        "order.customer": "العميل",
        "order.date": "التاريخ",
        "order.total": "الإجمالي",
        "error.not_found": "غير موجود",
        "error.unauthorized": "غير مصرح",
    },
    "tr": {
        "nav.home": "Ana Sayfa",
        "nav.products": "Ürünler",
        "nav.cart": "Sepet",
        "nav.orders": "Siparişler",
        "nav.dashboard": "Kontrol Paneli",
        "nav.customers": "Müşteriler",
        "nav.categories": "Kategoriler",
        "nav.vendors": "Satıcılar",
        "nav.analytics": "Analitik",
        "nav.settings": "Ayarlar",
        "auth.logout": "Çıkış Yap",
        "common.view_all": "Tümünü gör",
        "flash_sale.ends_in": "{hh}:{mm}:{ss} içinde bitiyor",
        "flash_sale.expired": "Kampanya sona erdi",
        "product.add_to_cart": "Sepete Ekle",
        "product.out_of_stock": "Stokta Yok",
        "product.price": "Fiyat",
        "checkout.title": "Ödeme",
        "checkout.place_order": "Sipariş Ver",
        "order.status.pending": "Beklemede",
        "order.status.processing": "İşleniyor",
        "order.status.shipped": "Kargoya Verildi",
        "order.status.delivered": "Teslim Edildi",
        "order.status.cancelled": "İptal Edildi",
        "dashboard.recent_orders": "Son Siparişler",
        "dashboard.view_all_orders": "Tüm siparişleri gör",
        "order.id": "Sipariş No",
        "order.customer": "Müşteri",
        "order.date": "Tarih",
        "order.total": "Toplam",
        "error.not_found": "Bulunamadı",
        "error.unauthorized": "Yetkisiz",
    },
}


class I18nController(Controller):
    async def catalogue(self, locale: str, request: Request) -> Response:
        data = _CATALOGUES.get(locale, _CATALOGUES["en"])
        body = _json.dumps(data, ensure_ascii=False)
        etag = f'"{hashlib.md5(body.encode(), usedforsecurity=False).hexdigest()}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return Response(
            content=body,
            media_type="application/json",
            headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
        )
