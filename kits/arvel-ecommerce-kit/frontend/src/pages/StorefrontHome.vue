<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import CategoryGrid from '@/components/storefront/CategoryGrid.vue'
import FeatureBadges from '@/components/storefront/FeatureBadges.vue'
import HeroBanner from '@/components/storefront/HeroBanner.vue'
import ProductCard from '@/components/storefront/ProductCard.vue'
import PromoBanners from '@/components/storefront/PromoBanners.vue'
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

onMounted(() => {
  categoriesStore.load()
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
      <h2 v-reveal class="mb-5 text-xl font-extrabold text-fg">
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
      <div v-reveal class="mb-6 flex items-center justify-between">
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
          class="rounded-full border border-brand px-4 py-1.5 text-sm font-semibold text-brand transition duration-300 hover:bg-brand hover:text-white hover:shadow-sm"
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
        <ProductCard
          v-for="(product, i) in products.slice(0, 8)"
          :key="product.id"
          v-reveal="(i % 4) * 70"
          :product="product"
        />
      </div>
    </section>

    <!-- ── Wide promo banner ──────────────────────────────────────────── -->
    <section class="mx-auto max-w-7xl px-4 pb-12 lg:px-8">
      <div
        v-reveal
        class="animate-gradient group relative flex flex-col items-center justify-between gap-4 overflow-hidden rounded-2xl bg-gradient-to-r from-primary-950 via-brand-hero to-primary-900 px-8 py-12 text-center md:flex-row md:text-start"
      >
        <!-- Decorative glows -->
        <div
          class="animate-glow pointer-events-none absolute -start-10 top-0 h-full w-1/3 bg-accent/15 blur-3xl"
        />
        <div
          class="animate-glow pointer-events-none absolute -end-10 bottom-0 h-40 w-72 bg-primary-500/25 blur-3xl"
          style="animation-delay: 1.2s"
        />
        <div class="relative">
          <p class="text-sm font-semibold uppercase tracking-widest text-accent">
            {{ t('home.big_sale_eyebrow', 'Top-selling electronics') }}
          </p>
          <h3 class="mt-2 text-2xl font-extrabold text-white md:text-3xl">
            {{ t('home.big_sale_title', 'Gear that keeps up with you') }}
          </h3>
        </div>
        <RouterLink
          to="/products"
          class="relative shrink-0 rounded-full bg-primary-500 px-8 py-3 text-sm font-bold text-white shadow-[0_8px_30px_-8px_oklch(0.591_0.201_294_/_0.8)] transition duration-300 hover:-translate-y-0.5 hover:bg-primary-400 hover:shadow-[0_14px_40px_-8px_oklch(0.591_0.201_294_/_0.95)]"
        >
          {{ t('hero.cta', 'Shop Now') }}
        </RouterLink>
      </div>
    </section>

    <!-- ── Feature badges ─────────────────────────────────────────────── -->
    <FeatureBadges />
  </div>
</template>
