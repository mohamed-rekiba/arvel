<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import ArvelLogo from '@/components/ArvelLogo.vue'

const props = defineProps<{
  collapsed: boolean
}>()

const emit = defineEmits<{
  toggle: []
  logout: []
}>()

const { t } = useI18n({ useScope: 'global' })
const route = useRoute()
const auth = useAuthStore()

interface NavItem {
  label: string
  to: string
  icon: string
  permission?: string
}

const navItems = computed<NavItem[]>(() => [
  { label: t('admin.sidebar.dashboard'), to: '/admin/dashboard', icon: 'dashboard' },
  {
    label: t('admin.sidebar.products'),
    to: '/admin/products',
    icon: 'inventory_2',
    permission: 'products.view',
  },
  {
    label: t('admin.sidebar.categories'),
    to: '/admin/categories',
    icon: 'label',
    permission: 'products.view',
  },
  {
    label: t('admin.sidebar.vendors'),
    to: '/admin/vendors',
    icon: 'storefront',
    permission: 'products.view',
  },
  {
    label: t('admin.sidebar.orders'),
    to: '/admin/orders',
    icon: 'shopping_bag',
    permission: 'orders.view',
  },
  {
    label: t('admin.sidebar.users'),
    to: '/admin/users',
    icon: 'group',
    permission: 'users.manage',
  },
  {
    label: t('admin.sidebar.roles'),
    to: '/admin/roles',
    icon: 'admin_panel_settings',
    permission: 'roles.manage',
  },
])

const visibleItems = computed(() =>
  navItems.value.filter((item) => !item.permission || auth.hasPermission(item.permission)),
)

function isActive(path: string): boolean {
  return route.path === path || route.path.startsWith(`${path}/`)
}
</script>

<template>
  <aside
    class="sticky top-0 flex h-screen shrink-0 flex-col bg-admin-sidebar-bg transition-all duration-200"
    :style="{
      width: props.collapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)',
      borderRight: '1px solid var(--color-admin-sidebar-border)',
    }"
  >
    <!-- Logo / wordmark area -->
    <div
      class="shrink-0 flex flex-col items-center px-3 pb-3 pt-4"
      :style="{ borderBottom: '1px solid var(--color-admin-sidebar-border)' }"
    >
      <template v-if="!props.collapsed">
        <RouterLink
          to="/"
          class="group flex items-center gap-2 rounded-lg px-2 py-2 transition hover:bg-admin-sidebar-bg-hover"
          title="Back to storefront"
        >
          <ArvelLogo variant="dark" :height="50" />
        </RouterLink>
        <div class="mt-2 px-2">
          <span
            class="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest"
            :style="{
              background: 'var(--color-admin-sidebar-bg-hover)',
              color: 'var(--color-admin-sidebar-muted)',
            }"
          >
            {{ t('admin.sidebar.admin_panel') }}
          </span>
        </div>
      </template>

      <RouterLink
        v-else
        to="/"
        class="flex justify-center rounded-lg py-2 transition hover:bg-admin-sidebar-bg-hover"
        title="Back to storefront"
      >
        <ArvelLogo variant="mark-only" :height="50" />
      </RouterLink>
    </div>

    <!-- Nav items -->
    <nav class="flex-1 space-y-0.5 overflow-y-auto p-3">
      <RouterLink
        v-for="item in visibleItems"
        :key="item.to"
        :to="item.to"
        class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition"
        :class="
          isActive(item.to)
            ? 'bg-admin-sidebar-bg-active text-admin-sidebar-active-text'
            : 'text-admin-sidebar-text hover:bg-admin-sidebar-bg-hover'
        "
        :title="props.collapsed ? item.label : undefined"
      >
        <span
          class="material-symbols-outlined select-none text-[22px] leading-none"
          :style="isActive(item.to) ? '' : 'color: var(--color-admin-accent)'"
          aria-hidden="true"
        >
          {{ item.icon }}
        </span>
        <span v-if="!props.collapsed" class="truncate">{{ item.label }}</span>
      </RouterLink>
    </nav>

    <!-- Collapse toggle + logout -->
    <div
      class="p-3 space-y-1"
      :style="{ borderTop: '1px solid var(--color-admin-sidebar-border)' }"
    >
      <button
        type="button"
        class="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm transition text-admin-sidebar-muted hover:bg-admin-sidebar-bg-hover hover:text-admin-sidebar-text"
        @click="emit('logout')"
      >
        <span
          class="material-symbols-outlined select-none text-[20px] leading-none"
          aria-hidden="true"
          >logout</span
        >
        <span v-if="!props.collapsed">{{ t('admin.sidebar.logout', 'Sign out') }}</span>
      </button>
      <button
        type="button"
        class="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm transition text-admin-sidebar-muted hover:bg-admin-sidebar-bg-hover hover:text-admin-sidebar-text"
        @click="emit('toggle')"
      >
        <span
          class="material-symbols-outlined select-none text-[20px] leading-none"
          aria-hidden="true"
        >
          {{ props.collapsed ? 'chevron_right' : 'chevron_left' }}
        </span>
        <span v-if="!props.collapsed">{{ t('admin.sidebar.collapse') }}</span>
      </button>
    </div>
  </aside>
</template>
