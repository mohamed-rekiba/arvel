<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  adminRolesPermissionsIndexApiAdminRolesPermissionsGet,
  adminRolesIndexApiAdminRolesGet,
} from '@/api/admin-roles-permissions/admin-roles-permissions'
import { adminTranslationsIndexApiAdminTranslationsGet } from '@/api/admin-translations/admin-translations'
import type { PermissionOut, RoleOut, TranslationEntryOut } from '@/api/schemas'
import { pickLocalized } from '@/lib/i18n'

const props = defineProps<{
  pageType: 'roles' | 'translations' | 'coming-soon'
  title?: string
}>()

const { t } = useI18n({ useScope: 'global' })

const roles = ref<RoleOut[]>([])
const permissions = ref<PermissionOut[]>([])
const translations = ref<TranslationEntryOut[]>([])
const loading = ref(props.pageType !== 'coming-soon')

const heading = computed(() => {
  if (props.pageType === 'roles') return t('admin.placeholder.roles_perms')
  if (props.pageType === 'translations') return t('admin.placeholder.translations')
  return props.title ?? ''
})

onMounted(async () => {
  if (props.pageType === 'coming-soon') return
  try {
    if (props.pageType === 'roles') {
      const [rolesOut, permsOut] = await Promise.all([
        adminRolesIndexApiAdminRolesGet(),
        adminRolesPermissionsIndexApiAdminRolesPermissionsGet(),
      ])
      roles.value = rolesOut.data
      permissions.value = permsOut.data
    } else {
      translations.value = (await adminTranslationsIndexApiAdminTranslationsGet()).data
    }
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-fg">{{ heading }}</h1>

    <div
      v-if="pageType === 'coming-soon'"
      class="mt-8 flex flex-col items-center justify-center rounded-xl border border-dashed border-border-subtle bg-admin-surface px-6 py-16 text-center"
    >
      <span class="material-symbols-outlined text-4xl text-fg-faint" aria-hidden="true"
        >hourglass_empty</span
      >
      <p class="mt-4 text-sm text-fg-muted">{{ t('admin.placeholder.coming_soon') }}</p>
    </div>

    <div v-else-if="loading" class="mt-8 h-48 animate-pulse rounded-xl bg-app-bg-sunken" />

    <template v-else-if="pageType === 'roles'">
      <div class="mt-6 grid gap-6 lg:grid-cols-2">
        <div class="rounded-xl bg-admin-surface p-6 shadow-sm">
          <h2 class="font-semibold text-fg">{{ t('admin.placeholder.roles') }}</h2>
          <ul class="mt-4 divide-y divide-border-subtle">
            <li v-for="role in roles" :key="role.id" class="flex justify-between py-3 text-sm">
              <span class="font-medium">{{ role.name }}</span>
              <span class="text-fg-faint">{{
                t('admin.placeholder.level', { level: role.level })
              }}</span>
            </li>
            <li v-if="roles.length === 0" class="py-4 text-fg-faint">
              {{ t('admin.placeholder.no_roles') }}
            </li>
          </ul>
        </div>
        <div class="rounded-xl bg-admin-surface p-6 shadow-sm">
          <h2 class="font-semibold text-fg">{{ t('admin.placeholder.permissions') }}</h2>
          <ul class="mt-4 flex flex-wrap gap-2">
            <li
              v-for="perm in permissions"
              :key="perm.id"
              class="rounded-full bg-app-bg-sunken px-3 py-1 text-xs text-fg-muted"
            >
              {{ perm.name }}
            </li>
            <li v-if="permissions.length === 0" class="text-fg-faint">
              {{ t('admin.placeholder.no_permissions') }}
            </li>
          </ul>
        </div>
      </div>
    </template>

    <template v-else>
      <div
        class="mt-6 overflow-hidden rounded-xl border border-[#eee] bg-admin-surface shadow-sm dark:border-border-subtle"
      >
        <table class="w-full">
          <thead class="bg-app-bg-raised text-xs uppercase tracking-wide text-fg-muted">
            <tr>
              <th class="px-6 py-3 text-start">{{ t('admin.placeholder.col_model') }}</th>
              <th class="px-6 py-3 text-start">{{ t('admin.placeholder.col_id') }}</th>
              <th class="px-6 py-3 text-start">{{ t('admin.placeholder.col_fields') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border-subtle">
            <tr
              v-for="entry in translations"
              :key="`${entry.model}-${entry.id}`"
              class="hover:bg-app-bg-raised"
            >
              <td class="px-6 py-4 text-sm capitalize">{{ entry.model }}</td>
              <td class="px-6 py-4 text-sm font-mono text-fg-muted">{{ entry.id.slice(0, 8) }}</td>
              <td class="px-6 py-4 text-sm text-fg">
                <span v-for="(value, key) in entry.fields" :key="key" class="me-3">
                  <strong>{{ key }}:</strong> {{ pickLocalized(value, 'en') }}
                </span>
              </td>
            </tr>
            <tr v-if="translations.length === 0">
              <td colspan="3" class="px-6 py-8 text-center text-fg-faint">
                {{ t('admin.placeholder.no_translations') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
