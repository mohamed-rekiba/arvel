<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import ProductCard from '@/components/storefront/ProductCard.vue'
import {
  apiCategoriesShowApiCategoriesSlugGet,
  apiProductsIndexApiProductsGet,
} from '@/api/storefront/storefront'
import type { ProductCardOut } from '@/api/schemas'
import { routeQuery, toSupportedLocale } from '@/lib/i18n'

const route = useRoute()
const { locale, t } = useI18n({ useScope: 'global' })

const searchTerm = ref('')
const loading = ref(false)
const products = ref<ProductCardOut[]>([])
const hasMore = ref(false)
const cursor = ref('')

const currentLocale = computed(() => toSupportedLocale(locale.value))
const categorySlug = computed(() => routeQuery(route.query.category))

async function load(resetCursor = true): Promise<void> {
  loading.value = true
  if (resetCursor) {
    cursor.value = ''
    products.value = []
  }
  try {
    if (categorySlug.value) {
      const result = await apiCategoriesShowApiCategoriesSlugGet(categorySlug.value, {
        locale: currentLocale.value,
        limit: 24,
        cursor: cursor.value || undefined,
      })
      products.value = resetCursor ? result.data : [...products.value, ...result.data]
      hasMore.value = result.pagination.has_more ?? false
      cursor.value = result.pagination.next_cursor ?? ''
    } else {
      const result = await apiProductsIndexApiProductsGet({
        locale: currentLocale.value,
        limit: 24,
        cursor: cursor.value || undefined,
      })
      products.value = resetCursor ? result.data : [...products.value, ...result.data]
      hasMore.value = result.pagination.has_more ?? false
      cursor.value = result.pagination.next_cursor ?? ''
    }
  } finally {
    loading.value = false
  }
}

watch([categorySlug, currentLocale], () => load(), { immediate: true })

const filtered = computed(() => {
  const q = searchTerm.value.trim().toLowerCase()
  if (!q) return products.value
  return products.value.filter((p) => p.name.toLowerCase().includes(q))
})
</script>

<template>
  <div class="mx-auto max-w-7xl px-4 py-10 lg:px-8">
    <div class="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 class="text-3xl font-bold text-fg">
          {{
            categorySlug ? t('products.category', 'Category') : t('products.all', 'All Products')
          }}
        </h1>
        <p v-if="!loading" class="mt-1 text-fg-muted">{{ filtered.length }} items</p>
      </div>
      <input
        v-model="searchTerm"
        type="search"
        placeholder="Filter products…"
        class="w-full max-w-xs rounded-lg border border-border px-4 py-2 text-sm outline-none focus:border-brand sm:w-64"
      />
    </div>

    <div v-if="loading && products.length === 0" class="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <div
        v-for="i in 8"
        :key="i"
        class="aspect-square animate-pulse rounded-xl bg-app-bg-sunken"
      />
    </div>
    <div v-else-if="!loading && filtered.length === 0" class="py-20 text-center text-fg-faint">
      No products found
    </div>
    <div v-else class="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <ProductCard v-for="product in filtered" :key="product.id" :product="product" />
    </div>

    <div v-if="hasMore && !loading" class="mt-10 text-center">
      <button
        type="button"
        class="rounded-lg border border-border px-6 py-2.5 text-sm font-medium text-fg transition hover:bg-app-bg-raised"
        @click="load(false)"
      >
        Load more
      </button>
    </div>
  </div>
</template>
