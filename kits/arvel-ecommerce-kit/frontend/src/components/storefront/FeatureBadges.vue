<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n({ useScope: 'global' })

const badges = computed(() => [
  {
    id: 'return',
    icon: 'autorenew',
    title: t('badge.return_title', 'Easy to buy & return'),
    subtitle: t('badge.return_subtitle', 'Single click returns & refunds'),
  },
  {
    id: 'payment',
    icon: 'lock',
    title: t('badge.payment_title', 'Secure Payments'),
    subtitle: t('badge.payment_subtitle', '100% protected transactions'),
  },
  {
    id: 'support',
    icon: 'headset_mic',
    title: t('badge.support_title', '24/7 Support Available'),
    subtitle: t('badge.support_subtitle', 'Dedicated support team'),
  },
  {
    id: 'app',
    icon: 'phone_iphone',
    title: t('badge.app_title', 'Shop with our App'),
    subtitle: t('badge.app_subtitle', 'Get exclusive app-only offers'),
  },
])
</script>

<template>
  <div class="border-t border-border">
    <div class="mx-auto grid max-w-7xl grid-cols-2 gap-6 px-4 py-10 md:grid-cols-4 lg:px-8">
      <div
        v-for="badge in badges"
        :key="badge.id"
        class="flex items-center gap-4 rounded-xl p-3 transition duration-150 hover:bg-app-bg-raised"
      >
        <div
          class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary-100 shadow-sm"
        >
          <span
            class="material-symbols-outlined select-none text-[22px] leading-none text-primary-700"
            aria-hidden="true"
            >{{ badge.icon }}</span
          >
        </div>
        <div>
          <p class="text-sm font-semibold text-fg">{{ badge.title }}</p>
          <p class="text-xs text-fg-muted">{{ badge.subtitle }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
