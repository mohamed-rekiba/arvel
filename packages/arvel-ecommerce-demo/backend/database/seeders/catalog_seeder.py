"""Seed electronics catalog: vendor, categories, products, and media.

Creates enough data to populate the marketplace-style storefront:
- 1 vendor  (TechWorld)
- 8 categories:
    Level 1: Electronics
    Level 2: Mobiles, Laptops, Speakers, TV Sets, Watches, Headsets
    Level 3: Smartphones  (child of Mobiles — exercises the recursive CTE)
- 12 published products (Mobiles/Smartphones share their 2 products)
- 1 media row per product using picsum for demo images
  (stored via custom_properties.image_url — no file downloads required)

All translatable fields include en/ar/tr values so i18n tests pass.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.support.seeder import EcommerceSeeder


def _english_slug(slug: dict[str, str]) -> str:
    return slug["en"]


class CatalogSeeder(EcommerceSeeder):
    async def run(self) -> None:
        vendors = await self._seed_vendors()
        categories = await self._seed_categories()
        await self._seed_products(vendors, categories)

    async def _seed_vendors(self) -> dict[str, str]:
        rows: list[dict[str, Any]] = [
            {
                "id": self.uuid(),
                "name": "TechWorld",
                "slug": "techworld",
                "description": "Premium electronics and accessories.",
                "status": "published",
                "published_at": self.now(),
            },
        ]
        result: dict[str, str] = {}
        for row in rows:
            record = await self.db.upsert(
                "vendors",
                match_on=["slug"],
                data=row,
                cast_map={"id": "uuid", "status": "vendors_status"},
            )
            if record:
                result[str(row["slug"])] = str(record["id"])
        return result

    async def _seed_categories(self) -> dict[str, str]:
        result: dict[str, str] = {}

        # ── Level 1: root ─────────────────────────────────────────────────────
        for row in [
            {
                "id": self.uuid(),
                "name": {"en": "Electronics", "ar": "إلكترونيات", "tr": "Elektronik"},
                "slug": {"en": "electronics", "ar": "electronics", "tr": "electronics"},
                "status": "published",
                "published_at": self.now(),
                "parent_id": None,
            },
        ]:
            record = await self.db.upsert(
                "categories",
                match_on=["(slug->>'en')"],
                data=row,
                cast_map={"id": "uuid", "status": "categories_status"},
            )
            if record:
                result[_english_slug(row["slug"])] = str(record["id"])

        # ── Level 2: direct children of Electronics ───────────────────────────
        for row in [
            {
                "id": self.uuid(),
                "name": {"en": "Mobiles", "ar": "الهواتف", "tr": "Telefonlar"},
                "slug": {"en": "mobiles", "ar": "mobiles", "tr": "mobiles"},
                "status": "published",
                "published_at": self.now(),
                "parent_id": result["electronics"],
            },
            {
                "id": self.uuid(),
                "name": {"en": "Laptops", "ar": "اللابتوب", "tr": "Dizüstü"},
                "slug": {"en": "laptops", "ar": "laptops", "tr": "laptops"},
                "status": "published",
                "published_at": self.now(),
                "parent_id": result["electronics"],
            },
            {
                "id": self.uuid(),
                "name": {"en": "Speakers", "ar": "السماعات", "tr": "Hoparlörler"},
                "slug": {"en": "speakers", "ar": "speakers", "tr": "speakers"},
                "status": "published",
                "published_at": self.now(),
                "parent_id": result["electronics"],
            },
            {
                "id": self.uuid(),
                "name": {"en": "TV Sets", "ar": "التلفزيونات", "tr": "Televizyonlar"},
                "slug": {"en": "tv-sets", "ar": "tv-sets", "tr": "tv-sets"},
                "status": "published",
                "published_at": self.now(),
                "parent_id": result["electronics"],
            },
            {
                "id": self.uuid(),
                "name": {"en": "Watches", "ar": "الساعات", "tr": "Saatler"},
                "slug": {"en": "watches", "ar": "watches", "tr": "watches"},
                "status": "published",
                "published_at": self.now(),
                "parent_id": result["electronics"],
            },
            {
                "id": self.uuid(),
                "name": {"en": "Headsets", "ar": "سماعات الرأس", "tr": "Kulaklıklar"},
                "slug": {"en": "headsets", "ar": "headsets", "tr": "headsets"},
                "status": "published",
                "published_at": self.now(),
                "parent_id": result["electronics"],
            },
        ]:
            record = await self.db.upsert(
                "categories",
                match_on=["(slug->>'en')"],
                data=row,
                cast_map={"id": "uuid", "parent_id": "uuid", "status": "categories_status"},
            )
            if record:
                result[_english_slug(row["slug"])] = str(record["id"])

        # ── Level 3: grandchildren (exercises the recursive ancestor CTE) ─────
        for row in [
            {
                "id": self.uuid(),
                "name": {"en": "Smartphones", "ar": "الهواتف الذكية", "tr": "Akıllı Telefonlar"},
                "slug": {"en": "smartphones", "ar": "smartphones", "tr": "smartphones"},
                "status": "published",
                "published_at": self.now(),
                "parent_id": result["mobiles"],
            },
        ]:
            record = await self.db.upsert(
                "categories",
                match_on=["(slug->>'en')"],
                data=row,
                cast_map={"id": "uuid", "parent_id": "uuid", "status": "categories_status"},
            )
            if record:
                result[_english_slug(row["slug"])] = str(record["id"])

        return result

    async def _seed_products(
        self,
        vendors: dict[str, str],
        categories: dict[str, str],
    ) -> None:
        products: list[dict[str, Any]] = [
            # ── Smartphones (Electronics > Mobiles > Smartphones) ────────────────
            # These are 3 levels deep — the recursive CTE must clear all 3 ancestors.
            {
                "id": self.uuid(),
                "name": {
                    "en": "iPhone 15 Pro",
                    "ar": "آيفون 15 برو",
                    "tr": "iPhone 15 Pro",
                },
                "slug": {
                    "en": "iphone-15-pro",
                    "ar": "iphone-15-pro",
                    "tr": "iphone-15-pro",
                },
                "description": {
                    "en": "Apple's flagship with A17 Pro chip, titanium design, and ProRes video.",
                    "ar": "الهاتف الرائد من آبل بمعالج A17 Pro وتصميم تيتانيوم وفيديو ProRes.",
                    "tr": "A17 Pro çip, titanyum tasarım ve ProRes video ile Apple'ın amiral gemisi.",
                },
                "price": "999.00",
                "stock_qty": 30,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["smartphones"],
                "vendor_id": vendors["techworld"],
            },
            {
                "id": self.uuid(),
                "name": {
                    "en": "Samsung Galaxy S25",
                    "ar": "سامسونج جالكسي S25",
                    "tr": "Samsung Galaxy S25",
                },
                "slug": {
                    "en": "samsung-galaxy-s25",
                    "ar": "samsung-galaxy-s25",
                    "tr": "samsung-galaxy-s25",
                },
                "description": {
                    "en": "Android flagship with Snapdragon 8 Elite, 200MP camera, and 7-year updates.",
                    "ar": "هاتف آندرويد الرائد بمعالج سناب دراجون Elite وكاميرا 200 ميجابكسل.",
                    "tr": "Snapdragon 8 Elite, 200MP kamera ve 7 yıl güncelleme garantili Android amiral gemisi.",
                },
                "price": "849.00",
                "stock_qty": 45,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["smartphones"],
                "vendor_id": vendors["techworld"],
            },
            # ── Laptops ──────────────────────────────────────────────────────────
            {
                "id": self.uuid(),
                "name": {
                    "en": "MacBook Air M4",
                    "ar": "ماك بوك إير M4",
                    "tr": "MacBook Air M4",
                },
                "slug": {
                    "en": "macbook-air-m4",
                    "ar": "macbook-air-m4",
                    "tr": "macbook-air-m4",
                },
                "description": {
                    "en": "Impossibly thin with M4 chip, 18-hour battery, and Liquid Retina display.",
                    "ar": "نحيف بشكل لافت مع معالج M4 وبطارية 18 ساعة وشاشة ليكويد ريتينا.",
                    "tr": "M4 çip, 18 saat pil ve Liquid Retina ekranla inanılmaz ince tasarım.",
                },
                "price": "1299.00",
                "stock_qty": 20,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["laptops"],
                "vendor_id": vendors["techworld"],
            },
            {
                "id": self.uuid(),
                "name": {
                    "en": "Dell XPS 15",
                    "ar": "ديل XPS 15",
                    "tr": "Dell XPS 15",
                },
                "slug": {
                    "en": "dell-xps-15",
                    "ar": "dell-xps-15",
                    "tr": "dell-xps-15",
                },
                "description": {
                    "en": '15.6" OLED display, Intel Core Ultra 9, RTX 4070 — powerhouse for creators.',
                    "ar": "شاشة OLED 15.6 إنش ومعالج Intel Core Ultra 9 وكارت RTX 4070.",
                    "tr": '15.6" OLED ekran, Intel Core Ultra 9, RTX 4070 — yaratıcılar için güç merkezi.',
                },
                "price": "1099.00",
                "stock_qty": 15,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["laptops"],
                "vendor_id": vendors["techworld"],
            },
            # ── Speakers ─────────────────────────────────────────────────────────
            {
                "id": self.uuid(),
                "name": {
                    "en": "Sony SRS-XB100",
                    "ar": "سوني SRS-XB100",
                    "tr": "Sony SRS-XB100",
                },
                "slug": {
                    "en": "sony-srs-xb100",
                    "ar": "sony-srs-xb100",
                    "tr": "sony-srs-xb100",
                },
                "description": {
                    "en": "Compact Bluetooth speaker with EXTRA BASS, IP67 waterproof, 16h battery.",
                    "ar": "سماعة بلوتوث مضغوطة بباص إضافي ومقاومة ماء IP67 وبطارية 16 ساعة.",
                    "tr": "EXTRA BASS, IP67 su geçirmez ve 16 saat pilli kompakt Bluetooth hoparlör.",
                },
                "price": "59.99",
                "stock_qty": 100,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["speakers"],
                "vendor_id": vendors["techworld"],
            },
            {
                "id": self.uuid(),
                "name": {
                    "en": "Bose SoundLink Flex",
                    "ar": "بوز ساوند لينك فليكس",
                    "tr": "Bose SoundLink Flex",
                },
                "slug": {
                    "en": "bose-soundlink-flex",
                    "ar": "bose-soundlink-flex",
                    "tr": "bose-soundlink-flex",
                },
                "description": {
                    "en": "Premium portable speaker with PositionIQ, IP67 waterproof, 12h playback.",
                    "ar": "سماعة محمولة فاخرة بتقنية PositionIQ ومقاومة ماء IP67.",
                    "tr": "PositionIQ, IP67 su geçirmez ve 12 saat çalma süreli premium taşınabilir hoparlör.",
                },
                "price": "149.99",
                "stock_qty": 60,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["speakers"],
                "vendor_id": vendors["techworld"],
            },
            # ── TV Sets ───────────────────────────────────────────────────────────
            {
                "id": self.uuid(),
                "name": {
                    "en": 'Samsung 55" QLED 4K',
                    "ar": "سامسونج 55 إنش QLED 4K",
                    "tr": 'Samsung 55" QLED 4K',
                },
                "slug": {
                    "en": "samsung-55-qled-4k",
                    "ar": "samsung-55-qled-4k",
                    "tr": "samsung-55-qled-4k",
                },
                "description": {
                    "en": "Quantum HDR, 120Hz refresh rate, built-in Tizen OS, and Object Tracking Sound.",
                    "ar": "Quantum HDR ومعدل تحديث 120Hz ونظام Tizen المدمج وصوت Object Tracking.",
                    "tr": "Quantum HDR, 120Hz yenileme hızı, dahili Tizen OS ve Object Tracking Sound.",
                },
                "price": "799.00",
                "stock_qty": 25,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["tv-sets"],
                "vendor_id": vendors["techworld"],
            },
            {
                "id": self.uuid(),
                "name": {
                    "en": 'LG 65" OLED evo C4',
                    "ar": "إل جي 65 إنش OLED evo C4",
                    "tr": 'LG 65" OLED evo C4',
                },
                "slug": {
                    "en": "lg-65-oled-evo-c4",
                    "ar": "lg-65-oled-evo-c4",
                    "tr": "lg-65-oled-evo-c4",
                },
                "description": {
                    "en": "Self-lit OLED pixels, α9 AI Processor Gen7, Dolby Vision IQ, NVIDIA G-Sync.",
                    "ar": "بكسل OLED ذاتية الإضاءة ومعالج α9 AI Gen7 و Dolby Vision IQ.",
                    "tr": "Kendi kendine aydınlatan OLED piksellar, α9 AI İşlemci Gen7, Dolby Vision IQ.",
                },
                "price": "1499.00",
                "stock_qty": 10,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["tv-sets"],
                "vendor_id": vendors["techworld"],
            },
            # ── Watches ───────────────────────────────────────────────────────────
            {
                "id": self.uuid(),
                "name": {
                    "en": "Apple Watch Series 10",
                    "ar": "آبل ووتش السلسلة 10",
                    "tr": "Apple Watch Series 10",
                },
                "slug": {
                    "en": "apple-watch-series-10",
                    "ar": "apple-watch-series-10",
                    "tr": "apple-watch-series-10",
                },
                "description": {
                    "en": "Thinnest Apple Watch ever — ECG, sleep apnea detection, 18h battery.",
                    "ar": "أنحف ساعة آبل على الإطلاق — ECG وكشف توقف التنفس وبطارية 18 ساعة.",
                    "tr": "Şimdiye kadarki en ince Apple Watch — EKG, uyku apnesi tespiti, 18 saat pil.",
                },
                "price": "399.00",
                "stock_qty": 35,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["watches"],
                "vendor_id": vendors["techworld"],
            },
            {
                "id": self.uuid(),
                "name": {
                    "en": "Garmin Forerunner 965",
                    "ar": "جارمن فورران 965",
                    "tr": "Garmin Forerunner 965",
                },
                "slug": {
                    "en": "garmin-forerunner-965",
                    "ar": "garmin-forerunner-965",
                    "tr": "garmin-forerunner-965",
                },
                "description": {
                    "en": "Premium GPS running watch with AMOLED display, advanced training metrics, 23-day battery.",
                    "ar": "ساعة جري GPS فاخرة بشاشة AMOLED وبيانات تدريب متقدمة وبطارية 23 يوماً.",
                    "tr": "AMOLED ekran, gelişmiş antrenman metrikleri ve 23 günlük pille premium GPS koşu saati.",
                },
                "price": "599.00",
                "stock_qty": 20,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["watches"],
                "vendor_id": vendors["techworld"],
            },
            # ── Headsets ──────────────────────────────────────────────────────────
            {
                "id": self.uuid(),
                "name": {
                    "en": "Sony WH-1000XM6",
                    "ar": "سوني WH-1000XM6",
                    "tr": "Sony WH-1000XM6",
                },
                "slug": {
                    "en": "sony-wh-1000xm6",
                    "ar": "sony-wh-1000xm6",
                    "tr": "sony-wh-1000xm6",
                },
                "description": {
                    "en": "Industry-leading ANC, 40h battery, multipoint Bluetooth, foldable design.",
                    "ar": "خاصية إلغاء الضوضاء الرائدة وبطارية 40 ساعة ووصل متعدد النقاط.",
                    "tr": "Sektör lideri ANC, 40 saat pil, çok noktalı Bluetooth ve katlanabilir tasarım.",
                },
                "price": "349.00",
                "stock_qty": 40,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["headsets"],
                "vendor_id": vendors["techworld"],
            },
            {
                "id": self.uuid(),
                "name": {
                    "en": "AirPods Pro 3",
                    "ar": "إيربودز برو 3",
                    "tr": "AirPods Pro 3",
                },
                "slug": {
                    "en": "airpods-pro-3",
                    "ar": "airpods-pro-3",
                    "tr": "airpods-pro-3",
                },
                "description": {
                    "en": "H3 chip, Adaptive Audio, Hearing Aid mode, 30h total battery life.",
                    "ar": "شريحة H3 وصوت تكيفي ووضع المساعدة السمعية وبطارية إجمالية 30 ساعة.",
                    "tr": "H3 çip, Adaptive Audio, İşitme Yardımı modu ve toplam 30 saat pil ömrü.",
                },
                "price": "249.00",
                "stock_qty": 55,
                "status": "published",
                "published_at": self.now(),
                "category_id": categories["headsets"],
                "vendor_id": vendors["techworld"],
            },
        ]

        for product in products:
            record = await self.db.upsert(
                "products",
                match_on=["(slug->>'en')"],
                data=product,
                cast_map={
                    "id": "uuid",
                    "category_id": "uuid",
                    "vendor_id": "uuid",
                    "status": "products_status",
                    "price": "numeric",
                },
            )
            if record:
                slug_en = product["slug"]["en"]
                await self._seed_media(str(record["id"]), slug_en)

    async def _seed_media(self, product_id: str, slug: str) -> None:
        """Insert a media row with a picsum URL — skips if one already exists."""
        existing = await self.db.table("media").where("model_id", product_id).first()
        if existing:
            return

        # Deterministic UUID so re-seeding is idempotent via ON CONFLICT(uuid).
        media_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"product-image:{product_id}"))
        await self.db.upsert(
            "media",
            match_on=["uuid"],
            data={
                "model_type": "Product",
                "model_id": product_id,
                "uuid": media_uuid,
                "collection_name": "images",
                "name": slug,
                "file_name": f"{slug}.jpg",
                "mime_type": "image/jpeg",
                "disk": "public",
                "size": 0,
                "manipulations": {},
                "custom_properties": {"image_url": f"https://picsum.photos/seed/{slug}/400/400"},
                "generated_conversions": {},
                "responsive_images": {},
                "metadata": {},
                "order_column": 1,
            },
            cast_map={"uuid": "uuid"},
        )
