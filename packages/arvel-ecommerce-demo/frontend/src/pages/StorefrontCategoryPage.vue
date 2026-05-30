<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { RouterLink } from 'vue-router'
import ProductCard from '@/components/storefront/ProductCard.vue'
import { apiCategoriesShowApiCategoriesSlugGet } from '@/api/storefront/storefront'
import type { ProductCardOut } from '@/api/schemas'
import { routeParam, toSupportedLocale } from '@/lib/i18n'

const route = useRoute()
const { locale } = useI18n({ useScope: 'global' })

const products = ref<ProductCardOut[]>([])
const loading = ref(true)
const hasMore = ref(false)
const cursor = ref('')

const currentLocale = computed(() => toSupportedLocale(locale.value))
const slug = computed(() => routeParam(route.params.slug))

// Derive display names from the first product — avoids a separate API call.
const categoryName = computed(() => {
  if (products.value.length > 0)
    return products.value[0].category_name ?? slug.value.replace(/-/g, ' ')
  return slug.value.replace(/-/g, ' ')
})

const parentCategoryName = computed(() => products.value[0]?.parent_category_name ?? null)
const parentCategorySlug = computed(() => products.value[0]?.parent_category_slug ?? null)

async function load(resetCursor = true): Promise<void> {
  loading.value = true
  if (resetCursor) cursor.value = ''
  try {
    const result = await apiCategoriesShowApiCategoriesSlugGet(slug.value, {
      locale: currentLocale.value,
      limit: 24,
      cursor: cursor.value || undefined,
    })
    products.value = resetCursor ? result.data : [...products.value, ...result.data]
    hasMore.value = result.pagination.has_more ?? false
    cursor.value = result.pagination.next_cursor ?? ''
  } finally {
    loading.value = false
  }
}

onMounted(() => load())
watch([slug, currentLocale], () => load())
</script>

<template>
  <div class="mx-auto max-w-7xl px-4 py-10 lg:px-8">
    <div class="mb-8">
      <!-- Breadcrumb — only rendered when the category has a parent -->
      <nav v-if="parentCategorySlug" class="mb-2 flex items-center gap-1.5 text-sm text-fg-muted">
        <RouterLink to="/products" class="hover:text-brand">All</RouterLink>
        <span>/</span>
        <RouterLink :to="`/categories/${parentCategorySlug}`" class="capitalize hover:text-brand">
          {{ parentCategoryName }}
        </RouterLink>
        <span>/</span>
        <span class="capitalize text-fg">{{ categoryName }}</span>
      </nav>
      <h1 class="text-3xl font-bold capitalize text-fg">{{ categoryName }}</h1>
      <p v-if="!loading" class="mt-1 text-fg-muted">{{ products.length }} products</p>
    </div>

    <div v-if="loading" class="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <div
        v-for="i in 8"
        :key="i"
        class="aspect-square animate-pulse rounded-xl bg-app-bg-sunken"
      />
    </div>

    <div v-else-if="products.length === 0" class="mt-16 text-center text-fg-faint">
      No products in this category yet.
    </div>

    <div v-else class="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <ProductCard v-for="product in products" :key="product.id" :product="product" />
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
