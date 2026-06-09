<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import ProductCard from '@/components/storefront/ProductCard.vue'
import { useStorefrontSearchApiSearchGet } from '@/api/storefront/storefront'
import { routeQuery, toSupportedLocale } from '@/lib/i18n'

const route = useRoute()
const { locale, t } = useI18n({ useScope: 'global' })

// Backend rejects queries shorter than this; don't fire a request that 400s.
const MIN_QUERY_LENGTH = 2

const currentLocale = computed(() => toSupportedLocale(locale.value))
const query = computed(() => routeQuery(route.query.q))
const canSearch = computed(() => query.value.trim().length >= MIN_QUERY_LENGTH)

const { data, isPending } = useStorefrontSearchApiSearchGet(
  computed(() => ({ q: query.value, locale: currentLocale.value })),
  { query: { enabled: canSearch } },
)
const products = computed(() => data.value?.data ?? [])
</script>

<template>
  <div class="mx-auto max-w-7xl px-4 py-10 lg:px-8">
    <h1 class="text-3xl font-bold text-fg">
      {{ t('search.results', 'Search Results') }}
    </h1>
    <p v-if="canSearch" class="mt-2 text-fg-muted">
      {{ t('search.count', { n: products.length, q: query }) }}
    </p>

    <div v-if="isPending" class="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <div
        v-for="i in 4"
        :key="i"
        class="aspect-square animate-pulse rounded-xl bg-app-bg-sunken"
      />
    </div>
    <div v-else-if="!canSearch" class="mt-16 text-center text-fg-faint">
      {{ t('search.prompt', 'Enter a search term above') }}
    </div>
    <div v-else-if="products.length === 0" class="mt-16 text-center text-fg-faint">
      {{ t('search.none', 'No products match your search') }}
    </div>
    <div v-else class="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <ProductCard v-for="product in products" :key="product.id" :product="product" />
    </div>
  </div>
</template>
