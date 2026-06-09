<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n({ useScope: 'global' })

// Sparkle positions (top/start %) + per-dot delay so the field twinkles out of sync.
const sparkles = [
  { top: '14%', start: '22%', size: 4, delay: '0s' },
  { top: '28%', start: '8%', size: 3, delay: '0.8s' },
  { top: '62%', start: '16%', size: 5, delay: '1.6s' },
  { top: '18%', start: '52%', size: 3, delay: '0.4s' },
  { top: '74%', start: '46%', size: 4, delay: '2.1s' },
  { top: '36%', start: '88%', size: 5, delay: '1.1s' },
  { top: '68%', start: '78%', size: 3, delay: '2.6s' },
  { top: '8%', start: '72%', size: 4, delay: '1.9s' },
]
</script>

<template>
  <section class="mx-auto max-w-7xl px-4 lg:px-8">
    <div
      class="animate-gradient relative grid min-h-[420px] overflow-hidden rounded-3xl bg-gradient-to-br from-primary-950 via-brand-hero to-primary-900 md:min-h-[460px] md:grid-cols-[55%_45%]"
    >
      <!-- ── Ambient glow orbs ──────────────────────────────────────────── -->
      <div
        class="animate-glow pointer-events-none absolute -start-24 -top-24 h-72 w-72 rounded-full bg-primary-500/40 blur-3xl"
      />
      <div
        class="animate-glow animate-float-slow pointer-events-none absolute -bottom-24 start-1/3 h-64 w-64 rounded-full bg-cyan-500/25 blur-3xl"
      />
      <div
        class="animate-glow pointer-events-none absolute -end-20 top-1/4 h-80 w-80 rounded-full bg-primary-700/35 blur-3xl"
        style="animation-delay: 1.5s"
      />

      <!-- ── Sparkle field ──────────────────────────────────────────────── -->
      <span
        v-for="(s, i) in sparkles"
        :key="i"
        class="animate-twinkle pointer-events-none absolute rounded-full bg-white"
        :style="{
          top: s.top,
          insetInlineStart: s.start,
          width: `${s.size}px`,
          height: `${s.size}px`,
          animationDelay: s.delay,
          boxShadow: '0 0 8px 1px rgba(255,255,255,0.6)',
        }"
        aria-hidden="true"
      />

      <!-- ── Left: editorial copy ───────────────────────────────────────── -->
      <div class="relative z-10 flex flex-col justify-center px-8 py-14 md:px-12">
        <span
          v-reveal
          class="inline-flex w-fit items-center gap-1.5 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs font-bold uppercase tracking-widest text-cyan-300 backdrop-blur-sm"
        >
          <span
            class="material-symbols-outlined animate-twinkle select-none text-[14px] leading-none"
            aria-hidden="true"
            >auto_awesome</span
          >
          {{ t('hero.eyebrow', 'New Collection') }}
        </span>

        <h1
          v-reveal="80"
          class="mt-5 text-balance text-4xl font-extrabold leading-[1.08] text-white md:text-5xl lg:text-6xl"
        >
          {{ t('hero.title', 'Tech that keeps up') }}
          <span
            class="animate-gradient bg-gradient-to-r from-cyan-300 via-primary-200 to-cyan-300 bg-clip-text text-transparent"
          >
            {{ t('hero.title_accent', 'with you') }}
          </span>
        </h1>

        <p v-reveal="160" class="mt-5 max-w-md text-base text-white/70 md:text-lg">
          {{ t('hero.subtitle', 'Curated electronics, ready to ship.') }}
        </p>

        <div v-reveal="240" class="mt-8 flex flex-wrap gap-3">
          <RouterLink
            to="/products"
            class="group inline-flex items-center gap-2 rounded-full bg-primary-500 px-7 py-3 text-sm font-bold text-white shadow-[0_8px_30px_-6px_oklch(0.591_0.201_294_/_0.7)] transition duration-300 hover:-translate-y-0.5 hover:bg-primary-400 hover:shadow-[0_12px_40px_-6px_oklch(0.591_0.201_294_/_0.9)]"
          >
            {{ t('hero.cta', 'Shop Now') }}
            <span
              class="material-symbols-outlined select-none text-[18px] leading-none transition-transform duration-300 group-hover:translate-x-0.5 rtl:rotate-180 rtl:group-hover:-translate-x-0.5"
              aria-hidden="true"
              >arrow_forward</span
            >
          </RouterLink>
          <RouterLink
            to="/products"
            class="inline-flex items-center rounded-full border border-white/25 bg-white/5 px-7 py-3 text-sm font-semibold text-white backdrop-blur-sm transition duration-300 hover:border-cyan-300/60 hover:bg-white/10 hover:text-cyan-200"
          >
            {{ t('hero.browse', 'Browse All') }}
          </RouterLink>
        </div>
      </div>

      <!-- ── Right: floating glassy device mock ─────────────────────────── -->
      <div class="relative hidden items-center justify-center md:flex">
        <!-- Glow halo behind the mock -->
        <div
          class="animate-glow absolute h-72 w-72 rounded-full bg-gradient-to-tr from-primary-500/50 to-cyan-400/40 blur-3xl"
        />

        <div class="animate-float relative z-10">
          <div
            class="rounded-3xl border border-white/15 bg-white/10 p-8 shadow-2xl backdrop-blur-md"
          >
            <span
              class="material-symbols-outlined select-none drop-shadow-[0_8px_24px_rgba(0,0,0,0.4)]"
              style="font-size: 9rem; line-height: 1; color: rgba(255, 255, 255, 0.95)"
              aria-hidden="true"
              >laptop_mac</span
            >
          </div>

          <!-- Floating verified chip -->
          <div
            class="animate-float-slow absolute -bottom-4 -end-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/15 px-4 py-2 text-sm font-semibold text-white shadow-lg backdrop-blur-md"
          >
            <span
              class="material-symbols-outlined select-none text-[16px] leading-none text-cyan-300"
              style="font-variation-settings: 'FILL' 1"
              aria-hidden="true"
              >verified</span
            >
            <span>{{ t('hero.badge', 'Curated picks') }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
