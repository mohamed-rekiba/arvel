<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n({ useScope: 'global' })
</script>

<template>
  <section class="mx-auto max-w-7xl px-4 lg:px-8">
    <div
      class="grid min-h-[360px] overflow-hidden rounded-2xl sm:min-h-[420px] md:grid-cols-[55%_45%]"
      style="border: 1px solid oklch(0.62 0.06 287 / 0.15)"
    >
      <!-- Left: editorial text on soft violet wash -->
      <div
        class="relative flex flex-col justify-center overflow-hidden bg-gradient-to-br from-primary-50 via-white to-white px-8 py-12 md:px-12"
      >
        <!-- decorative blob -->
        <div
          class="pointer-events-none absolute -start-16 -top-16 h-64 w-64 rounded-full bg-primary-100/60"
        />

        <span
          class="relative inline-flex w-fit items-center gap-1.5 rounded-full bg-brand px-3 py-1 text-xs font-bold uppercase tracking-widest text-white"
        >
          <span
            class="material-symbols-outlined select-none text-[14px] leading-none"
            aria-hidden="true"
            >auto_awesome</span
          >
          {{ t('hero.eyebrow', 'New Collection') }}
        </span>

        <!-- text-primary-950 stays dark in both modes; left panel is always light -->
        <h1
          class="relative mt-4 text-balance text-4xl font-extrabold leading-tight text-primary-950 md:text-5xl"
        >
          {{ t('hero.title', 'Tech that keeps up') }}
          <span class="text-primary-700">{{ t('hero.title_accent', 'with you') }}</span>
        </h1>

        <p class="relative mt-4 max-w-md text-primary-900/70">
          {{ t('hero.subtitle', 'Curated electronics, ready to ship.') }}
        </p>

        <div class="relative mt-6 flex gap-3">
          <RouterLink
            to="/products"
            class="inline-flex items-center rounded-full bg-primary-700 px-7 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-primary-800 hover:shadow-md"
          >
            {{ t('hero.cta', 'Shop Now') }}
          </RouterLink>
          <RouterLink
            to="/products"
            class="inline-flex items-center rounded-full border border-primary-200 px-7 py-3 text-sm font-semibold text-primary-950 transition hover:border-primary-700 hover:text-primary-700"
          >
            {{ t('hero.browse', 'Browse All') }}
          </RouterLink>
        </div>
      </div>

      <!-- Right: product showcase on violet gradient (matches framework brand) -->
      <div
        class="relative hidden items-center justify-center overflow-hidden bg-gradient-to-br from-brand-hero via-primary-900 to-primary-950 md:flex"
      >
        <!-- Decorative circles -->
        <div class="absolute -end-16 -top-16 h-64 w-64 rounded-full bg-primary-600/30" />
        <div class="absolute -bottom-12 -start-12 h-48 w-48 rounded-full bg-cyan-500/20" />

        <!-- Product device mockup -->
        <div class="relative z-10 text-center">
          <span
            class="material-symbols-outlined select-none drop-shadow-lg"
            style="font-size: 9rem; line-height: 1; color: rgba(255, 255, 255, 0.92)"
            aria-hidden="true"
            >laptop_mac</span
          >
          <div
            class="mt-4 inline-flex items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-sm font-semibold text-white shadow-md backdrop-blur-sm"
          >
            <span
              class="material-symbols-outlined select-none text-[16px] leading-none text-accent"
              style="font-variation-settings: 'FILL' 1"
              aria-hidden="true"
              >verified</span
            >
            <span class="text-white">{{ t('hero.badge', 'Curated picks') }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
