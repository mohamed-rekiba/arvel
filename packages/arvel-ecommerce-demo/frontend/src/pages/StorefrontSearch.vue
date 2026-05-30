<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import ProductCard from '@/components/storefront/ProductCard.vue'
import { useApiSearchApiSearchGet } from '@/api/storefront/storefront'
import { routeQuery, toSupportedLocale } from '@/lib/i18n'

const route = useRoute()
const { locale, t } = useI18n({ useScope: 'global' })

const currentLocale = computed(() => toSupportedLocale(locale.value))
const query = computed(() => routeQuery(route.query.q))

const { data, isPending } = useApiSearchApiSearchGet(
  computed(() => ({ q: query.value, locale: currentLocale.value })),
  { query: { enabled: computed(() => !!query.value.trim()) } },
)
const products = computed(() => data.value?.data ?? [])
</script>

<template>
  <div class="mx-auto max-w-7xl px-4 py-10 lg:px-8">
    <h1 class="text-3xl font-bold text-fg">
      {{ t('search.results', 'Search Results') }}
    </h1>
    <p v-if="query" class="mt-2 text-fg-muted">{{ products.length }} results for "{{ query }}"</p>

    <div v-if="isPending" class="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <div
        v-for="i in 4"
        :key="i"
        class="aspect-square animate-pulse rounded-xl bg-app-bg-sunken"
      />
    </div>
    <div v-else-if="!query" class="mt-16 text-center text-fg-faint">Enter a search term above</div>
    <div v-else-if="products.length === 0" class="mt-16 text-center text-fg-faint">
      No products match your search
    </div>
    <div v-else class="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <ProductCard v-for="product in products" :key="product.id" :product="product" />
    </div>
  </div>
</template>
