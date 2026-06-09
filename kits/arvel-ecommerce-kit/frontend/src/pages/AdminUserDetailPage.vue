<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAdminRolesIndexApiAdminRolesGet } from '@/api/admin-roles-permissions/admin-roles-permissions'
import {
  getAdminUsersIndexApiAdminUsersGetQueryKey,
  getAdminUsersShowApiAdminUsersUserIdGetQueryKey,
  useAdminUsersForceDestroyApiAdminUsersUserIdForceDelete,
  useAdminUsersRolesAssignApiAdminUsersUserIdRolesPost,
  useAdminUsersRolesRevokeApiAdminUsersUserIdRolesDelete,
  useAdminUsersShowApiAdminUsersUserIdGet,
} from '@/api/admin-users/admin-users'
import { useQueryClient } from '@tanstack/vue-query'
import { routeParam } from '@/lib/i18n'
import { useToastStore } from '@/stores/toast'
import PermissionGate from '@/components/admin/PermissionGate.vue'

const { t } = useI18n({ useScope: 'global' })
const toast = useToastStore()
const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

const userId = computed(() => Number(routeParam(route.params.userId ?? route.params.id)))
const selectedRole = ref('')

const { data: userWrapper, isPending } = useAdminUsersShowApiAdminUsersUserIdGet(userId)
const { data: rolesData } = useAdminRolesIndexApiAdminRolesGet()

const user = computed(() => userWrapper.value?.data ?? null)
const roles = computed(() => rolesData.value?.data ?? [])

function invalidateUser(): Promise<void> {
  return queryClient.invalidateQueries({
    queryKey: getAdminUsersShowApiAdminUsersUserIdGetQueryKey(userId.value),
  })
}

const { mutate: assignRole, isPending: assigning } =
  useAdminUsersRolesAssignApiAdminUsersUserIdRolesPost({
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
  useAdminUsersRolesRevokeApiAdminUsersUserIdRolesDelete({
    mutation: {
      onSuccess: (_data, vars) => {
        void invalidateUser()
        toast.success(t('admin.user.toast_removed', { role: vars.params.role_name }))
      },
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : t('admin.user.remove_failed')),
    },
  })

const { mutate: forceDelete, isPending: deleting } =
  useAdminUsersForceDestroyApiAdminUsersUserIdForceDelete({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: getAdminUsersIndexApiAdminUsersGetQueryKey(),
        })
        toast.success(t('admin.user.toast_force_deleted'))
        void router.push('/admin/users')
      },
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : t('admin.user.force_delete_failed')),
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
                @click="user && revokeRole({ userId: user.id, params: { role_name: role } })"
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

          <PermissionGate permission="users.manage" :min-level="100">
            <div class="mt-4">
              <button
                type="button"
                class="rounded-lg border border-danger px-4 py-2 text-sm text-danger hover:bg-red-50 disabled:opacity-50"
                :disabled="deleting"
                @click="forceDelete({ userId: user.id })"
              >
                {{ t('admin.user.force_delete', 'Force delete user') }}
              </button>
            </div>
          </PermissionGate>
        </div>
      </PermissionGate>
    </div>
  </div>
</template>
