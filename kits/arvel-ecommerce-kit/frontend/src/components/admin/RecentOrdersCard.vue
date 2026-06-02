<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { formatCurrency, formatDate } from '@/lib/i18n'
import type { AdminOrderOut } from '@/api/schemas'
import type { SupportedLocale } from '@/types'

const { t } = useI18n({ useScope: 'global' })

defineProps<{
  orders: AdminOrderOut[]
  locale: SupportedLocale
}>()

const statusColors: Record<string, string> = {
  pending: 'bg-status-pending-bg text-status-pending-fg',
  confirmed: 'bg-status-active-bg text-status-active-fg',
  processing: 'bg-status-active-bg text-status-active-fg',
  shipped: 'bg-status-shipped-bg text-status-shipped-fg',
  delivered: 'bg-status-delivered-bg text-status-delivered-fg',
  cancelled: 'bg-danger/15 text-danger',
}
</script>

<template>
  <div
    class="flex flex-col rounded-xl border border-[#eee] bg-admin-surface shadow-sm dark:border-border-subtle"
  >
    <div class="flex items-center justify-between border-b border-border-subtle px-6 py-4">
      <h2 class="font-semibold text-fg">{{ t('admin.recent_orders.title') }}</h2>
      <RouterLink to="/admin/orders" class="text-sm text-brand hover:text-brand-hover">
        {{ t('admin.recent_orders.view_all') }}
      </RouterLink>
    </div>

    <div class="divide-y divide-border-subtle">
      <RouterLink
        v-for="order in orders"
        :key="order.id"
        :to="`/admin/orders/${order.id}`"
        class="group flex items-center gap-4 px-6 py-3.5 transition hover:bg-app-bg-raised"
      >
        <!-- order id + customer -->
        <div class="min-w-0 flex-1">
          <p class="text-sm font-semibold text-fg">#{{ order.id.slice(0, 8) }}</p>
          <p class="mt-0.5 truncate text-xs text-fg-muted">{{ order.user?.name ?? '—' }}</p>
        </div>

        <!-- status badge -->
        <span
          class="inline-flex w-20 shrink-0 justify-center rounded-full px-[10px] py-[5px] text-xs font-medium"
          :class="statusColors[order.status]"
        >
          {{ t(`admin.order_status.${order.status}`, order.status) }}
        </span>

        <!-- amount + date -->
        <div class="shrink-0 text-end">
          <p class="text-sm font-semibold text-fg">{{ formatCurrency(order.total, locale) }}</p>
          <p class="mt-0.5 text-xs text-fg-faint">{{ formatDate(order.created_at, locale) }}</p>
        </div>

        <!-- chevron -->
        <span
          class="material-symbols-outlined shrink-0 text-[18px] leading-none text-fg-faint transition group-hover:text-brand rtl:rotate-180"
          aria-hidden="true"
          >chevron_right</span
        >
      </RouterLink>

      <p v-if="orders.length === 0" class="px-6 py-10 text-center text-sm text-fg-faint">
        {{ t('admin.recent_orders.empty') }}
      </p>
    </div>
  </div>
</template>
