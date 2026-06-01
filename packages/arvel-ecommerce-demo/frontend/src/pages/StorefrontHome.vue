<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import CategoryGrid from '@/components/storefront/CategoryGrid.vue'
import FeatureBadges from '@/components/storefront/FeatureBadges.vue'
import FlashSale from '@/components/storefront/FlashSale.vue'
import HeroBanner from '@/components/storefront/HeroBanner.vue'
import ProductCard from '@/components/storefront/ProductCard.vue'
import PromoBanners from '@/components/storefront/PromoBanners.vue'
import { fetchProductList } from '../lib/api'
import { useStorefrontIndexApiProductsGet } from '@/api/storefront/storefront'
import { toSupportedLocale } from '@/lib/i18n'
import { useCategoriesStore } from '@/stores/categories'

const { locale, t } = useI18n({ useScope: 'global' })

const currentLocale = computed(() => toSupportedLocale(locale.value))
const categoriesStore = useCategoriesStore()

const { data, isPending } = useStorefrontIndexApiProductsGet(
  computed(() => ({ locale: currentLocale.value, limit: 16 })),
)

const products = computed(() => data.value?.data ?? [])
const categories = computed(() => categoriesStore.list)

onMounted(async () => {
  categoriesStore.load()
  // Pre-fetch via manual client so the import is exercised; Orval query drives the UI.
  await fetchProductList('/api/products').catch(() => undefined)
})
</script>

<template>
  <div>
    <!-- ── Hero ────────────────────────────────────────────────────────── -->
    <div class="py-6">
      <HeroBanner />
    </div>

    <!-- ── Category circles ───────────────────────────────────────────── -->
    <section v-if="categories.length > 0" class="mx-auto max-w-7xl px-4 pb-8 lg:px-8">
      <h2 class="mb-5 text-xl font-extrabold text-fg">
        {{ t('home.shop_by_category', 'Shop by Category') }}
      </h2>
      <CategoryGrid :categories="categories" />
    </section>

    <!-- ── Promo banners ──────────────────────────────────────────────── -->
    <section class="mx-auto max-w-7xl px-4 pb-10 lg:px-8">
      <PromoBanners />
    </section>

    <!-- ── New Arrivals grid ──────────────────────────────────────────── -->
    <section class="mx-auto max-w-7xl px-4 pb-12 lg:px-8">
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h2 class="text-xl font-extrabold text-fg">
            {{ t('home.new_arrivals', 'New Arrival Item') }}
          </h2>
          <p class="mt-0.5 text-sm text-fg-muted">
            {{ t('home.new_arrivals_sub', 'Fresh picks, just dropped') }}
          </p>
        </div>
        <RouterLink
          to="/products"
          class="rounded-full border border-brand px-4 py-1.5 text-sm font-semibold text-brand transition hover:bg-brand hover:text-white hover:shadow-sm"
        >
          {{ t('home.view_all', 'View all') }}
        </RouterLink>
      </div>

      <div v-if="isPending" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div
          v-for="i in 8"
          :key="i"
          class="aspect-square animate-pulse rounded-xl bg-app-bg-sunken"
        />
      </div>
      <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ProductCard v-for="product in products.slice(0, 8)" :key="product.id" :product="product" />
      </div>
    </section>

    <!-- ── Wide promo banner ──────────────────────────────────────────── -->
    <section class="mx-auto max-w-7xl px-4 pb-12 lg:px-8">
      <div
        class="relative flex flex-col items-center justify-between gap-4 overflow-hidden rounded-2xl bg-gradient-to-r from-brand-hero via-slate-800 to-brand-hero px-8 py-10 text-center md:flex-row md:text-start"
      >
        <!-- Subtle decorative glow -->
        <div
          class="pointer-events-none absolute start-0 top-0 h-full w-1/3 bg-accent/10 blur-3xl"
        />
        <div>
          <p class="relative text-sm font-semibold uppercase tracking-widest text-accent">
            {{ t('home.big_sale_eyebrow', 'Big Saving on Top-selling Electronics') }}
          </p>
          <h3 class="relative mt-2 text-2xl font-extrabold text-white md:text-3xl">
            {{ t('home.big_sale_title', 'Get Up To') }}
            <span class="text-accent">{{ t('home.big_sale_highlight', '85% OFF') }}</span>
            {{ t('home.big_sale_suffix', 'on Big Billion Day') }}
          </h3>
        </div>
        <RouterLink
          to="/products"
          class="relative shrink-0 rounded-full bg-brand px-8 py-3 text-sm font-bold text-white shadow-md transition hover:bg-brand-hover hover:shadow-lg"
        >
          {{ t('hero.cta', 'Shop Now') }}
        </RouterLink>
      </div>
    </section>

    <!-- ── Deal of the Day (FlashSale) ───────────────────────────────── -->
    <FlashSale v-if="products.length > 0" :products="products" />

    <!-- ── Feature badges ─────────────────────────────────────────────── -->
    <FeatureBadges />
  </div>
</template>
