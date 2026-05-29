<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  useApiAdminCategoriesDestroyApiAdminCategoriesCategoryIdDelete,
  useApiAdminCategoriesIndexApiAdminCategoriesGet,
  useApiAdminCategoriesPublishApiAdminCategoriesCategoryIdPublishPatch,
  useApiAdminCategoriesRestoreApiAdminCategoriesCategoryIdRestorePost,
  useApiAdminCategoriesStoreApiAdminCategoriesPost,
  useApiAdminCategoriesUnpublishApiAdminCategoriesCategoryIdUnpublishPatch,
  useApiAdminCategoriesUpdateApiAdminCategoriesCategoryIdPatch,
} from '@/api/admin-categories/admin-categories'
import {
  useApiAdminProductsCatalogRefreshApiAdminProductsCatalogRefreshPost,
  useApiAdminProductsDestroyApiAdminProductsProductIdDelete,
  useApiAdminProductsIndexApiAdminProductsGet,
  useApiAdminProductsPublishApiAdminProductsProductIdPublishPatch,
  useApiAdminProductsRestoreApiAdminProductsProductIdRestorePost,
  useApiAdminProductsStoreApiAdminProductsPost,
  useApiAdminProductsUnpublishApiAdminProductsProductIdUnpublishPatch,
  useApiAdminProductsUpdateApiAdminProductsProductIdPatch,
} from '@/api/admin-products/admin-products'
import {
  useApiAdminVendorsDestroyApiAdminVendorsVendorIdDelete,
  useApiAdminVendorsIndexApiAdminVendorsGet,
  useApiAdminVendorsPublishApiAdminVendorsVendorIdPublishPatch,
  useApiAdminVendorsRestoreApiAdminVendorsVendorIdRestorePost,
  useApiAdminVendorsStoreApiAdminVendorsPost,
  useApiAdminVendorsUnpublishApiAdminVendorsVendorIdUnpublishPatch,
  useApiAdminVendorsUpdateApiAdminVendorsVendorIdPatch,
} from '@/api/admin-vendors/admin-vendors'
import type { AdminCategoryOut, AdminVendorOut } from '@/api/schemas'
import { useQueryClient } from '@tanstack/vue-query'
import TranslatableInput from '@/components/admin/TranslatableInput.vue'
import { useToastStore } from '@/stores/toast'
import { pickLocalized } from '@/lib/i18n'
import type { AdminProductWithStatus, LocalizedText, RealStatus } from '@/types'

const { t } = useI18n({ useScope: 'global' })
const toast = useToastStore()
const queryClient = useQueryClient()

const props = defineProps<{
  catalog: 'products' | 'categories' | 'vendors'
}>()

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

const pageParams = computed(() => ({ limit: PAGE_SIZE, offset: page.value * PAGE_SIZE }))

const { data: productsData, isPending: loadingProducts } =
  useApiAdminProductsIndexApiAdminProductsGet(pageParams, { query: { enabled: isProducts } })
const { data: categoriesData, isPending: loadingCategories } =
  useApiAdminCategoriesIndexApiAdminCategoriesGet(pageParams, { query: { enabled: isCategories } })
const { data: vendorsData, isPending: loadingVendors } = useApiAdminVendorsIndexApiAdminVendorsGet(
  pageParams,
  { query: { enabled: isVendors } },
)
// high limit so all options appear in the product-form selects
const { data: allCategoriesData } = useApiAdminCategoriesIndexApiAdminCategoriesGet({ limit: 500 })
const { data: allVendorsData } = useApiAdminVendorsIndexApiAdminVendorsGet({ limit: 500 })

// Only check the active tab's query — disabled queries stay isPending:true forever in TanStack Query v5.
const loading = computed(() =>
  isProducts.value
    ? loadingProducts.value
    : isCategories.value
      ? loadingCategories.value
      : loadingVendors.value,
)

type CatalogItem = AdminProductWithStatus | AdminCategoryOut | AdminVendorOut

const items = computed<CatalogItem[]>(() => {
  if (isProducts.value) return (productsData.value?.data ?? []) as AdminProductWithStatus[]
  if (isCategories.value) return categoriesData.value?.data ?? []
  return vendorsData.value?.data ?? []
})

const total = computed<number>(() => {
  if (isProducts.value) return productsData.value?.total ?? 0
  if (isCategories.value) return categoriesData.value?.total ?? 0
  return vendorsData.value?.total ?? 0
})

const totalPages = computed(() => Math.ceil(total.value / PAGE_SIZE))
const hasPrev = computed(() => page.value > 0)
const hasNext = computed(() => page.value < totalPages.value - 1)

const allCategories = computed(() => allCategoriesData.value?.data ?? [])
const allVendors = computed(() => allVendorsData.value?.data ?? [])

function invalidateActive(): Promise<void> {
  // prefix match — invalidates all pages of the active catalog
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

const showForm = ref(false)
const editingId = ref<string | null>(null)
const error = ref<string | null>(null)

const productForm = reactive({
  name: { en: '', ar: '', tr: '' } as LocalizedText,
  slug: { en: '', ar: '', tr: '' } as LocalizedText,
  description: { en: '', ar: '', tr: '' } as LocalizedText,
  price: 0,
  stock_qty: 0,
  category_id: '',
  vendor_id: '',
})

const categoryForm = reactive({
  name: { en: '', ar: '', tr: '' } as LocalizedText,
  slug: { en: '', ar: '', tr: '' } as LocalizedText,
})

const vendorForm = reactive({
  name: '',
  slug: '',
  description: '',
})

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
  // AdminVendorOut.name is a plain string
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

function resetForm(): void {
  editingId.value = null
  error.value = null
  Object.assign(productForm, {
    name: { en: '', ar: '', tr: '' },
    slug: { en: '', ar: '', tr: '' },
    description: { en: '', ar: '', tr: '' },
    price: 0,
    stock_qty: 0,
    category_id: '',
    vendor_id: '',
  })
  Object.assign(categoryForm, {
    name: { en: '', ar: '', tr: '' },
    slug: { en: '', ar: '', tr: '' },
  })
  Object.assign(vendorForm, { name: '', slug: '', description: '' })
}

function openCreate(): void {
  resetForm()
  showForm.value = true
}

async function onMutationSuccess(label: string): Promise<void> {
  showForm.value = false
  resetForm()
  await invalidateActive()
  toast.success(label)
}

function onMutationError(err: unknown): void {
  const msg = err instanceof Error ? err.message : t('admin.catalog.op_failed')
  error.value = msg
  toast.error(msg)
}

// Catalog refresh
const { mutate: refreshCatalog, isPending: refreshing } =
  useApiAdminProductsCatalogRefreshApiAdminProductsCatalogRefreshPost({
    mutation: {
      onSuccess: async (result) => {
        await queryClient.invalidateQueries({
          queryKey: ['api', 'admin', 'products'],
        })
        toast.success(t('admin.catalog.catalog_refreshed', { count: result.product_count }))
      },
      onError: onMutationError,
    },
  })

// Create mutations
const { mutate: createProduct, isPending: creatingProduct } =
  useApiAdminProductsStoreApiAdminProductsPost({
    mutation: {
      onSuccess: () =>
        onMutationSuccess(t('admin.catalog.toast_created', { item: singularTitle.value })),
      onError: onMutationError,
    },
  })

const { mutate: createCategory, isPending: creatingCategory } =
  useApiAdminCategoriesStoreApiAdminCategoriesPost({
    mutation: {
      onSuccess: () =>
        onMutationSuccess(t('admin.catalog.toast_created', { item: singularTitle.value })),
      onError: onMutationError,
    },
  })

const { mutate: createVendor, isPending: creatingVendor } =
  useApiAdminVendorsStoreApiAdminVendorsPost({
    mutation: {
      onSuccess: () =>
        onMutationSuccess(t('admin.catalog.toast_created', { item: singularTitle.value })),
      onError: onMutationError,
    },
  })

// Update mutations
const { mutate: updateProduct, isPending: updatingProduct } =
  useApiAdminProductsUpdateApiAdminProductsProductIdPatch({
    mutation: {
      onSuccess: () => onMutationSuccess(t('admin.catalog.toast_saved')),
      onError: onMutationError,
    },
  })

const { mutate: updateCategory, isPending: updatingCategory } =
  useApiAdminCategoriesUpdateApiAdminCategoriesCategoryIdPatch({
    mutation: {
      onSuccess: () => onMutationSuccess(t('admin.catalog.toast_saved')),
      onError: onMutationError,
    },
  })

const { mutate: updateVendor, isPending: updatingVendor } =
  useApiAdminVendorsUpdateApiAdminVendorsVendorIdPatch({
    mutation: {
      onSuccess: () => onMutationSuccess(t('admin.catalog.toast_saved')),
      onError: onMutationError,
    },
  })

// Delete mutations
const { mutate: deleteProduct } = useApiAdminProductsDestroyApiAdminProductsProductIdDelete({
  mutation: {
    onSuccess: async () => {
      await invalidateActive()
      toast.success(t('admin.catalog.toast_deleted', { item: singularTitle.value }))
    },
    onError: onMutationError,
  },
})

const { mutate: deleteCategory } = useApiAdminCategoriesDestroyApiAdminCategoriesCategoryIdDelete({
  mutation: {
    onSuccess: async () => {
      await invalidateActive()
      toast.success(t('admin.catalog.toast_deleted', { item: singularTitle.value }))
    },
    onError: onMutationError,
  },
})

const { mutate: deleteVendor } = useApiAdminVendorsDestroyApiAdminVendorsVendorIdDelete({
  mutation: {
    onSuccess: async () => {
      await invalidateActive()
      toast.success(t('admin.catalog.toast_deleted', { item: singularTitle.value }))
    },
    onError: onMutationError,
  },
})

// Publish mutations
const { mutate: publishProduct } = useApiAdminProductsPublishApiAdminProductsProductIdPublishPatch({
  mutation: {
    onSuccess: async () => {
      await invalidateActive()
      toast.success(t('admin.catalog.toast_published', { item: singularTitle.value }))
    },
    onError: onMutationError,
  },
})

const { mutate: publishCategory } =
  useApiAdminCategoriesPublishApiAdminCategoriesCategoryIdPublishPatch({
    mutation: {
      onSuccess: async () => {
        await invalidateActive()
        toast.success(t('admin.catalog.toast_published', { item: singularTitle.value }))
      },
      onError: onMutationError,
    },
  })

const { mutate: publishVendor } = useApiAdminVendorsPublishApiAdminVendorsVendorIdPublishPatch({
  mutation: {
    onSuccess: async () => {
      await invalidateActive()
      toast.success(t('admin.catalog.toast_published', { item: singularTitle.value }))
    },
    onError: onMutationError,
  },
})

const { mutate: unpublishProduct } =
  useApiAdminProductsUnpublishApiAdminProductsProductIdUnpublishPatch({
    mutation: {
      onSuccess: async () => {
        await invalidateActive()
        toast.success(t('admin.catalog.toast_unpublished', { item: singularTitle.value }))
      },
      onError: onMutationError,
    },
  })

const { mutate: unpublishCategory } =
  useApiAdminCategoriesUnpublishApiAdminCategoriesCategoryIdUnpublishPatch({
    mutation: {
      onSuccess: async () => {
        await invalidateActive()
        toast.success(t('admin.catalog.toast_unpublished', { item: singularTitle.value }))
      },
      onError: onMutationError,
    },
  })

const { mutate: unpublishVendor } =
  useApiAdminVendorsUnpublishApiAdminVendorsVendorIdUnpublishPatch({
    mutation: {
      onSuccess: async () => {
        await invalidateActive()
        toast.success(t('admin.catalog.toast_unpublished', { item: singularTitle.value }))
      },
      onError: onMutationError,
    },
  })

const { mutate: restoreProduct } = useApiAdminProductsRestoreApiAdminProductsProductIdRestorePost({
  mutation: {
    onSuccess: async () => {
      await invalidateActive()
      toast.success(t('admin.catalog.toast_restored', { item: singularTitle.value }))
    },
    onError: onMutationError,
  },
})

const { mutate: restoreCategory } =
  useApiAdminCategoriesRestoreApiAdminCategoriesCategoryIdRestorePost({
    mutation: {
      onSuccess: async () => {
        await invalidateActive()
        toast.success(t('admin.catalog.toast_restored', { item: singularTitle.value }))
      },
      onError: onMutationError,
    },
  })

const { mutate: restoreVendor } = useApiAdminVendorsRestoreApiAdminVendorsVendorIdRestorePost({
  mutation: {
    onSuccess: async () => {
      await invalidateActive()
      toast.success(t('admin.catalog.toast_restored', { item: singularTitle.value }))
    },
    onError: onMutationError,
  },
})

const saving = computed(
  () =>
    creatingProduct.value ||
    creatingCategory.value ||
    creatingVendor.value ||
    updatingProduct.value ||
    updatingCategory.value ||
    updatingVendor.value,
)

function saveItem(): void {
  error.value = null
  if (props.catalog === 'products') {
    if (editingId.value) {
      updateProduct({
        productId: editingId.value,
        data: {
          name: productForm.name,
          slug: productForm.slug,
          description: productForm.description,
          price: productForm.price,
          stock_qty: productForm.stock_qty,
        },
      })
    } else {
      createProduct({ data: productForm })
    }
  } else if (props.catalog === 'categories') {
    if (editingId.value) {
      updateCategory({ categoryId: editingId.value, data: categoryForm })
    } else {
      createCategory({ data: categoryForm })
    }
  } else if (editingId.value) {
    updateVendor({ vendorId: editingId.value, data: vendorForm })
  } else {
    createVendor({ data: vendorForm })
  }
}

function handleDelete(id: string): void {
  if (!confirm(t('admin.catalog.delete_confirm'))) return
  if (props.catalog === 'products') deleteProduct({ productId: id })
  else if (props.catalog === 'categories') deleteCategory({ categoryId: id })
  else deleteVendor({ vendorId: id })
}

function handlePublish(id: string): void {
  if (props.catalog === 'products') publishProduct({ productId: id })
  else if (props.catalog === 'categories') publishCategory({ categoryId: id })
  else publishVendor({ vendorId: id })
}

function handleUnpublish(id: string): void {
  if (props.catalog === 'products') unpublishProduct({ productId: id })
  else if (props.catalog === 'categories') unpublishCategory({ categoryId: id })
  else if (props.catalog === 'vendors') unpublishVendor({ vendorId: id })
}

function handleRestore(id: string): void {
  if (props.catalog === 'products') restoreProduct({ productId: id })
  else if (props.catalog === 'categories') restoreCategory({ categoryId: id })
  else if (props.catalog === 'vendors') restoreVendor({ vendorId: id })
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
        <button
          v-if="catalog === 'products'"
          type="button"
          :disabled="refreshing"
          class="rounded-lg border border-border px-4 py-2 text-sm font-medium text-fg hover:bg-app-bg-raised disabled:opacity-50"
          @click="refreshCatalog()"
        >
          {{ refreshing ? t('admin.catalog.refreshing') : t('admin.catalog.refresh') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover"
          @click="openCreate"
        >
          {{ t('admin.catalog.add', { item: singularTitle }) }}
        </button>
      </div>
    </div>

    <div v-if="showForm" class="mt-6 rounded-xl bg-admin-surface p-6 shadow-sm">
      <h2 class="font-semibold text-fg">
        {{
          editingId
            ? t('admin.catalog.form_edit', { item: singularTitle })
            : t('admin.catalog.form_create', { item: singularTitle })
        }}
      </h2>
      <form class="mt-4 space-y-4" @submit.prevent="saveItem">
        <template v-if="catalog === 'products'">
          <TranslatableInput v-model="productForm.name" label="Name" />
          <TranslatableInput v-model="productForm.slug" label="Slug" />
          <TranslatableInput v-model="productForm.description" label="Description" />
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="text-sm text-fg">
              {{ t('admin.catalog.field_price') }}
              <input
                v-model.number="productForm.price"
                type="number"
                min="0"
                step="0.01"
                class="mt-1 w-full rounded-lg border border-border px-3 py-2"
              />
            </label>
            <label class="text-sm text-fg">
              {{ t('admin.catalog.field_stock') }}
              <input
                v-model.number="productForm.stock_qty"
                type="number"
                min="0"
                class="mt-1 w-full rounded-lg border border-border px-3 py-2"
              />
            </label>
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="text-sm">
              {{ t('admin.catalog.field_category') }}
              <select
                v-model="productForm.category_id"
                required
                class="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand"
              >
                <option value="" disabled>{{ t('admin.catalog.select_category') }}</option>
                <option v-for="cat in allCategories" :key="cat.id" :value="cat.id">
                  {{ pickLocalized(cat.name, 'en') }}
                </option>
              </select>
            </label>
            <label class="text-sm">
              {{ t('admin.catalog.field_vendor') }}
              <select
                v-model="productForm.vendor_id"
                class="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand"
              >
                <option value="">{{ t('admin.catalog.no_vendor') }}</option>
                <option v-for="vendor in allVendors" :key="vendor.id" :value="vendor.id">
                  {{ vendor.name }}
                </option>
              </select>
            </label>
          </div>
        </template>
        <template v-else-if="catalog === 'categories'">
          <TranslatableInput v-model="categoryForm.name" label="Name" />
          <TranslatableInput v-model="categoryForm.slug" label="Slug" />
        </template>
        <template v-else>
          <label class="block text-sm text-fg">
            {{ t('admin.catalog.col_name') }}
            <input
              v-model="vendorForm.name"
              required
              class="mt-1 w-full rounded-lg border border-border px-3 py-2"
            />
          </label>
          <label class="block text-sm text-fg">
            {{ t('admin.catalog.field_slug') }}
            <input
              v-model="vendorForm.slug"
              required
              class="mt-1 w-full rounded-lg border border-border px-3 py-2"
            />
          </label>
          <label class="block text-sm text-fg">
            {{ t('admin.catalog.field_description') }}
            <textarea
              v-model="vendorForm.description"
              class="mt-1 w-full rounded-lg border border-border px-3 py-2"
              rows="3"
            />
          </label>
        </template>
        <p v-if="error" class="text-sm text-danger">{{ error }}</p>
        <div class="flex gap-3">
          <button
            type="submit"
            :disabled="saving"
            class="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-50"
          >
            {{ saving ? t('admin.catalog.saving') : t('admin.catalog.save') }}
          </button>
          <button
            type="button"
            class="rounded-lg border border-border px-4 py-2 text-sm text-fg hover:bg-app-bg-raised"
            @click="showForm = false"
          >
            {{ t('admin.catalog.cancel') }}
          </button>
        </div>
      </form>
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
          <tr v-for="item in items" :key="item.id" class="hover:bg-app-bg-raised">
            <td class="px-6 py-4 text-sm font-medium text-fg">{{ itemName(item) }}</td>
            <td class="px-6 py-4">
              <span
                class="inline-flex w-20 justify-center rounded-full px-[10px] py-[5px] text-xs font-medium"
                :class="
                  itemStatus(item) === 'published'
                    ? 'bg-status-delivered-bg text-status-delivered-fg'
                    : 'bg-app-bg-sunken text-fg-muted'
                "
              >
                {{ itemStatusLabel(item) }}
              </span>
            </td>
            <!-- real_status badge: only rendered for product rows -->
            <td v-if="catalog === 'products'" class="px-6 py-4">
              <span
                v-if="'real_status' in item && item.real_status"
                class="inline-flex w-20 justify-center rounded-full px-[10px] py-[5px] text-xs font-medium"
                :class="
                  REAL_STATUS_CLASSES[item.real_status as RealStatus] ??
                  'bg-app-bg-sunken text-fg-muted'
                "
              >
                {{
                  REAL_STATUS_LABELS[item.real_status as RealStatus] ?? (item.real_status as string)
                }}
              </span>
              <span v-else class="text-xs text-fg-faint">—</span>
            </td>
            <td class="px-6 py-4 text-end">
              <div class="flex justify-end gap-3">
                <RouterLink
                  :to="`/admin/${catalog}/${item.id}/edit`"
                  class="text-xs text-fg-muted hover:text-fg hover:underline"
                >
                  {{ t('admin.catalog.action_edit') }}
                </RouterLink>
                <button
                  v-if="itemStatus(item) !== 'published'"
                  type="button"
                  class="text-xs text-brand hover:underline"
                  @click="handlePublish(item.id)"
                >
                  {{ t('admin.catalog.action_publish') }}
                </button>
                <button
                  v-else
                  type="button"
                  class="text-xs text-fg-muted hover:underline"
                  @click="handleUnpublish(item.id)"
                >
                  {{ t('admin.catalog.action_unpublish') }}
                </button>
                <button
                  v-if="'deleted_at' in item && item.deleted_at"
                  type="button"
                  class="text-xs text-stock-in hover:underline"
                  @click="handleRestore(item.id)"
                >
                  {{ t('admin.catalog.action_restore') }}
                </button>
                <button
                  type="button"
                  class="text-xs text-danger hover:underline"
                  @click="handleDelete(item.id)"
                >
                  {{ t('admin.catalog.action_delete') }}
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!loading && items.length === 0">
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
