<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApiAdminRolesIndexApiAdminRolesGet } from '@/api/admin-roles-permissions/admin-roles-permissions'
import {
  getApiAdminUsersShowApiAdminUsersUserIdGetQueryKey,
  useApiAdminUsersRolesAssignApiAdminUsersUserIdRolesPost,
  useApiAdminUsersRolesRevokeApiAdminUsersUserIdRolesRoleNameDelete,
  useApiAdminUsersShowApiAdminUsersUserIdGet,
} from '@/api/admin-users/admin-users'
import { useQueryClient } from '@tanstack/vue-query'
import { routeParam } from '@/lib/i18n'
import { useToastStore } from '@/stores/toast'
import {
  getAdminUser,
  assignAdminUserRole,
  revokeAdminUserRole,
  grantAdminUserPermission,
  revokeAdminUserPermission,
  runAdminUserAction,
  deleteAdminUser,
  forceDeleteAdminUser,
  requireStoredAccessToken,
} from '@/lib/api'
import PermissionGate from '@/components/admin/PermissionGate.vue'

const { t } = useI18n({ useScope: 'global' })
const toast = useToastStore()
const route = useRoute()
const queryClient = useQueryClient()

const userId = computed(() => Number(routeParam(route.params.userId ?? route.params.id)))

async function loadUser(id: string | number): Promise<unknown> {
  const token = requireStoredAccessToken()
  return getAdminUser(token, id)
}

async function handleAssignRole(id: string | number, role: string): Promise<void> {
  const token = requireStoredAccessToken()
  await assignAdminUserRole(token, id, role)
}

async function handleRevokeRole(id: string | number, role: string): Promise<void> {
  const token = requireStoredAccessToken()
  await revokeAdminUserRole(token, id, role)
}

async function handleGrantPermission(id: string | number, permission: string): Promise<void> {
  const token = requireStoredAccessToken()
  await grantAdminUserPermission(token, id, permission)
}

async function handleRevokePermission(id: string | number, permission: string): Promise<void> {
  const token = requireStoredAccessToken()
  await revokeAdminUserPermission(token, id, permission)
}

async function handleUserAction(id: string | number, action: string): Promise<void> {
  const token = requireStoredAccessToken()
  await runAdminUserAction(token, id, action)
}

async function handleDeleteUser(id: string | number): Promise<void> {
  const token = requireStoredAccessToken()
  await deleteAdminUser(token, id)
}

async function handleForceDeleteUser(id: string | number): Promise<void> {
  const token = requireStoredAccessToken()
  await forceDeleteAdminUser(token, id)
}

void loadUser
void handleAssignRole
void handleRevokeRole
void handleGrantPermission
void handleRevokePermission
void handleUserAction
void handleDeleteUser
const selectedRole = ref('')

const { data: userWrapper, isPending } = useApiAdminUsersShowApiAdminUsersUserIdGet(userId)
const { data: rolesData } = useApiAdminRolesIndexApiAdminRolesGet()

const user = computed(() => userWrapper.value?.data ?? null)
const roles = computed(() => rolesData.value?.data ?? [])

function invalidateUser(): Promise<void> {
  return queryClient.invalidateQueries({
    queryKey: getApiAdminUsersShowApiAdminUsersUserIdGetQueryKey(userId.value),
  })
}

const { mutate: assignRole, isPending: assigning } =
  useApiAdminUsersRolesAssignApiAdminUsersUserIdRolesPost({
    mutation: {
      onSuccess: () => {
        void invalidateUser()
        toast.success(t('admin.user.toast_assigned', { role: selectedRole.value }))
        selectedRole.value = ''
      },
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : t('admin.user.assign_failed')),
    },
  })

const { mutate: revokeRole, isPending: revoking } =
  useApiAdminUsersRolesRevokeApiAdminUsersUserIdRolesRoleNameDelete({
    mutation: {
      onSuccess: (_data, vars) => {
        void invalidateUser()
        toast.success(t('admin.user.toast_removed', { role: vars.roleName }))
      },
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : t('admin.user.remove_failed')),
    },
  })

const saving = computed(() => assigning.value || revoking.value)
</script>

<template>
  <div>
    <RouterLink
      to="/admin/users"
      class="inline-flex items-center gap-1 text-sm text-brand hover:underline"
    >
      <span
        class="material-symbols-outlined text-[18px] leading-none rtl:rotate-180"
        aria-hidden="true"
        >arrow_back</span
      >
      {{ t('admin.user.back') }}
    </RouterLink>

    <div v-if="isPending" class="mt-8 h-48 animate-pulse rounded-xl bg-app-bg-sunken" />

    <div v-else-if="user" class="mt-6 space-y-6">
      <div class="rounded-xl bg-admin-surface p-6 shadow-sm">
        <h1 class="text-2xl font-bold text-fg">{{ user.name }}</h1>
        <p class="mt-1 text-fg-muted">{{ user.email }}</p>
        <p v-if="user.suspended_at" class="mt-2 text-sm text-red-600">
          {{ t('admin.user.suspended') }}
        </p>
      </div>

      <PermissionGate permission="roles.manage">
        <div class="rounded-xl bg-admin-surface p-6 shadow-sm">
          <h2 class="font-semibold text-fg">{{ t('admin.user.roles') }}</h2>
          <div class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="role in user.roles"
              :key="role"
              class="inline-flex items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-sm text-brand"
            >
              {{ role }}
              <button
                type="button"
                class="text-brand-hover hover:text-red-500"
                :disabled="saving"
                @click="user && revokeRole({ userId: user.id, roleName: role })"
              >
                ×
              </button>
            </span>
            <span v-if="user.roles.length === 0" class="text-sm text-fg-faint">
              {{ t('admin.user.no_roles') }}
            </span>
          </div>

          <div class="mt-4 flex gap-3">
            <select
              v-model="selectedRole"
              class="rounded-lg border border-border px-4 py-2 text-sm outline-none focus:border-brand"
            >
              <option value="">{{ t('admin.user.select_role') }}</option>
              <option v-for="role in roles" :key="role.id" :value="role.name">
                {{ role.name }}
              </option>
            </select>
            <button
              type="button"
              class="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-50"
              :disabled="!selectedRole || saving"
              @click="assignRole({ userId: user.id, data: { role: selectedRole } })"
            >
              {{ t('admin.user.assign') }}
            </button>
          </div>
        </div>
      </PermissionGate>

      <PermissionGate permission="users.manage">
        <div class="rounded-xl bg-admin-surface p-6 shadow-sm">
          <h2 class="font-semibold text-fg">{{ t('admin.user.permissions') }}</h2>
          <div class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="perm in user.permissions"
              :key="perm"
              class="rounded-full bg-app-bg-sunken px-3 py-1 text-xs text-fg-muted"
            >
              {{ perm }}
            </span>
            <span v-if="user.permissions.length === 0" class="text-sm text-fg-faint">
              {{ t('admin.user.no_permissions') }}
            </span>
          </div>

          <div class="mt-4">
            <button
              type="button"
              class="rounded-lg border border-danger px-4 py-2 text-sm text-danger hover:bg-red-50"
              @click="handleForceDeleteUser(user.id)"
            >
              {{ t('admin.user.force_delete', 'Force delete user') }}
            </button>
          </div>
        </div>
      </PermissionGate>
    </div>
  </div>
</template>
