<!-- generated-from: specs/product-card.md -->
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'
import SalesBadge from '@/components/storefront/SalesBadge.vue'
import WishlistButton from '@/components/storefront/WishlistButton.vue'
import { formatCurrency, toSupportedLocale } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { useCartStore } from '@/stores/cart'
import type { ProductCardOut } from '@/api/schemas'

const props = defineProps<{
  product: ProductCardOut
}>()

const { locale, t } = useI18n({ useScope: 'global' })
const auth = useAuthStore()
const cart = useCartStore()
const router = useRouter()

const currentLocale = computed(() => toSupportedLocale(locale.value))

const productImage = computed(() => props.product.thumbnail_url ?? '')
const originalPrice = computed(() => props.product.original_price ?? null)
const isDiscounted = computed(
  () => originalPrice.value != null && originalPrice.value > props.product.price,
)
const discountPct = computed(() => {
  if (!isDiscounted.value || originalPrice.value == null) return null
  return Math.round((1 - props.product.price / originalPrice.value) * 100)
})
const isOutOfStock = computed(() => (props.product.stock ?? 0) === 0)

const rating = computed(() => props.product.rating)
const ratingCount = computed(() => props.product.rating_count)
const hasRating = computed(() => rating.value != null)

const fullStars = computed(() => Math.floor(rating.value ?? 0))
const hasHalfStar = computed(() => (rating.value ?? 0) - fullStars.value >= 0.5)

async function handleAddToCart(event: Event): Promise<void> {
  event.preventDefault()
  event.stopPropagation()
  if (!auth.isAuthenticated) {
    await router.push({ name: 'login' })
    return
  }
  await cart.addItem(props.product.id)
}
</script>

<template>
  <article
    class="group relative flex flex-col rounded-xl border border-border bg-app-bg shadow-2xs transition duration-300 ease-[cubic-bezier(0.2,0,0,1)] hover:-translate-y-1 hover:border-primary-300 hover:shadow-lg"
  >
    <RouterLink :to="`/products/${product.slug}`" class="block">
      <!-- Image area -->
      <div class="relative aspect-square overflow-hidden rounded-t-xl bg-app-bg-sunken">
        <img
          v-if="productImage"
          :src="productImage"
          :srcset="product.image_srcset || undefined"
          :alt="product.name"
          class="h-full w-full object-cover transition duration-300 group-hover:scale-[1.06]"
        />
        <div
          v-else
          class="flex h-full w-full items-center justify-center bg-app-bg-sunken text-5xl"
        >
          🖥️
        </div>

        <!-- Discount badge -->
        <SalesBadge v-if="discountPct" class="absolute start-3 top-3" :discount="discountPct" />

        <!-- Out of stock overlay -->
        <div
          v-if="isOutOfStock"
          class="absolute inset-0 flex items-center justify-center bg-black/40"
        >
          <span
            class="rounded-full bg-white px-3 py-1 text-xs font-bold uppercase tracking-wide text-fg"
          >
            {{ t('product.out_of_stock', 'Out of Stock') }}
          </span>
        </div>

        <WishlistButton
          :product-id="product.id"
          class="absolute end-3 top-3 opacity-0 group-hover:opacity-100"
        />
      </div>

      <!-- Info -->
      <div class="p-3">
        <h3 class="line-clamp-2 text-sm font-medium text-fg leading-snug">
          {{ product.name }}
        </h3>

        <!-- Star rating — only when the backend reports real review data -->
        <div v-if="hasRating" class="mt-1.5 flex items-center gap-1">
          <div class="flex text-sm text-rating-star">
            <span v-for="i in fullStars" :key="`full-${i}`">★</span>
            <span v-if="hasHalfStar">½</span>
            <span
              v-for="i in 5 - fullStars - (hasHalfStar ? 1 : 0)"
              :key="`empty-${i}`"
              class="text-rating-empty"
              >★</span
            >
          </div>
          <span v-if="ratingCount != null" class="text-xs text-fg-muted">({{ ratingCount }})</span>
        </div>

        <!-- Price row -->
        <div class="mt-2 flex items-baseline gap-2">
          <span
            class="text-base font-extrabold"
            :class="isDiscounted ? 'text-price-sale' : 'text-fg'"
          >
            {{ formatCurrency(product.price, currentLocale) }}
          </span>
          <span v-if="isDiscounted && originalPrice" class="text-xs text-fg-muted line-through">
            {{ formatCurrency(originalPrice, currentLocale) }}
          </span>
        </div>
      </div>
    </RouterLink>

    <!-- Add to Cart — always visible -->
    <div class="mt-auto px-3 pb-3">
      <button
        type="button"
        class="w-full rounded-lg py-2 text-sm font-bold transition duration-200 active:scale-[0.98]"
        :class="
          isOutOfStock
            ? 'cursor-not-allowed bg-app-bg-sunken text-fg-faint'
            : 'bg-cart-cta text-white hover:bg-cart-cta-hover'
        "
        :disabled="isOutOfStock"
        @click="handleAddToCart"
      >
        {{
          isOutOfStock
            ? t('product.out_of_stock', 'Out of Stock')
            : t('product.add_to_cart', 'Add to Cart')
        }}
      </button>
    </div>
  </article>
</template>
