<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  useAdminOrdersShowApiAdminOrdersOrderIdGet,
  useAdminOrdersUpdateStatusApiAdminOrdersOrderIdStatusPatch,
} from '@/api/admin-orders/admin-orders'
import { useQueryClient } from '@tanstack/vue-query'
import {
  formatCurrency,
  formatDate,
  pickLocalized,
  routeParam,
  toSupportedLocale,
} from '@/lib/i18n'
import { useToastStore } from '@/stores/toast'
import PermissionGate from '@/components/admin/PermissionGate.vue'
import { getShippingField, isOrderStatus } from '@/types'
import type { OrderStatus } from '@/types'

const { locale, t } = useI18n({ useScope: 'global' })
const currentLocale = computed(() => toSupportedLocale(locale.value))
const toast = useToastStore()
const route = useRoute()
const queryClient = useQueryClient()

const orderId = computed(() => routeParam(route.params.id ?? route.params.orderId))

const selectedStatus = ref<OrderStatus>('pending')

const { data: orderWrapper, isPending } = useAdminOrdersShowApiAdminOrdersOrderIdGet(orderId)
const order = computed(() => orderWrapper.value?.data ?? null)

watch(order, (o) => {
  if (o && isOrderStatus(o.status)) selectedStatus.value = o.status
})

const { mutate: updateStatus, isPending: saving } =
  useAdminOrdersUpdateStatusApiAdminOrdersOrderIdStatusPatch({
    mutation: {
      onSuccess: () => {
        // Prefix covers both the detail (show) and the orders list queries.
        void queryClient.invalidateQueries({ queryKey: ['api', 'admin', 'orders'] })
        toast.success(t('admin.order.status_updated', { status: selectedStatus.value }))
      },
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : t('admin.order.update_failed')),
    },
  })

const statuses: OrderStatus[] = [
  'pending',
  'confirmed',
  'processing',
  'shipped',
  'delivered',
  'cancelled',
]
</script>

<template>
  <div>
    <RouterLink
      to="/admin/orders"
      class="inline-flex items-center gap-1 text-sm text-brand hover:underline"
    >
      <span
        class="material-symbols-outlined text-[18px] leading-none rtl:rotate-180"
        aria-hidden="true"
        >arrow_back</span
      >
      {{ t('admin.order.back') }}
    </RouterLink>

    <div v-if="isPending" class="mt-8 h-48 animate-pulse rounded-xl bg-app-bg-sunken" />

    <div v-else-if="order" class="mt-6 space-y-6">
      <div class="rounded-xl bg-admin-surface p-6 shadow-sm">
        <div class="flex items-start justify-between">
          <div>
            <h1 class="text-2xl font-bold text-fg">Order #{{ order.id.slice(0, 8) }}</h1>
            <p class="mt-1 text-sm text-fg-muted">
              {{ formatDate(order.created_at, currentLocale) }}
            </p>
          </div>
          <p class="text-xl font-bold">{{ formatCurrency(order.total, currentLocale) }}</p>
        </div>

        <div class="mt-6 grid gap-4 sm:grid-cols-2">
          <div>
            <p class="text-xs uppercase tracking-wide text-fg-faint">
              {{ t('admin.order.customer') }}
            </p>
            <p class="font-medium">{{ order.user?.name }}</p>
            <p class="text-sm text-fg-muted">{{ order.user?.email }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-fg-faint">
              {{ t('admin.order.shipping') }}
            </p>
            <p class="text-sm text-fg">
              {{ getShippingField(order.shipping_address, 'name') }}<br />
              {{ getShippingField(order.shipping_address, 'street') }}<br />
              {{ getShippingField(order.shipping_address, 'city') }},
              {{ getShippingField(order.shipping_address, 'country') }}
            </p>
          </div>
        </div>
      </div>

      <div class="rounded-xl bg-admin-surface p-6 shadow-sm">
        <h2 class="font-semibold text-fg">{{ t('admin.order.items') }}</h2>
        <ul class="mt-4 divide-y divide-border-subtle">
          <li v-for="item in order.items" :key="item.id" class="flex justify-between py-3 text-sm">
            <span
              >{{
                item.product ? pickLocalized(item.product.name, currentLocale) : item.product_name
              }}
              × {{ item.quantity }}</span
            >
            <span class="font-medium">{{
              formatCurrency(item.unit_price * item.quantity, currentLocale)
            }}</span>
          </li>
        </ul>
      </div>

      <div class="rounded-xl bg-admin-surface p-6 shadow-sm">
        <h2 class="font-semibold text-fg">{{ t('admin.order.update_status') }}</h2>
        <div class="mt-4 flex flex-wrap items-center gap-3">
          <select
            v-model="selectedStatus"
            class="rounded-lg border border-border px-4 py-2 text-sm outline-none focus:border-brand"
          >
            <option v-for="status in statuses" :key="status" :value="status">
              {{ t(`admin.order_status.${status}`, status) }}
            </option>
          </select>
          <PermissionGate permission="orders.update">
            <button
              type="button"
              class="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-50"
              :disabled="saving || selectedStatus === order.status"
              @click="updateStatus({ orderId: order.id, data: { status: selectedStatus } })"
            >
              {{ saving ? t('admin.order.saving') : t('admin.order.update') }}
            </button>
          </PermissionGate>
        </div>
      </div>
    </div>
  </div>
</template>
