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
const activeIndex = ref(0)
let touchStartX = 0

const currentLocale = computed(() => toSupportedLocale(locale.value))
const slug = computed(() => routeParam(route.params.slug))

const { data: productWrapper, isPending } = useStorefrontShowApiProductsSlugGet(
  slug,
  computed(() => ({ locale: currentLocale.value })),
)
const product = computed(() => productWrapper.value?.data ?? null)
const images = computed(() => product.value?.images ?? [])
const activeImage = computed(() => images.value[activeIndex.value] ?? null)
const hasMultiple = computed(() => images.value.length > 1)

watch(
  slug,
  (s) => {
    if (s) void fetchProductBySlug(s).catch(() => undefined)
    activeIndex.value = 0
  },
  { immediate: true },
)
watch(product, (p) => storefrontStore.setCurrentProduct(p?.id ?? null), { immediate: true })
onUnmounted(() => storefrontStore.setCurrentProduct(null))

function prev(): void {
  activeIndex.value = (activeIndex.value - 1 + images.value.length) % images.value.length
}

function next(): void {
  activeIndex.value = (activeIndex.value + 1) % images.value.length
}

function onKeydown(e: KeyboardEvent): void {
  if (!hasMultiple.value) return
  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    prev()
  }
  if (e.key === 'ArrowRight') {
    e.preventDefault()
    next()
  }
}

function onTouchStart(e: TouchEvent): void {
  touchStartX = e.touches[0]?.clientX ?? 0
}

function onTouchEnd(e: TouchEvent): void {
  if (!hasMultiple.value) return
  const dx = (e.changedTouches[0]?.clientX ?? 0) - touchStartX
  // 40 px threshold to avoid firing on taps
  if (dx > 40) prev()
  else if (dx < -40) next()
}

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
    <!-- Skeleton -->
    <div v-if="isPending" class="grid animate-pulse gap-8 lg:grid-cols-2">
      <div class="space-y-3">
        <div class="aspect-square rounded-2xl bg-app-bg-sunken" />
        <div class="flex justify-center gap-2">
          <div v-for="i in 3" :key="i" class="h-2 w-2 rounded-full bg-app-bg-sunken" />
        </div>
      </div>
      <div class="space-y-4">
        <div class="h-8 w-2/3 rounded bg-app-bg-sunken" />
        <div class="h-6 w-1/3 rounded bg-app-bg-sunken" />
        <div class="h-24 rounded bg-app-bg-sunken" />
      </div>
    </div>

    <div v-else-if="product" class="grid gap-10 lg:grid-cols-2">
      <!-- Carousel -->
      <div class="space-y-3">
        <!-- Main stage -->
        <div
          class="relative aspect-square select-none overflow-hidden rounded-2xl bg-app-bg-sunken focus:outline-none"
          tabindex="0"
          role="region"
          :aria-label="t('product.image_gallery', 'Product image gallery')"
          @keydown="onKeydown"
          @touchstart.passive="onTouchStart"
          @touchend.passive="onTouchEnd"
        >
          <Transition name="carousel-fade" mode="out-in">
            <img
              v-if="activeImage"
              :key="activeIndex"
              :src="activeImage.conversions?.card || activeImage.url"
              :srcset="activeImage.srcsets?.card || undefined"
              sizes="(min-width: 1024px) 50vw, 100vw"
              :alt="`${product.name} — ${t('product.image', 'image')} ${activeIndex + 1}`"
              class="h-full w-full object-cover"
              draggable="false"
            />
            <img
              v-else-if="product.thumbnail_url"
              :key="'fallback'"
              :src="product.thumbnail_url"
              :srcset="product.image_srcset || undefined"
              :alt="product.name"
              class="h-full w-full object-cover"
              draggable="false"
            />
            <div
              v-else
              :key="'empty'"
              class="flex h-full items-center justify-center text-fg-faint"
            >
              {{ t('product.no_image', 'No image') }}
            </div>
          </Transition>

          <!-- Prev / Next arrows -->
          <template v-if="hasMultiple">
            <button
              type="button"
              :aria-label="t('product.prev_image', 'Previous image')"
              class="absolute start-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-2 text-white backdrop-blur-sm transition hover:bg-black/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
              @click="prev"
            >
              <svg
                class="h-5 w-5"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>

            <button
              type="button"
              :aria-label="t('product.next_image', 'Next image')"
              class="absolute end-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-2 text-white backdrop-blur-sm transition hover:bg-black/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
              @click="next"
            >
              <svg
                class="h-5 w-5"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </button>

            <!-- Counter badge -->
            <span
              class="absolute bottom-3 end-3 rounded-full bg-black/50 px-2 py-0.5 text-xs text-white tabular-nums backdrop-blur-sm"
            >
              {{ activeIndex + 1 }} / {{ images.length }}
            </span>
          </template>
        </div>

        <!-- Thumbnail strip + dot indicators -->
        <div v-if="hasMultiple">
          <!-- Thumbnails (desktop) -->
          <div class="hidden gap-2 overflow-x-auto pb-1 sm:flex">
            <button
              v-for="(img, i) in images"
              :key="img.url"
              type="button"
              :aria-label="`${t('product.go_to_image', 'Go to image')} ${i + 1}`"
              :aria-current="i === activeIndex"
              class="h-16 w-16 shrink-0 overflow-hidden rounded-lg border-2 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
              :class="
                i === activeIndex
                  ? 'border-brand opacity-100'
                  : 'border-transparent opacity-50 hover:opacity-80'
              "
              @click="activeIndex = i"
            >
              <img
                :src="img.conversions?.thumbnail || img.url"
                :alt="`${product.name} ${i + 1}`"
                class="h-full w-full object-cover"
              />
            </button>
          </div>

          <!-- Dot indicators (mobile) -->
          <div class="flex justify-center gap-1.5 sm:hidden" role="tablist">
            <button
              v-for="(_, i) in images"
              :key="i"
              type="button"
              role="tab"
              :aria-label="`${t('product.go_to_image', 'Go to image')} ${i + 1}`"
              :aria-selected="i === activeIndex"
              class="h-2 rounded-full transition-all duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
              :class="i === activeIndex ? 'w-5 bg-brand' : 'w-2 bg-fg-faint'"
              @click="activeIndex = i"
            />
          </div>
        </div>
      </div>

      <!-- Product info -->
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

<style scoped>
.carousel-fade-enter-active,
.carousel-fade-leave-active {
  transition: opacity 0.18s ease;
}
.carousel-fade-enter-from,
.carousel-fade-leave-to {
  opacity: 0;
}
</style>
