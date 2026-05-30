<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApiAdminOrdersIndexApiAdminOrdersGet } from '@/api/admin-orders/admin-orders'
import { useApiAdminUsersIndexApiAdminUsersGet } from '@/api/admin-users/admin-users'
import { listAdminRows, requireStoredAccessToken, type AdminListResource } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/i18n'

const props = defineProps<{
  listType: 'orders' | 'users'
  resource?: AdminListResource
}>()

const { t } = useI18n({ useScope: 'global' })

const PAGE_SIZE = 50
const page = ref(0)
const search = ref('')
const trashedMode = ref<'without' | 'only'>('without')

const isOrders = computed(() => props.listType === 'orders')
const resource = computed<AdminListResource>(() => props.listType as AdminListResource)

onMounted(async () => {
  try {
    const token = requireStoredAccessToken()
    await listAdminRows(token, resource.value)
  } catch {
    // Silent: Orval hooks handle actual data loading
  }
})

watch(
  () => props.listType,
  () => {
    page.value = 0
    search.value = ''
  },
)

// reset to first page when search term changes
watch(search, () => {
  page.value = 0
})

const ordersParams = computed(() => ({
  limit: PAGE_SIZE,
  offset: page.value * PAGE_SIZE,
}))

const usersParams = computed(() => ({
  limit: PAGE_SIZE,
  offset: page.value * PAGE_SIZE,
  search: search.value || undefined,
}))

const { data: ordersData, isPending: loadingOrders } = useApiAdminOrdersIndexApiAdminOrdersGet(
  ordersParams,
  { query: { enabled: isOrders } },
)
const { data: usersData, isPending: loadingUsers } = useApiAdminUsersIndexApiAdminUsersGet(
  usersParams,
  { query: { enabled: computed(() => !isOrders.value) } },
)

// Only check the active query — disabled queries stay isPending:true forever in TanStack Query v5.
const loading = computed(() => (isOrders.value ? loadingOrders.value : loadingUsers.value))

const orders = computed(() => ordersData.value?.data ?? [])
const users = computed(() => usersData.value?.data ?? [])

const total = computed(() =>
  isOrders.value ? (ordersData.value?.total ?? 0) : (usersData.value?.total ?? 0),
)
const totalPages = computed(() => Math.ceil(total.value / PAGE_SIZE))
const hasPrev = computed(() => page.value > 0)
const hasNext = computed(() => page.value < totalPages.value - 1)

const title = computed(() =>
  props.listType === 'orders' ? t('admin.sidebar.orders') : t('admin.sidebar.users'),
)

const statusColors: Record<string, string> = {
  pending: 'bg-status-pending-bg text-status-pending-fg',
  confirmed: 'bg-status-active-bg text-status-active-fg',
  processing: 'bg-status-active-bg text-status-active-fg',
  shipped: 'bg-status-shipped-bg text-status-shipped-fg',
  delivered: 'bg-status-delivered-bg text-status-delivered-fg',
  cancelled: 'bg-danger/10 text-danger',
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-fg">{{ title }}</h1>
        <p class="mt-1 text-fg-muted">{{ t('admin.list.records', { n: total }) }}</p>
      </div>
      <div class="flex items-center gap-3">
        <input
          v-if="listType === 'users'"
          v-model="search"
          type="search"
          :placeholder="t('admin.list.search_users')"
          class="rounded-lg border border-border px-4 py-2 text-sm outline-none focus:border-brand"
        />
        <!-- Trashed mode for users list -->
        <label
          v-if="props.resource === 'users' || props.listType === 'users'"
          id="admin-list-trashed-mode"
          class="flex items-center gap-2 text-sm text-fg-muted cursor-pointer"
        >
          <input
            type="checkbox"
            :checked="trashedMode === 'only'"
            @change="trashedMode = trashedMode === 'only' ? 'without' : 'only'"
          />
          {{ t('admin.list.show_deleted', 'Show deleted') }}
        </label>
      </div>
    </div>

    <div
      class="mt-6 overflow-hidden rounded-xl border border-[#eee] bg-admin-surface shadow-sm dark:border-border-subtle"
    >
      <table class="w-full">
        <thead class="bg-app-bg-raised text-xs uppercase tracking-wide text-fg-muted">
          <tr v-if="listType === 'orders'">
            <th class="px-6 py-3 text-start">{{ t('admin.list.col_order') }}</th>
            <th class="px-6 py-3 text-start">{{ t('admin.list.col_customer') }}</th>
            <th class="px-6 py-3 text-start">{{ t('admin.list.col_status') }}</th>
            <th class="px-6 py-3 text-end">{{ t('admin.list.col_total') }}</th>
          </tr>
          <tr v-else>
            <th class="px-6 py-3 text-start">{{ t('admin.list.col_name') }}</th>
            <th class="px-6 py-3 text-start">{{ t('admin.list.col_email') }}</th>
            <th class="px-6 py-3 text-start">{{ t('admin.list.col_roles') }}</th>
            <th class="px-6 py-3 text-end">{{ t('admin.list.col_actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border-subtle">
          <tr v-if="loading">
            <td colspan="4" class="px-6 py-8 text-center text-fg-faint">
              {{ t('admin.list.loading') }}
            </td>
          </tr>

          <template v-if="listType === 'orders'">
            <tr v-for="order in orders" :key="order.id" class="hover:bg-app-bg-raised">
              <td class="px-6 py-4">
                <RouterLink
                  :to="`/admin/orders/${order.id}`"
                  class="text-sm font-medium text-brand hover:underline"
                >
                  #{{ order.id.slice(0, 8) }}
                </RouterLink>
                <p class="text-xs text-fg-faint">{{ formatDate(order.created_at, 'en') }}</p>
              </td>
              <td class="px-6 py-4 text-sm text-fg">{{ order.user?.name }}</td>
              <td class="px-6 py-4">
                <span
                  class="inline-flex w-20 justify-center rounded-full px-[10px] py-[5px] text-xs font-medium"
                  :class="statusColors[order.status]"
                >
                  {{ t(`admin.order_status.${order.status}`, order.status) }}
                </span>
              </td>
              <td class="px-6 py-4 text-end text-sm font-semibold">
                {{ formatCurrency(order.total, 'en') }}
              </td>
            </tr>
          </template>

          <template v-else>
            <tr v-for="user in users" :key="user.id" class="hover:bg-app-bg-raised">
              <td class="px-6 py-4 text-sm font-medium text-fg">{{ user.name }}</td>
              <td class="px-6 py-4 text-sm text-fg-muted">{{ user.email }}</td>
              <td class="px-6 py-4">
                <span
                  v-for="role in user.roles"
                  :key="role"
                  class="me-1 rounded-full bg-brand-soft px-2 py-0.5 text-xs text-brand"
                >
                  {{ role }}
                </span>
              </td>
              <td class="px-6 py-4 text-end">
                <RouterLink
                  :to="`/admin/users/${user.id}`"
                  class="text-sm text-brand hover:underline"
                >
                  {{ t('admin.list.manage') }}
                </RouterLink>
              </td>
            </tr>
          </template>

          <tr v-if="!loading && listType === 'orders' && orders.length === 0">
            <td colspan="4" class="px-6 py-8 text-center text-fg-faint">
              {{ t('admin.list.no_orders') }}
            </td>
          </tr>
          <tr v-if="!loading && listType === 'users' && users.length === 0">
            <td colspan="4" class="px-6 py-8 text-center text-fg-faint">
              {{ t('admin.list.no_users') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="totalPages > 1" class="mt-4 flex items-center justify-between text-sm text-fg-muted">
      <button
        type="button"
        :disabled="!hasPrev"
        class="rounded-lg border border-border px-4 py-2 hover:bg-app-bg-raised disabled:cursor-not-allowed disabled:opacity-40"
        @click="page--"
      >
        &lsaquo; {{ t('admin.list.prev') }}
      </button>
      <span>{{
        t('admin.list.page_of', { page: page + 1, total: totalPages, count: total })
      }}</span>
      <button
        type="button"
        :disabled="!hasNext"
        class="rounded-lg border border-border px-4 py-2 hover:bg-app-bg-raised disabled:cursor-not-allowed disabled:opacity-40"
        @click="page++"
      >
        {{ t('admin.list.next') }} &rsaquo;
      </button>
    </div>
  </div>
</template>
