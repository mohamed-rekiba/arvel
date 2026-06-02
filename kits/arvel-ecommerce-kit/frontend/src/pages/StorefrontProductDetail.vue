<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ProductRating from '@/components/storefront/ProductRating.vue'
import { fetchProductBySlug } from '../lib/api'
import { useStorefrontShowApiProductsSlugGet } from '@/api/storefront/storefront'
import { formatCurrency, routeParam, toSupportedLocale } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { useCartStore } from '@/stores/cart'
import { useStorefrontStore } from '@/stores/storefront'

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n({ useScope: 'global' })
const auth = useAuthStore()
const cart = useCartStore()
const storefrontStore = useStorefrontStore()

const quantity = ref(1)
const adding = ref(false)

const currentLocale = computed(() => toSupportedLocale(locale.value))
const slug = computed(() => routeParam(route.params.slug))

const { data: productWrapper, isPending } = useStorefrontShowApiProductsSlugGet(
  slug,
  computed(() => ({ locale: currentLocale.value })),
)
const product = computed(() => productWrapper.value?.data ?? null)

watch(
  slug,
  (s) => {
    if (s) void fetchProductBySlug(s).catch(() => undefined)
  },
  { immediate: true },
)
watch(product, (p) => storefrontStore.setCurrentProduct(p?.id ?? null), { immediate: true })
onUnmounted(() => storefrontStore.setCurrentProduct(null))

async function handleAddToCart(): Promise<void> {
  if (!auth.isAuthenticated) {
    await router.push({ name: 'login', query: { redirect: route.fullPath } })
    return
  }
  if (!product.value) return
  adding.value = true
  try {
    await cart.addItem(product.value.id, quantity.value)
  } finally {
    adding.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-7xl px-4 py-10 lg:px-8">
    <div v-if="isPending" class="grid animate-pulse gap-8 lg:grid-cols-2">
      <div class="aspect-square rounded-2xl bg-app-bg-sunken" />
      <div class="space-y-4">
        <div class="h-8 w-2/3 rounded bg-app-bg-sunken" />
        <div class="h-6 w-1/3 rounded bg-app-bg-sunken" />
        <div class="h-24 rounded bg-app-bg-sunken" />
      </div>
    </div>

    <div v-else-if="product" class="grid gap-10 lg:grid-cols-2">
      <div class="aspect-square overflow-hidden rounded-2xl bg-app-bg-sunken">
        <img
          v-if="product.thumbnail_url"
          :src="product.thumbnail_url"
          :srcset="product.image_srcset || undefined"
          :alt="product.name"
          class="h-full w-full object-cover"
        />
        <div v-else class="flex h-full items-center justify-center text-fg-faint">No image</div>
      </div>

      <div>
        <h1 class="text-3xl font-bold text-fg">{{ product.name }}</h1>
        <ProductRating class="mt-3" :rating="4.5" :count="128" />
        <p class="mt-4 text-2xl font-bold text-fg">
          {{ formatCurrency(product.price, currentLocale) }}
        </p>
        <p class="mt-4 text-fg-muted">{{ product.short_description }}</p>
        <p class="mt-2 text-sm" :class="product.stock > 0 ? 'text-stock-in' : 'text-stock-out'">
          {{ product.stock > 0 ? `${product.stock} in stock` : 'Out of stock' }}
        </p>

        <div class="mt-8 flex items-center gap-4">
          <label class="text-sm font-medium text-fg">
            {{ t('product.quantity', 'Qty') }}
            <input
              v-model.number="quantity"
              type="number"
              min="1"
              :max="product.stock"
              class="ms-2 w-20 rounded-lg border border-border px-3 py-2 text-sm"
            />
          </label>
        </div>

        <button
          type="button"
          class="mt-6 w-full rounded-xl bg-cart-cta py-4 text-sm font-semibold text-white transition hover:bg-cart-cta-hover disabled:opacity-50 sm:w-auto sm:px-12"
          :disabled="product.stock === 0 || adding"
          @click="handleAddToCart"
        >
          {{ adding ? t('product.adding', 'Adding…') : t('product.add_to_cart', 'Add to Cart') }}
        </button>
      </div>
    </div>
  </div>
</template>
