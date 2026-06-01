<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAdminRolesIndexApiAdminRolesGet } from '@/api/admin-roles-permissions/admin-roles-permissions'

const { t } = useI18n({ useScope: 'global' })

const { data, isPending } = useAdminRolesIndexApiAdminRolesGet()
const roles = computed(() => data.value?.data ?? [])

const levelLabel = computed<Record<number, { label: string; classes: string }>>(() => ({
  100: { label: t('admin.roles.super_admin'), classes: 'bg-danger/10 text-danger' },
  80: { label: t('admin.roles.admin'), classes: 'bg-status-shipped-bg text-status-shipped-fg' },
  60: { label: t('admin.roles.manager'), classes: 'bg-kpi-amber-bg text-kpi-amber-fg' },
  40: { label: t('admin.roles.support'), classes: 'bg-app-bg-sunken text-fg-muted' },
}))
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-fg">{{ t('admin.roles.title') }}</h1>
    <p class="mt-1 text-fg-muted">{{ t('admin.roles.summary', { count: roles.length }) }}</p>

    <div v-if="isPending" class="mt-6 space-y-3">
      <div v-for="i in 5" :key="i" class="h-14 animate-pulse rounded-lg bg-app-bg-sunken" />
    </div>

    <div
      v-else-if="!isPending"
      class="mt-6 overflow-hidden rounded-xl border border-[#eee] bg-admin-surface shadow-sm dark:border-border-subtle"
    >
      <table class="w-full">
        <thead class="bg-app-bg-raised text-xs uppercase tracking-wide text-fg-muted">
          <tr>
            <th class="px-6 py-3 text-start">{{ t('admin.roles.col_role') }}</th>
            <th class="px-6 py-3 text-start">{{ t('admin.roles.col_guard') }}</th>
            <th class="px-6 py-3 text-center">{{ t('admin.roles.col_level') }}</th>
            <th class="px-6 py-3 text-start">{{ t('admin.roles.col_access') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border-subtle">
          <tr v-for="role in roles" :key="role.id" class="hover:bg-app-bg-raised">
            <td class="px-6 py-4 font-medium text-fg">{{ role.name }}</td>
            <td class="px-6 py-4 font-mono text-sm text-fg-muted">{{ role.guard_name }}</td>
            <td class="px-6 py-4 text-center">
              <span
                class="rounded-full px-2 py-0.5 text-xs font-semibold"
                :class="(levelLabel[role.level] ?? levelLabel[40]).classes"
              >
                {{ role.level }}
              </span>
            </td>
            <td class="px-6 py-4 text-sm text-fg-muted">
              {{ (levelLabel[role.level] ?? { label: role.name }).label }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
