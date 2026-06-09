<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n({ useScope: 'global' })

interface Promo {
  id: string
  eyebrow: string
  title: string
  subtitle: string
  cta: string
  to: string
  bg: string
  icon: string
}

const promos = computed<Promo[]>(() => [
  {
    id: 'smartphones',
    eyebrow: t('promo.mobiles.eyebrow', 'Trending now'),
    title: t('promo.mobiles.title', 'Smart Mobiles'),
    subtitle: t('promo.mobiles.subtitle', 'Indulge in latest models'),
    cta: t('promo.shop_now', 'Shop Now'),
    to: '/products?category=smartphones',
    bg: 'linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%)',
    icon: 'phone_iphone',
  },
  {
    id: 'headsets',
    eyebrow: t('promo.headsets.eyebrow', 'Fan favorites'),
    title: t('promo.headsets.title', 'Smart Headset'),
    subtitle: t('promo.headsets.subtitle', 'Enjoy wireless freedom'),
    cta: t('promo.shop_now', 'Shop Now'),
    to: '/products?category=headsets',
    bg: 'linear-gradient(135deg, #7C3AED 0%, #5B21B6 100%)',
    icon: 'headphones',
  },
  {
    id: 'speakers',
    eyebrow: t('promo.speakers.eyebrow', "Editor's pick"),
    title: t('promo.speakers.title', 'Portable Speaker'),
    subtitle: t('promo.speakers.subtitle', 'Take your music anywhere'),
    cta: t('promo.shop_now', 'Shop Now'),
    to: '/products?category=speakers',
    bg: 'linear-gradient(135deg, #06B6D4 0%, #0E7490 100%)',
    icon: 'speaker',
  },
])
</script>

<template>
  <div class="grid gap-4 sm:grid-cols-3">
    <RouterLink
      v-for="(promo, i) in promos"
      :key="promo.id"
      v-reveal="i * 90"
      :to="promo.to"
      class="group relative flex min-h-[160px] flex-col justify-between overflow-hidden rounded-xl p-5 shadow-sm transition duration-300 ease-[cubic-bezier(0.2,0,0,1)] hover:-translate-y-1 hover:shadow-xl"
      :style="{ background: promo.bg }"
    >
      <div>
        <p class="text-xs font-semibold uppercase tracking-widest text-white/80">
          {{ promo.eyebrow }}
        </p>
        <h3 class="mt-1 max-w-[65%] text-lg font-extrabold leading-tight text-white">
          {{ promo.title }}
        </h3>
        <p class="mt-1 max-w-[65%] text-xs text-white/70">{{ promo.subtitle }}</p>
      </div>

      <span
        class="mt-4 inline-flex w-fit items-center rounded-full bg-white/20 px-4 py-1.5 text-xs font-bold text-white backdrop-blur-sm transition group-hover:bg-white/30"
      >
        {{ promo.cta }} →
      </span>

      <!-- Decorative product icon -->
      <span
        class="material-symbols-outlined absolute bottom-5 self-end select-none text-[72px] leading-none opacity-25 transition duration-300 group-hover:scale-110 group-hover:opacity-35"
        style="font-size: 72px"
        aria-hidden="true"
        >{{ promo.icon }}</span
      >
    </RouterLink>
  </div>
</template>
