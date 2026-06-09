<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  useAdminRolesPermissionsIndexApiAdminRolesPermissionsGet,
  useAdminRolesIndexApiAdminRolesGet,
} from '@/api/admin-roles-permissions/admin-roles-permissions'
import type { PermissionOut } from '@/api/schemas'

const { t } = useI18n({ useScope: 'global' })

const { data: permsData, isPending: permsPending } =
  useAdminRolesPermissionsIndexApiAdminRolesPermissionsGet()
const { data: rolesData, isPending: rolesPending } = useAdminRolesIndexApiAdminRolesGet()

const isPending = computed(() => permsPending.value || rolesPending.value)
const permissions = computed(() => permsData.value?.data ?? [])
const roles = computed(() => rolesData.value?.data ?? [])

// Group permissions by their domain prefix (e.g. "products.view" → "products").
function domain(name: string): string {
  return name.split('.')[0]
}

const domains = computed(() => {
  const set = new Set<string>()
  permissions.value.forEach((p) => set.add(domain(p.name)))
  return set
})

function byDomain(d: string): PermissionOut[] {
  return permissions.value.filter((p) => domain(p.name) === d)
}
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-fg">{{ t('admin.perms.title') }}</h1>
    <p class="mt-1 text-fg-muted">
      {{ t('admin.perms.summary', { count: permissions.length, domains: domains.size }) }}
    </p>

    <div v-if="isPending" class="mt-6 space-y-3">
      <div v-for="i in 6" :key="i" class="h-10 animate-pulse rounded-lg bg-app-bg-sunken" />
    </div>

    <div v-else-if="!isPending" class="mt-6 space-y-6">
      <div
        v-for="d in [...domains].sort()"
        :key="d"
        class="overflow-hidden rounded-xl border border-[#eee] bg-admin-surface shadow-sm dark:border-border-subtle"
      >
        <div class="border-b border-border px-6 py-3">
          <h2 class="text-sm font-semibold capitalize text-fg">{{ d }}</h2>
        </div>
        <table class="w-full">
          <thead class="bg-app-bg-raised text-xs uppercase tracking-wide text-fg-muted">
            <tr>
              <th class="px-6 py-3 text-start">{{ t('admin.perms.col_permission') }}</th>
              <th v-for="role in roles" :key="role.id" class="px-4 py-3 text-center">
                {{ role.name }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border-subtle">
            <tr v-for="perm in byDomain(d)" :key="perm.id" class="hover:bg-app-bg-raised">
              <td class="px-6 py-3 font-mono text-sm text-fg">{{ perm.name }}</td>
              <td v-for="role in roles" :key="role.id" class="px-4 py-3 text-center">
                <span v-if="(role.permissions ?? []).includes(perm.name)" class="text-stock-in"
                  >✓</span
                >
                <span v-else class="text-fg-faint">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
