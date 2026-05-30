<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAdminOrdersBestSellersApiAdminOrdersBestSellersGet } from '@/api/default/default'
import { formatCurrency } from '@/lib/i18n'
import type { SupportedLocale } from '@/types'

const { t } = useI18n({ useScope: 'global' })

const { locale } = defineProps<{ locale: SupportedLocale }>()

const { data, isPending } = useAdminOrdersBestSellersApiAdminOrdersBestSellersGet()

const items = computed(() => data.value?.data ?? [])
const maxRevenue = computed(() => Math.max(...items.value.map((p) => p.revenue), 1))

function barWidth(revenue: number): string {
  return `${Math.round((revenue / maxRevenue.value) * 100)}%`
}
</script>

<template>
  <div
    class="flex flex-col rounded-xl border border-[#eee] bg-admin-surface shadow-sm dark:border-border-subtle"
  >
    <div class="border-b border-border-subtle px-6 py-4">
      <h2 class="font-semibold text-fg">{{ t('admin.best_sellers.title') }}</h2>
    </div>

    <div v-if="isPending" class="flex items-center justify-center px-6 py-10">
      <span class="material-symbols-outlined animate-spin text-fg-faint">progress_activity</span>
    </div>

    <ol v-else class="divide-y divide-border-subtle">
      <li
        v-for="(entry, index) in items"
        :key="entry.product_id ?? entry.name"
        class="flex items-center gap-4 px-6 py-4"
      >
        <span
          class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold"
          :class="
            index === 0 ? 'bg-kpi-amber-bg text-kpi-amber-fg' : 'bg-app-bg-sunken text-fg-muted'
          "
          >{{ index + 1 }}</span
        >

        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium text-fg">{{ entry.name }}</p>
          <div class="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-app-bg-sunken">
            <div
              class="h-full rounded-full bg-brand transition-all duration-500"
              :style="{ width: barWidth(entry.revenue) }"
            />
          </div>
        </div>

        <div class="shrink-0 text-end">
          <p class="text-sm font-semibold text-fg">
            {{ formatCurrency(entry.revenue, locale as SupportedLocale) }}
          </p>
          <p class="mt-0.5 text-xs text-fg-faint">
            {{ t('admin.best_sellers.units', { n: entry.units_sold }) }}
          </p>
        </div>
      </li>

      <p v-if="items.length === 0" class="px-6 py-10 text-center text-sm text-fg-faint">
        {{ t('admin.best_sellers.empty') }}
      </p>
    </ol>
  </div>
</template>
