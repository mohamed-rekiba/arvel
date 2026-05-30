<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { requireStoredAccessToken } from '@/lib/api'
import {
  useApiAccountOrdersListApiAccountOrdersGet,
  useApiAccountOrdersShowApiAccountOrdersOrderIdGet,
} from '@/api/account/account'
import type { OrderOut } from '@/api/schemas'
import { formatCurrency, formatDate, toSupportedLocale } from '@/lib/i18n'

const { locale, t } = useI18n({ useScope: 'global' })
const currentLocale = computed(() => toSupportedLocale(locale.value))

onMounted(() => {
  requireStoredAccessToken()
})

const route = useRoute()

const { data, isPending } = useApiAccountOrdersListApiAccountOrdersGet()
const orders = computed(() => data.value?.data ?? [])

const selectedOrderId = ref<string | null>(null)

const orderIdForQuery = computed<string>(() => selectedOrderId.value ?? '')

const { data: orderDetailData, isPending: loadingDetail } =
  useApiAccountOrdersShowApiAccountOrdersOrderIdGet(orderIdForQuery, {
    query: { enabled: computed(() => Boolean(selectedOrderId.value)) },
  })

const orderDetail = computed(() => orderDetailData.value?.data ?? null)

const DELIVERY_FEE = 0

const statusColors: Record<string, string> = {
  pending: 'bg-status-pending-bg text-status-pending-fg',
  confirmed: 'bg-status-active-bg text-status-active-fg',
  processing: 'bg-status-active-bg text-status-active-fg',
  shipped: 'bg-status-shipped-bg text-status-shipped-fg',
  delivered: 'bg-status-delivered-bg text-status-delivered-fg',
  cancelled: 'bg-danger/15 text-danger',
}

function orderAddress(order: OrderOut): string {
  const addr = order.shipping_address
  return ['street', 'city', 'country']
    .map((key) => addr[key])
    .filter((v): v is string => typeof v === 'string' && v !== '')
    .join(', ')
}

function itemShipping(index: number): string {
  return index === 0 ? formatCurrency(DELIVERY_FEE, currentLocale.value) : t('order.free', 'Free')
}

function closeDrawer(): void {
  selectedOrderId.value = null
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-4 py-10 lg:px-8">
    <h1 class="text-3xl font-bold text-fg">{{ t('account.title', 'My Orders') }}</h1>

    <!-- Success banner after checkout redirect -->
    <div
      v-if="route.query.order"
      class="mt-4 flex items-center gap-2 rounded-xl bg-status-delivered-bg px-4 py-3 text-sm text-status-delivered-fg"
    >
      <span
        class="material-symbols-outlined select-none text-[18px] leading-none"
        style="font-variation-settings: 'FILL' 1"
        >check_circle</span
      >
      {{ t('account.order_placed') }}
    </div>

    <!-- Loading skeletons -->
    <div v-if="isPending" class="mt-8 space-y-3">
      <div v-for="i in 4" :key="i" class="h-16 animate-pulse rounded-xl bg-app-bg-sunken" />
    </div>

    <!-- Empty state -->
    <div v-else-if="orders.length === 0" class="mt-20 flex flex-col items-center gap-3 text-center">
      <span class="material-symbols-outlined select-none text-[56px] leading-none text-fg-faint">
        receipt_long
      </span>
      <p class="text-fg-faint">{{ t('account.no_orders') }}</p>
    </div>

    <!-- Orders table -->
    <div
      v-else
      class="mt-8 overflow-hidden rounded-xl border border-border-subtle bg-app-bg shadow-sm"
    >
      <div class="overflow-x-auto">
        <table class="w-full min-w-[560px]">
          <thead>
            <tr class="bg-brand text-white">
              <th class="px-6 py-3.5 text-start text-sm font-semibold">
                {{ t('account.col_order') }}
              </th>
              <th class="px-4 py-3.5 text-start text-sm font-semibold">
                {{ t('account.col_date') }}
              </th>
              <th class="px-4 py-3.5 text-center text-sm font-semibold">
                {{ t('account.col_items') }}
              </th>
              <th class="px-4 py-3.5 text-center text-sm font-semibold">
                {{ t('account.col_payment') }}
              </th>
              <th class="px-4 py-3.5 text-center text-sm font-semibold">
                {{ t('account.col_status') }}
              </th>
              <th class="px-6 py-3.5 text-end text-sm font-semibold">{{ t('order.total') }}</th>
              <th class="px-4 py-3.5 text-center text-sm font-semibold">
                {{ t('account.col_details') }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border-subtle">
            <tr
              v-for="order in orders"
              :key="order.id"
              class="group cursor-pointer transition-colors hover:bg-app-bg-raised"
              @click="selectedOrderId = order.id"
            >
              <td class="px-6 py-4">
                <p class="text-sm font-semibold text-fg">#{{ order.id.slice(0, 8) }}</p>
              </td>
              <td class="px-4 py-4">
                <p class="text-sm text-fg-muted">
                  {{ formatDate(order.created_at, currentLocale) }}
                </p>
              </td>
              <td class="px-4 py-4 text-center">
                <span class="text-sm text-fg">{{ order.items?.length ?? 0 }}</span>
              </td>
              <td class="px-4 py-4">
                <div class="flex items-center justify-center gap-1">
                  <span
                    class="material-symbols-outlined select-none text-[15px] leading-none text-brand"
                    style="font-variation-settings: 'FILL' 1"
                    >payments</span
                  >
                  <span class="text-xs text-fg-muted">COD</span>
                </div>
              </td>
              <td class="px-4 py-4 text-center">
                <span
                  class="inline-flex w-20 justify-center rounded-full px-[10px] py-[5px] text-xs font-medium"
                  :class="statusColors[order.status] ?? 'bg-app-bg-sunken text-fg-muted'"
                  >{{ t(`admin.order_status.${order.status}`, order.status) }}</span
                >
              </td>
              <td class="px-6 py-4 text-end text-sm font-bold text-fg">
                {{ formatCurrency(order.total, currentLocale) }}
              </td>
              <td class="px-4 py-4 text-center">
                <span
                  class="material-symbols-outlined select-none text-[20px] leading-none text-fg-faint transition group-hover:text-brand rtl:rotate-180"
                >
                  chevron_right
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Order detail drawer -->
  <Teleport to="body">
    <Transition name="overlay">
      <!-- ltr:justify-end rtl:justify-start keeps the drawer on the right in both directions -->
      <div v-if="selectedOrderId" class="fixed inset-0 z-50 flex ltr:justify-end rtl:justify-start">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="closeDrawer" />

        <!-- Drawer panel -->
        <div
          class="drawer-panel relative z-10 flex h-full w-full max-w-lg flex-col overflow-y-auto bg-app-bg shadow-2xl"
        >
          <!-- Sticky header -->
          <div
            class="sticky top-0 z-10 flex items-center justify-between border-b border-border-subtle bg-app-bg px-6 py-5"
          >
            <div>
              <h2 class="text-lg font-bold text-fg">
                {{ t('account.drawer_order') }}
                <span dir="ltr">#{{ orderDetail?.id.slice(0, 8) ?? '…' }}</span>
              </h2>
              <span
                v-if="orderDetail"
                class="mt-0.5 inline-flex w-20 justify-center rounded-full px-[10px] py-[5px] text-xs font-medium"
                :class="statusColors[orderDetail.status] ?? 'bg-app-bg-sunken text-fg-muted'"
                >{{ t(`admin.order_status.${orderDetail.status}`, orderDetail.status) }}</span
              >
            </div>
            <button
              type="button"
              class="flex h-8 w-8 items-center justify-center rounded-full text-fg-muted hover:bg-app-bg-raised hover:text-fg"
              @click="closeDrawer"
            >
              <span class="material-symbols-outlined select-none text-[20px] leading-none"
                >close</span
              >
            </button>
          </div>

          <!-- Loading -->
          <div v-if="loadingDetail" class="flex-1 space-y-4 p-6">
            <div v-for="i in 4" :key="i" class="h-16 animate-pulse rounded-lg bg-app-bg-sunken" />
          </div>

          <!-- Detail content -->
          <template v-else-if="orderDetail">
            <!-- Meta grid -->
            <div class="grid grid-cols-2 gap-4 border-b border-border-subtle px-6 py-5">
              <div>
                <p class="text-xs text-fg-muted">{{ t('order.date') }}</p>
                <p class="mt-0.5 text-sm font-semibold text-fg">
                  {{ formatDate(orderDetail.created_at, currentLocale) }}
                </p>
              </div>
              <div>
                <p class="text-xs text-fg-muted">{{ t('order.id') }}</p>
                <p class="mt-0.5 text-sm font-semibold text-fg" dir="ltr">
                  #{{ orderDetail.id.slice(0, 10) }}
                </p>
              </div>
              <div>
                <p class="text-xs text-fg-muted">{{ t('order.payment') }}</p>
                <div class="mt-1 flex items-center gap-1.5">
                  <span
                    class="material-symbols-outlined select-none text-[16px] leading-none text-brand"
                    style="font-variation-settings: 'FILL' 1"
                    >payments</span
                  >
                  <span class="text-xs font-medium text-fg">{{ t('order.cod') }}</span>
                </div>
              </div>
              <div>
                <p class="text-xs text-fg-muted">{{ t('order.address') }}</p>
                <p class="mt-0.5 truncate text-sm font-semibold text-fg">
                  {{ orderAddress(orderDetail) || '—' }}
                </p>
              </div>
            </div>

            <!-- Items table -->
            <div class="overflow-x-auto">
              <table class="w-full min-w-[380px]">
                <thead>
                  <tr class="border-b border-border-subtle">
                    <th
                      class="px-6 py-3 text-start text-xs font-medium uppercase tracking-wide text-fg-muted"
                    >
                      {{ t('order.product') }}
                    </th>
                    <th
                      class="px-4 py-3 text-center text-xs font-medium uppercase tracking-wide text-fg-muted"
                    >
                      {{ t('order.shipping') }}
                    </th>
                    <th
                      class="px-4 py-3 text-center text-xs font-medium uppercase tracking-wide text-fg-muted"
                    >
                      {{ t('order.qty') }}
                    </th>
                    <th
                      class="px-6 py-3 text-end text-xs font-medium uppercase tracking-wide text-fg-muted"
                    >
                      {{ t('order.total') }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-border-subtle">
                  <tr v-for="(item, i) in orderDetail.items" :key="item.id">
                    <td class="px-6 py-4">
                      <div class="flex items-center gap-3">
                        <div
                          class="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-app-bg-sunken"
                        >
                          <span
                            class="material-symbols-outlined select-none text-[24px] leading-none text-fg-faint"
                            >shopping_bag</span
                          >
                        </div>
                        <div>
                          <p class="text-sm font-semibold text-fg">{{ item.product_name }}</p>
                          <p class="text-xs font-medium text-brand">
                            {{ formatCurrency(item.unit_price, currentLocale) }}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td class="px-4 py-4 text-center text-sm text-fg">{{ itemShipping(i) }}</td>
                    <td class="px-4 py-4 text-center">
                      <span
                        class="inline-flex h-7 min-w-[2rem] items-center justify-center rounded-full border border-border px-2 text-sm font-medium text-fg"
                      >
                        {{ item.quantity }}
                      </span>
                    </td>
                    <td class="px-6 py-4 text-end text-sm font-semibold text-brand">
                      {{ formatCurrency(item.subtotal, currentLocale) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Totals -->
            <div class="space-y-2 border-t border-border-subtle px-6 py-5">
              <div class="flex justify-between text-sm text-fg-muted">
                <span>{{ t('order.shipping') }}</span>
                <span>{{ formatCurrency(DELIVERY_FEE, currentLocale) }}</span>
              </div>
              <div
                class="flex justify-between border-t border-border-subtle pt-2 text-sm font-bold text-fg"
              >
                <span>{{ t('order.total') }}</span>
                <span>{{ formatCurrency(orderDetail.total, currentLocale) }}</span>
              </div>
            </div>
          </template>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.overlay-enter-active {
  transition: opacity 0.25s;
}
.overlay-enter-active .drawer-panel {
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
.overlay-leave-active {
  transition: opacity 0.2s;
}
.overlay-leave-active .drawer-panel {
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}
/* Drawer is always on the right (ltr:justify-end rtl:justify-start).
   translateX(100%) slides it off-screen to the right in both directions. */
.overlay-enter-from .drawer-panel,
.overlay-leave-to .drawer-panel {
  transform: translateX(100%);
}
</style>
