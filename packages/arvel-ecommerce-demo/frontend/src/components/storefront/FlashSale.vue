<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ProductCard from '@/components/storefront/ProductCard.vue'
import type { ProductCardOut } from '@/api/schemas'

const props = defineProps<{
  products: ProductCardOut[]
}>()

const { t } = useI18n({ useScope: 'global' })

const saleProducts = computed(() =>
  props.products.slice(0, 4).map((product, index) => ({
    product,
    salePrice: product.price * (index % 2 === 0 ? 0.8 : 0.85),
    originalPrice: product.price,
  })),
)

// Countdown — resets to 24h from page load each session (demo behaviour)
const secondsLeft = ref(24 * 60 * 60)
let timer: ReturnType<typeof setInterval> | null = null

const pad = (n: number): string => String(n).padStart(2, '0')

const countdown = computed(() => {
  const h = Math.floor(secondsLeft.value / 3600)
  const m = Math.floor((secondsLeft.value % 3600) / 60)
  const s = secondsLeft.value % 60
  return { h: pad(h), m: pad(m), s: pad(s) }
})

onMounted(() => {
  timer = setInterval(() => {
    if (secondsLeft.value > 0) secondsLeft.value--
  }, 1000)
})

onBeforeUnmount(() => {
  if (timer !== null) clearInterval(timer)
})
</script>

<template>
  <section class="bg-app-bg-raised">
    <div class="mx-auto max-w-7xl px-4 py-12 lg:px-8">
      <!-- Header row -->
      <div class="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <!-- Violet accent bar -->
          <div class="h-8 w-1 rounded-full bg-brand" aria-hidden="true" />
          <div>
            <!-- Cyan label for energy on white bg — matches docs site cyan highlight pattern -->
            <p
              class="flex items-center gap-1 text-xs font-bold uppercase tracking-widest text-accent"
            >
              <span
                class="material-symbols-outlined select-none text-base leading-none"
                aria-hidden="true"
                >bolt</span
              >
              {{ t('flash.limited_time', 'Limited Time') }}
            </p>
            <h2 class="mt-0.5 text-2xl font-extrabold text-fg">
              {{ t('flash.title', 'Deal of the Day') }}
            </h2>
          </div>
        </div>

        <!-- Countdown timer -->
        <div
          class="flex items-center gap-1"
          role="timer"
          aria-label="`Sale ends in ${countdown.h}:${countdown.m}:${countdown.s}`"
          aria-live="polite"
          aria-atomic="true"
        >
          <div v-for="(unit, key) in countdown" :key="key" class="flex items-center gap-1">
            <div
              class="flex h-12 w-12 flex-col items-center justify-center rounded-lg bg-brand-hero text-center shadow-sm"
            >
              <span class="font-mono text-xl font-extrabold leading-none text-white">{{
                unit
              }}</span>
              <span class="text-[9px] font-medium uppercase tracking-wide text-white/60">
                {{
                  key === 'h'
                    ? t('flash.hrs', 'Hrs')
                    : key === 'm'
                      ? t('flash.min', 'Min')
                      : t('flash.sec', 'Sec')
                }}
              </span>
            </div>
            <span v-if="key !== 's'" class="text-lg font-bold text-fg-faint">:</span>
          </div>
        </div>
      </div>

      <!-- Product cards -->
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ProductCard
          v-for="item in saleProducts"
          :key="item.product.id"
          :product="item.product"
          :sale-price="item.salePrice"
          :original-price="item.originalPrice"
        />
      </div>
    </div>
  </section>
</template>
