<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'
import BestSellingList from '@/components/admin/BestSellingList.vue'
import RecentOrdersCard from '@/components/admin/RecentOrdersCard.vue'
import RevenueBarChart from '@/components/admin/RevenueBarChart.vue'
import StatCard from '@/components/admin/StatCard.vue'
import {
  useAdminOrdersIndexApiAdminOrdersGet,
  useAdminOrdersStatsApiAdminOrdersStatsGet,
} from '@/api/admin-orders/admin-orders'
import type { AdminOrderOut } from '@/api/schemas'
import { formatCurrency, toSupportedLocale } from '@/lib/i18n'

const { locale, t } = useI18n({ useScope: 'global' })
const router = useRouter()

const currentLocale = computed(() => toSupportedLocale(locale.value))

// KPIs + status breakdown are all-time aggregates from the DB; the recent list
// is just the latest handful for the activity card.
const { data: statsData, isPending: statsPending } = useAdminOrdersStatsApiAdminOrdersStatsGet()
const { data: recentData, isPending: recentPending } = useAdminOrdersIndexApiAdminOrdersGet({
  limit: 6,
})

const isPending = computed(() => statsPending.value || recentPending.value)
const recentOrders = computed<AdminOrderOut[]>(() => recentData.value?.data ?? [])

function openOrder(orderId: string): void {
  void router.push(`/admin/orders/${orderId}`)
}

const totalRevenue = computed(() => statsData.value?.total_revenue ?? 0)
const totalOrders = computed(() => statsData.value?.total_orders ?? 0)
const uniqueCustomers = computed(() => statsData.value?.unique_customers ?? 0)
const avgOrderValue = computed(() => statsData.value?.avg_order_value ?? 0)
const revenueSeries = computed(() => statsData.value?.revenue_last_7_days ?? [])

// Status breakdown
const ORDER_STATUSES = [
  'pending',
  'confirmed',
  'processing',
  'shipped',
  'delivered',
  'cancelled',
] as const
type OrderStatus = (typeof ORDER_STATUSES)[number]

const statusCounts = computed<Record<OrderStatus, number>>(() => {
  const counts = Object.fromEntries(ORDER_STATUSES.map((s) => [s, 0])) as Record<
    OrderStatus,
    number
  >
  const raw = statsData.value?.status_counts ?? {}
  for (const s of ORDER_STATUSES) {
    counts[s] = raw[s] ?? 0
  }
  return counts
})

const statusPercent = (s: OrderStatus): number => {
  if (totalOrders.value === 0) return 0
  return Math.round((statusCounts.value[s] / totalOrders.value) * 100)
}

// Stacked bar fills — vivid so they read as proportional segments
const statusBarFill: Record<OrderStatus, string> = {
  pending: 'var(--color-warning)',
  confirmed: 'var(--color-info)',
  processing: 'var(--color-cyan-500)',
  shipped: 'var(--color-brand)',
  delivered: 'var(--color-success)',
  cancelled: 'var(--color-danger)',
}

const statusIcon: Record<OrderStatus, string> = {
  pending: 'schedule',
  confirmed: 'check_circle',
  processing: 'autorenew',
  shipped: 'local_shipping',
  delivered: 'inventory_2',
  cancelled: 'cancel',
}

// Greeting
const greeting = computed<string>(() => {
  const h = new Date().getHours()
  if (h < 12) return t('admin.dashboard.greeting_morning')
  if (h < 18) return t('admin.dashboard.greeting_afternoon')
  return t('admin.dashboard.greeting_evening')
})

const formattedDate = computed(() =>
  new Date().toLocaleDateString(locale.value, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  }),
)
</script>

<template>
  <div class="space-y-6">
    <!-- ── Greeting header ─────────────────────────────────────────── -->
    <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-fg">{{ greeting }} 👋</h1>
        <p class="mt-0.5 text-sm text-fg-muted">{{ formattedDate }}</p>
      </div>
      <RouterLink
        to="/admin/orders"
        class="inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-hover"
      >
        <span
          class="material-symbols-outlined text-[18px] leading-none"
          style="font-variation-settings: 'FILL' 1"
          aria-hidden="true"
          >receipt_long</span
        >
        {{ t('admin.dashboard.all_orders') }}
      </RouterLink>
    </div>

    <!-- ── KPI skeleton ────────────────────────────────────────────── -->
    <div v-if="isPending" class="space-y-6">
      <div class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <div v-for="i in 4" :key="i" class="h-36 animate-pulse rounded-xl bg-app-bg-sunken" />
      </div>
      <div class="grid gap-6 lg:grid-cols-2">
        <div class="h-48 animate-pulse rounded-xl bg-app-bg-sunken" />
        <div class="h-40 animate-pulse rounded-xl bg-app-bg-sunken" />
      </div>
      <div class="grid gap-6 lg:grid-cols-2">
        <div class="h-72 animate-pulse rounded-xl bg-app-bg-sunken" />
        <div class="h-72 animate-pulse rounded-xl bg-app-bg-sunken" />
      </div>
    </div>

    <template v-else>
      <!-- ── KPI cards ───────────────────────────────────────────────── -->
      <div class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          :label="t('admin.stat.revenue')"
          :value="formatCurrency(totalRevenue, currentLocale)"
          icon="payments"
          tone="amber"
        />
        <StatCard
          :label="t('admin.stat.orders')"
          :value="String(totalOrders)"
          icon="shopping_bag"
          tone="indigo"
        />
        <StatCard
          :label="t('admin.stat.customers')"
          :value="String(uniqueCustomers)"
          icon="group"
          tone="emerald"
        />
        <StatCard
          :label="t('admin.stat.avg_order')"
          :value="formatCurrency(avgOrderValue, currentLocale)"
          icon="analytics"
          tone="violet"
        />
      </div>

      <div class="grid gap-6 lg:grid-cols-2">
        <!-- ── Order status breakdown ──────────────────────────────────── -->
        <div
          class="rounded-xl border border-[#eee] bg-admin-surface p-6 shadow-sm dark:border-border-subtle"
        >
          <div class="mb-5 flex items-center justify-between">
            <h2 class="font-semibold text-fg">{{ t('admin.dashboard.status_breakdown') }}</h2>
            <span class="text-sm text-fg-faint">
              {{ t('admin.status.total') }}:
              <strong class="font-semibold text-fg">{{ totalOrders }}</strong>
            </span>
          </div>

          <!-- stacked proportional bar -->
          <div class="flex h-3 overflow-hidden rounded-full bg-app-bg-sunken">
            <div
              v-for="s in ORDER_STATUSES"
              :key="s"
              class="transition-all duration-700"
              :style="{
                width: `${statusPercent(s)}%`,
                backgroundColor: statusBarFill[s],
              }"
            />
          </div>

          <!-- legend: 3-col on mobile (2 rows), 6-col on sm+ (1 row) -->
          <div class="mt-4 grid grid-cols-3 gap-x-4 gap-y-3 sm:grid-cols-6">
            <div v-for="s in ORDER_STATUSES" :key="s" class="flex items-center gap-2">
              <!-- material icon -->
              <span
                class="material-symbols-outlined shrink-0 text-[16px] leading-none"
                :style="{ color: statusBarFill[s] }"
                aria-hidden="true"
                >{{ statusIcon[s] }}</span
              >
              <!-- label + count -->
              <div class="min-w-0">
                <p class="truncate text-[11px] text-fg-muted">
                  {{ t(`admin.order_status.${s}`, s) }}
                </p>
                <p class="text-xs font-bold tabular-nums text-fg">
                  {{ statusCounts[s] }}
                  <span class="font-normal text-fg-faint">({{ statusPercent(s) }}%)</span>
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Revenue chart ─────────────────────────────── -->
        <RevenueBarChart :series="revenueSeries" :locale="currentLocale" />
      </div>

      <!-- ── Bottom row: recent orders + best sellers ────────────────── -->
      <div class="grid gap-6 lg:grid-cols-2">
        <RecentOrdersCard :orders="recentOrders" :locale="currentLocale" @view-order="openOrder" />
        <BestSellingList :locale="currentLocale" />
      </div>
    </template>
  </div>
</template>
