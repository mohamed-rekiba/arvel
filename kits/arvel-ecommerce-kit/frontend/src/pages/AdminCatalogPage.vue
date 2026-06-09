<script setup lang="ts">
// Rendered inside AdminLayout — the router provides the parent layout shell.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import PermissionGate from '@/components/admin/PermissionGate.vue'
import {
  useAdminCategoriesDestroyApiAdminCategoriesCategoryIdDelete,
  useAdminCategoriesForceDestroyApiAdminCategoriesCategoryIdForceDelete,
  useAdminCategoriesIndexApiAdminCategoriesGet,
  useAdminCategoriesPublishApiAdminCategoriesCategoryIdPublishPatch,
  useAdminCategoriesRestoreApiAdminCategoriesCategoryIdRestorePost,
  useAdminCategoriesUnpublishApiAdminCategoriesCategoryIdUnpublishPatch,
} from '@/api/admin-categories/admin-categories'
import {
  useAdminProductsCatalogRefreshApiAdminProductsCatalogRefreshPost,
  useAdminProductsDestroyApiAdminProductsProductIdDelete,
  useAdminProductsForceDestroyApiAdminProductsProductIdForceDelete,
  useAdminProductsIndexApiAdminProductsGet,
  useAdminProductsPublishApiAdminProductsProductIdPublishPatch,
  useAdminProductsRestoreApiAdminProductsProductIdRestorePost,
  useAdminProductsUnpublishApiAdminProductsProductIdUnpublishPatch,
} from '@/api/admin-products/admin-products'
import {
  useAdminVendorsDestroyApiAdminVendorsVendorIdDelete,
  useAdminVendorsForceDestroyApiAdminVendorsVendorIdForceDelete,
  useAdminVendorsIndexApiAdminVendorsGet,
  useAdminVendorsPublishApiAdminVendorsVendorIdPublishPatch,
  useAdminVendorsRestoreApiAdminVendorsVendorIdRestorePost,
  useAdminVendorsUnpublishApiAdminVendorsVendorIdUnpublishPatch,
} from '@/api/admin-vendors/admin-vendors'
import type {
  AdminCategoryOut,
  AdminProductOut,
  AdminProductsIndexApiAdminProductsGetParams,
  AdminVendorOut,
} from '@/api/schemas'
import { useToastStore } from '@/stores/toast'
import { pickLocalized } from '@/lib/i18n'
import type { RealStatus } from '@/types'

const { t } = useI18n({ useScope: 'global' })
const toast = useToastStore()
const router = useRouter()
const queryClient = useQueryClient()

const props = defineProps<{
  catalog: 'products' | 'categories' | 'vendors'
}>()

// Backend gates products publish on products.publish, but categories/vendors on <resource>.update.
const publishPermission = computed(() =>
  props.catalog === 'products' ? 'products.publish' : `${props.catalog}.update`,
)
const deletePermission = computed(() => `${props.catalog}.delete`)
const createPermission = computed(() => `${props.catalog}.create`)
// Edit and restore both hit <resource>.update on the backend.
const updatePermission = computed(() => `${props.catalog}.update`)

const trashedMode = ref<'without' | 'only'>('without')

const PAGE_SIZE = 50
const page = ref(0)

const isProducts = computed(() => props.catalog === 'products')
const isCategories = computed(() => props.catalog === 'categories')
const isVendors = computed(() => props.catalog === 'vendors')

watch(
  () => props.catalog,
  () => {
    page.value = 0
  },
)

const pageParams = computed<AdminProductsIndexApiAdminProductsGetParams>(() => ({
  limit: PAGE_SIZE,
  offset: page.value * PAGE_SIZE,
  trashed: trashedMode.value,
}))

const { data: productsData, isPending: loadingProducts } = useAdminProductsIndexApiAdminProductsGet(
  pageParams,
  { query: { enabled: isProducts } },
)
const { data: categoriesData, isPending: loadingCategories } =
  useAdminCategoriesIndexApiAdminCategoriesGet(pageParams, { query: { enabled: isCategories } })
const { data: vendorsData, isPending: loadingVendors } = useAdminVendorsIndexApiAdminVendorsGet(
  pageParams,
  { query: { enabled: isVendors } },
)

// Only check the active tab's query — disabled queries stay isPending:true forever in TanStack Query v5.
const loading = computed(() =>
  isProducts.value
    ? loadingProducts.value
    : isCategories.value
      ? loadingCategories.value
      : loadingVendors.value,
)

type CatalogItem = AdminProductOut | AdminCategoryOut | AdminVendorOut

const items = computed<CatalogItem[]>(() => {
  if (isProducts.value) return productsData.value?.data ?? []
  if (isCategories.value) return categoriesData.value?.data ?? []
  return vendorsData.value?.data ?? []
})

// Categories render as a parent/child tree; products/vendors stay flat (depth 0).
const rows = computed<{ item: CatalogItem; depth: number }[]>(() => {
  if (!isCategories.value) return items.value.map((item) => ({ item, depth: 0 }))

  const cats = items.value as AdminCategoryOut[]
  const childrenByParent = new Map<string | null, AdminCategoryOut[]>()
  const ids = new Set(cats.map((c) => c.id))
  for (const cat of cats) {
    // Orphans (parent not on this page) render as roots so nothing disappears.
    const parent = cat.parent_id && ids.has(cat.parent_id) ? cat.parent_id : null
    const bucket = childrenByParent.get(parent) ?? []
    bucket.push(cat)
    childrenByParent.set(parent, bucket)
  }
  const ordered: { item: CatalogItem; depth: number }[] = []
  const walk = (parent: string | null, depth: number): void => {
    for (const cat of childrenByParent.get(parent) ?? []) {
      ordered.push({ item: cat, depth })
      walk(cat.id, depth + 1)
    }
  }
  walk(null, 0)
  return ordered
})

const total = computed<number>(() => {
  if (isProducts.value) return productsData.value?.total ?? 0
  if (isCategories.value) return categoriesData.value?.total ?? 0
  return vendorsData.value?.total ?? 0
})

const totalPages = computed(() => Math.ceil(total.value / PAGE_SIZE))
const hasPrev = computed(() => page.value > 0)
const hasNext = computed(() => page.value < totalPages.value - 1)

function invalidateActive(): Promise<void> {
  const key = isProducts.value
    ? ['api', 'admin', 'products']
    : isCategories.value
      ? ['api', 'admin', 'categories']
      : ['api', 'admin', 'vendors']
  return queryClient.invalidateQueries({ queryKey: key })
}

const REAL_STATUS_LABELS = computed<Record<RealStatus, string>>(() => ({
  visible: t('admin.real_status.visible'),
  draft: t('admin.real_status.draft'),
  not_scheduled: t('admin.real_status.not_scheduled'),
  scheduled: t('admin.real_status.scheduled'),
  category_deleted: t('admin.real_status.category_deleted'),
  category_hidden: t('admin.real_status.category_hidden'),
  vendor_deleted: t('admin.real_status.vendor_deleted'),
  vendor_hidden: t('admin.real_status.vendor_hidden'),
}))

const REAL_STATUS_CLASSES: Record<RealStatus, string> = {
  visible: 'bg-status-delivered-bg text-status-delivered-fg',
  draft: 'bg-app-bg-sunken text-fg-muted',
  not_scheduled: 'bg-app-bg-sunken text-fg-muted',
  scheduled: 'bg-kpi-amber-bg text-kpi-amber-fg',
  category_deleted: 'bg-kpi-danger-bg text-kpi-danger-fg',
  category_hidden: 'bg-kpi-amber-bg text-kpi-amber-fg',
  vendor_deleted: 'bg-kpi-danger-bg text-kpi-danger-fg',
  vendor_hidden: 'bg-kpi-amber-bg text-kpi-amber-fg',
}

const title = computed(
  () =>
    ({
      products: t('admin.catalog.products'),
      categories: t('admin.catalog.categories'),
      vendors: t('admin.catalog.vendors'),
    })[props.catalog],
)

const singularTitle = computed(
  () =>
    ({
      products: t('admin.catalog.product_singular'),
      categories: t('admin.catalog.category_singular'),
      vendors: t('admin.catalog.vendor_singular'),
    })[props.catalog],
)

function itemName(item: CatalogItem): string {
  if ('name' in item && item.name !== null && typeof item.name === 'object') {
    return pickLocalized(item.name as Record<string, string>, 'en')
  }
  return typeof item.name === 'string' ? item.name : ''
}

function itemStatus(item: CatalogItem): string {
  return 'status' in item ? item.status : '—'
}

function itemStatusLabel(item: CatalogItem): string {
  const raw = itemStatus(item)
  const key = `admin.status.${raw}`
  const translated = t(key)
  return translated !== key ? translated : raw
}

function onMutationError(err: unknown): void {
  toast.error(err instanceof Error ? err.message : t('admin.catalog.op_failed'))
}

function goCreate(): void {
  void router.push(`/admin/${props.catalog}/new`)
}

function goEdit(id: string): void {
  void router.push(`/admin/${props.catalog}/${id}/edit`)
}

const { mutate: refreshCatalog, isPending: refreshing } =
  useAdminProductsCatalogRefreshApiAdminProductsCatalogRefreshPost({
    mutation: {
      onSuccess: async (result) => {
        await queryClient.invalidateQueries({ queryKey: ['api', 'admin', 'products'] })
        toast.success(t('admin.catalog.catalog_refreshed', { count: result.product_count }))
      },
      onError: onMutationError,
    },
  })

function onDeleted(): void {
  void invalidateActive()
  toast.success(t('admin.catalog.toast_deleted', { item: singularTitle.value }))
}

function onPublished(): void {
  void invalidateActive()
  toast.success(t('admin.catalog.toast_published', { item: singularTitle.value }))
}

function onUnpublished(): void {
  void invalidateActive()
  toast.success(t('admin.catalog.toast_unpublished', { item: singularTitle.value }))
}

function onRestored(): void {
  void invalidateActive()
  toast.success(t('admin.catalog.toast_restored', { item: singularTitle.value }))
}

function onForceDeleted(): void {
  void invalidateActive()
  toast.success(t('admin.catalog.force_deleted'))
}

const { mutate: deleteProduct } = useAdminProductsDestroyApiAdminProductsProductIdDelete({
  mutation: { onSuccess: onDeleted, onError: onMutationError },
})
const { mutate: deleteCategory } = useAdminCategoriesDestroyApiAdminCategoriesCategoryIdDelete({
  mutation: { onSuccess: onDeleted, onError: onMutationError },
})
const { mutate: deleteVendor } = useAdminVendorsDestroyApiAdminVendorsVendorIdDelete({
  mutation: { onSuccess: onDeleted, onError: onMutationError },
})

const { mutate: forceDeleteProduct } =
  useAdminProductsForceDestroyApiAdminProductsProductIdForceDelete({
    mutation: { onSuccess: onForceDeleted, onError: onMutationError },
  })
const { mutate: forceDeleteCategory } =
  useAdminCategoriesForceDestroyApiAdminCategoriesCategoryIdForceDelete({
    mutation: { onSuccess: onForceDeleted, onError: onMutationError },
  })
const { mutate: forceDeleteVendor } = useAdminVendorsForceDestroyApiAdminVendorsVendorIdForceDelete(
  {
    mutation: { onSuccess: onForceDeleted, onError: onMutationError },
  },
)

const { mutate: publishProduct } = useAdminProductsPublishApiAdminProductsProductIdPublishPatch({
  mutation: { onSuccess: onPublished, onError: onMutationError },
})
const { mutate: publishCategory } =
  useAdminCategoriesPublishApiAdminCategoriesCategoryIdPublishPatch({
    mutation: { onSuccess: onPublished, onError: onMutationError },
  })
const { mutate: publishVendor } = useAdminVendorsPublishApiAdminVendorsVendorIdPublishPatch({
  mutation: { onSuccess: onPublished, onError: onMutationError },
})

const { mutate: unpublishProduct } =
  useAdminProductsUnpublishApiAdminProductsProductIdUnpublishPatch({
    mutation: { onSuccess: onUnpublished, onError: onMutationError },
  })
const { mutate: unpublishCategory } =
  useAdminCategoriesUnpublishApiAdminCategoriesCategoryIdUnpublishPatch({
    mutation: { onSuccess: onUnpublished, onError: onMutationError },
  })
const { mutate: unpublishVendor } = useAdminVendorsUnpublishApiAdminVendorsVendorIdUnpublishPatch({
  mutation: { onSuccess: onUnpublished, onError: onMutationError },
})

const { mutate: restoreProduct } = useAdminProductsRestoreApiAdminProductsProductIdRestorePost({
  mutation: { onSuccess: onRestored, onError: onMutationError },
})
const { mutate: restoreCategory } =
  useAdminCategoriesRestoreApiAdminCategoriesCategoryIdRestorePost({
    mutation: { onSuccess: onRestored, onError: onMutationError },
  })
const { mutate: restoreVendor } = useAdminVendorsRestoreApiAdminVendorsVendorIdRestorePost({
  mutation: { onSuccess: onRestored, onError: onMutationError },
})

function handleDelete(id: string): void {
  if (!confirm(t('admin.catalog.delete_confirm'))) return
  if (props.catalog === 'products') deleteProduct({ productId: id })
  else if (props.catalog === 'categories') deleteCategory({ categoryId: id })
  else deleteVendor({ vendorId: id })
}

function handleForceDelete(id: string): void {
  if (!confirm(t('admin.catalog.force_delete_confirm'))) return
  if (props.catalog === 'products') forceDeleteProduct({ productId: id })
  else if (props.catalog === 'categories') forceDeleteCategory({ categoryId: id })
  else forceDeleteVendor({ vendorId: id })
}

function handlePublish(id: string): void {
  if (props.catalog === 'products') publishProduct({ productId: id })
  else if (props.catalog === 'categories') publishCategory({ categoryId: id })
  else publishVendor({ vendorId: id })
}

function handleUnpublish(id: string): void {
  if (props.catalog === 'products') unpublishProduct({ productId: id })
  else if (props.catalog === 'categories') unpublishCategory({ categoryId: id })
  else unpublishVendor({ vendorId: id })
}

function handleRestore(id: string): void {
  if (props.catalog === 'products') restoreProduct({ productId: id })
  else if (props.catalog === 'categories') restoreCategory({ categoryId: id })
  else restoreVendor({ vendorId: id })
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-fg">{{ title }}</h1>
        <p class="mt-1 text-fg-muted">{{ t('admin.catalog.items_count', { n: total }) }}</p>
      </div>
      <div class="flex items-center gap-3">
        <label
          id="trashed-mode"
          class="flex items-center gap-2 text-sm text-fg-muted cursor-pointer"
        >
          <input
            type="checkbox"
            :checked="trashedMode === 'only'"
            @change="trashedMode = trashedMode === 'only' ? 'without' : 'only'"
          />
          {{ t('admin.catalog.show_trashed', 'Show deleted') }}
        </label>
        <button
          v-if="catalog === 'products'"
          type="button"
          :disabled="refreshing"
          class="rounded-lg border border-border px-4 py-2 text-sm font-medium text-fg hover:bg-app-bg-raised disabled:opacity-50"
          @click="refreshCatalog()"
        >
          {{ refreshing ? t('admin.catalog.refreshing') : t('admin.catalog.refresh') }}
        </button>
        <PermissionGate :permission="createPermission">
          <button
            type="button"
            class="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover"
            @click="goCreate"
          >
            {{ t('admin.catalog.add', { item: singularTitle }) }}
          </button>
        </PermissionGate>
      </div>
    </div>

    <div
      class="mt-6 overflow-hidden rounded-xl border border-[#eee] bg-admin-surface shadow-sm dark:border-border-subtle"
    >
      <table class="w-full">
        <thead class="bg-app-bg-raised text-xs uppercase tracking-wide text-fg-muted">
          <tr>
            <th class="px-6 py-3 text-start">{{ t('admin.catalog.col_name') }}</th>
            <th class="px-6 py-3 text-start">{{ t('admin.catalog.col_status') }}</th>
            <th v-if="catalog === 'products'" class="px-6 py-3 text-start">
              {{ t('admin.catalog.col_visibility') }}
            </th>
            <th class="px-6 py-3 text-end">{{ t('admin.catalog.col_actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border-subtle">
          <tr v-if="loading">
            <td
              :colspan="catalog === 'products' ? 4 : 3"
              class="px-6 py-8 text-center text-fg-faint"
            >
              {{ t('admin.catalog.loading') }}
            </td>
          </tr>
          <tr
            v-for="{ item: record, depth } in rows"
            :key="record.id"
            class="hover:bg-app-bg-raised"
          >
            <td class="px-6 py-4 text-sm font-medium text-fg">
              <span :style="depth ? { paddingInlineStart: `${depth * 1.25}rem` } : undefined">
                <span v-if="depth" class="text-fg-faint" aria-hidden="true">└ </span
                >{{ itemName(record) }}
              </span>
            </td>
            <td class="px-6 py-4">
              <span
                class="inline-flex w-20 justify-center rounded-full px-[10px] py-[5px] text-xs font-medium"
                :class="
                  itemStatus(record) === 'published'
                    ? 'bg-status-delivered-bg text-status-delivered-fg'
                    : 'bg-app-bg-sunken text-fg-muted'
                "
              >
                {{ itemStatusLabel(record) }}
              </span>
            </td>
            <td v-if="catalog === 'products'" class="px-6 py-4">
              <span
                v-if="'real_status' in record && record.real_status"
                class="inline-flex w-20 justify-center rounded-full px-[10px] py-[5px] text-xs font-medium"
                :class="
                  REAL_STATUS_CLASSES[record.real_status as RealStatus] ??
                  'bg-app-bg-sunken text-fg-muted'
                "
              >
                {{
                  REAL_STATUS_LABELS[record.real_status as RealStatus] ??
                  (record.real_status as string)
                }}
              </span>
              <span v-else class="text-xs text-fg-faint">—</span>
            </td>
            <td class="px-6 py-4 text-end">
              <div class="flex justify-end gap-3">
                <PermissionGate :permission="updatePermission">
                  <button
                    type="button"
                    class="text-xs text-fg-muted hover:text-fg hover:underline"
                    @click="goEdit(record.id)"
                  >
                    {{ t('admin.catalog.action_edit') }}
                  </button>
                </PermissionGate>
                <PermissionGate :permission="publishPermission">
                  <button
                    v-if="itemStatus(record) !== 'published'"
                    type="button"
                    class="text-xs text-brand hover:underline"
                    @click="handlePublish(record.id)"
                  >
                    {{ t('admin.catalog.action_publish') }}
                  </button>
                  <button
                    v-else
                    type="button"
                    class="text-xs text-fg-muted hover:underline"
                    @click="handleUnpublish(record.id)"
                  >
                    {{ t('admin.catalog.action_unpublish') }}
                  </button>
                </PermissionGate>
                <PermissionGate :permission="updatePermission">
                  <button
                    v-if="'deleted_at' in record && record.deleted_at"
                    type="button"
                    class="text-xs text-stock-in hover:underline"
                    @click="handleRestore(record.id)"
                  >
                    {{ t('admin.catalog.action_restore') }}
                  </button>
                </PermissionGate>
                <PermissionGate :permission="deletePermission">
                  <button
                    type="button"
                    class="text-xs text-danger hover:underline"
                    @click="handleDelete(record.id)"
                  >
                    {{ t('admin.catalog.action_delete') }}
                  </button>
                  <button
                    v-if="trashedMode === 'only'"
                    type="button"
                    class="text-xs text-danger font-semibold hover:underline"
                    @click="handleForceDelete(record.id)"
                  >
                    {{ t('admin.catalog.action_force_delete', 'Force delete') }}
                  </button>
                </PermissionGate>
              </div>
            </td>
          </tr>
          <tr v-if="!loading && rows.length === 0">
            <td
              :colspan="catalog === 'products' ? 4 : 3"
              class="px-6 py-8 text-center text-fg-faint"
            >
              {{ t('admin.catalog.empty') }}
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
        &lsaquo; {{ t('admin.catalog.prev') }}
      </button>
      <span>{{
        t('admin.catalog.page_of', { page: page + 1, total: totalPages, count: total })
      }}</span>
      <button
        type="button"
        :disabled="!hasNext"
        class="rounded-lg border border-border px-4 py-2 hover:bg-app-bg-raised disabled:cursor-not-allowed disabled:opacity-40"
        @click="page++"
      >
        {{ t('admin.catalog.next') }} &rsaquo;
      </button>
    </div>
  </div>
</template>
