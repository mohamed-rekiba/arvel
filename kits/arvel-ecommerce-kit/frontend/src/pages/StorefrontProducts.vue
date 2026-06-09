<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import ProductCard from '@/components/storefront/ProductCard.vue'
import {
  storefrontProductsCatalogApiCategoriesSlugGet,
  storefrontIndexApiProductsGet,
  storefrontSearchApiSearchGet,
} from '@/api/storefront/storefront'
import type { ProductCardOut } from '@/api/schemas'
import { routeQuery, toSupportedLocale } from '@/lib/i18n'

// Backend rejects shorter queries; below this we show the normal paginated list.
const MIN_QUERY_LENGTH = 2
const SEARCH_DEBOUNCE_MS = 300

const route = useRoute()
const { locale, t } = useI18n({ useScope: 'global' })

const searchTerm = ref('')
const loading = ref(false)
const products = ref<ProductCardOut[]>([])
const hasMore = ref(false)
const cursor = ref('')

const searching = ref(false)
const searchResults = ref<ProductCardOut[]>([])

const currentLocale = computed(() => toSupportedLocale(locale.value))
const categorySlug = computed(() => routeQuery(route.query.category))
const activeQuery = computed(() => {
  const q = searchTerm.value.trim()
  return q.length >= MIN_QUERY_LENGTH ? q : ''
})

async function load(resetCursor = true): Promise<void> {
  loading.value = true
  if (resetCursor) {
    cursor.value = ''
    products.value = []
  }
  try {
    if (categorySlug.value) {
      const result = await storefrontProductsCatalogApiCategoriesSlugGet(categorySlug.value, {
        locale: currentLocale.value,
        limit: 24,
        cursor: cursor.value || undefined,
      })
      products.value = resetCursor ? result.data : [...products.value, ...result.data]
      hasMore.value = result.pagination.has_more ?? false
      cursor.value = result.pagination.next_cursor ?? ''
    } else {
      const result = await storefrontIndexApiProductsGet({
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

// Search the whole catalog server-side, not just the page already loaded.
// Debounce keystrokes and drop stale responses so a slow request can't clobber
// a newer one.
let debounceTimer: ReturnType<typeof setTimeout> | undefined
let searchSeq = 0

async function runSearch(query: string, locale: string): Promise<void> {
  const seq = ++searchSeq
  searching.value = true
  try {
    const result = await storefrontSearchApiSearchGet({ q: query, locale, limit: 48 })
    if (seq === searchSeq) searchResults.value = result.data
  } finally {
    if (seq === searchSeq) searching.value = false
  }
}

watch([activeQuery, currentLocale], ([query, locale]) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (!query) {
    searchSeq++ // cancel any in-flight result
    searching.value = false
    searchResults.value = []
    return
  }
  debounceTimer = setTimeout(() => void runSearch(query, locale), SEARCH_DEBOUNCE_MS)
})

const displayed = computed(() => (activeQuery.value ? searchResults.value : products.value))
const showLoadMore = computed(() => !activeQuery.value && hasMore.value && !loading.value)
const showSkeleton = computed(() =>
  activeQuery.value ? searching.value && searchResults.value.length === 0 : loading.value && products.value.length === 0,
)
const showEmpty = computed(() =>
  activeQuery.value ? !searching.value && searchResults.value.length === 0 : !loading.value && products.value.length === 0,
)
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
        <p v-if="!loading" class="mt-1 text-fg-muted">
          {{ t('products.count', { n: displayed.length }) }}
        </p>
      </div>
      <input
        v-model="searchTerm"
        type="search"
        :placeholder="t('products.filter_placeholder', 'Filter products…')"
        class="w-full max-w-xs rounded-lg border border-border px-4 py-2 text-sm outline-none focus:border-brand sm:w-64"
      />
    </div>

    <div v-if="showSkeleton" class="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <div
        v-for="i in 8"
        :key="i"
        class="aspect-square animate-pulse rounded-xl bg-app-bg-sunken"
      />
    </div>
    <div v-else-if="showEmpty" class="py-20 text-center text-fg-faint">
      {{ t('products.none', 'No products found') }}
    </div>
    <div v-else class="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <ProductCard v-for="product in displayed" :key="product.id" :product="product" />
    </div>

    <div v-if="showLoadMore" class="mt-10 text-center">
      <button
        type="button"
        class="rounded-lg border border-border px-6 py-2.5 text-sm font-medium text-fg transition hover:bg-app-bg-raised"
        @click="load(false)"
      >
        {{ t('products.load_more', 'Load more') }}
      </button>
    </div>
  </div>
</template>
