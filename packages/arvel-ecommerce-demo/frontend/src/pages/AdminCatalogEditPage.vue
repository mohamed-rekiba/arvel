<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  useApiAdminCategoriesIndexApiAdminCategoriesGet,
  useApiAdminCategoriesShowApiAdminCategoriesCategoryIdGet,
  useApiAdminCategoriesUpdateApiAdminCategoriesCategoryIdPatch,
  useApiAdminCategoriesPublishApiAdminCategoriesCategoryIdPublishPatch,
  useApiAdminCategoriesUnpublishApiAdminCategoriesCategoryIdUnpublishPatch,
} from '@/api/admin-categories/admin-categories'
import {
  useApiAdminProductsShowApiAdminProductsProductIdGet,
  useApiAdminProductsUpdateApiAdminProductsProductIdPatch,
} from '@/api/admin-products/admin-products'
import {
  useApiAdminVendorsIndexApiAdminVendorsGet,
  useApiAdminVendorsShowApiAdminVendorsVendorIdGet,
  useApiAdminVendorsUpdateApiAdminVendorsVendorIdPatch,
} from '@/api/admin-vendors/admin-vendors'
import TranslatableInput from '@/components/admin/TranslatableInput.vue'
import { useToastStore } from '@/stores/toast'
import { pickLocalized } from '@/lib/i18n'
import type { LocalizedText } from '@/types'

const { t } = useI18n({ useScope: 'global' })
const toast = useToastStore()
const router = useRouter()

const props = defineProps<{
  catalog: 'products' | 'categories' | 'vendors'
  id: string
}>()

const isProducts = computed(() => props.catalog === 'products')
const isCategories = computed(() => props.catalog === 'categories')
const isVendors = computed(() => props.catalog === 'vendors')

const catalogSingular = computed(
  () =>
    ({
      products: t('admin.catalog.product_singular'),
      categories: t('admin.catalog.category_singular'),
      vendors: t('admin.catalog.vendor_singular'),
    })[props.catalog],
)

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
  parent_id: null as string | null,
})

const categoryIsPublished = ref(false)

const vendorForm = reactive({
  name: '',
  slug: '',
  description: '',
})

// Fetch current item
const { data: productWrapper, isPending: loadingProduct } =
  useApiAdminProductsShowApiAdminProductsProductIdGet(
    computed(() => props.id),
    { query: { enabled: isProducts } },
  )

const { data: categoryWrapper, isPending: loadingCategory } =
  useApiAdminCategoriesShowApiAdminCategoriesCategoryIdGet(
    computed(() => props.id),
    { query: { enabled: isCategories } },
  )

const { data: vendorWrapper, isPending: loadingVendor } =
  useApiAdminVendorsShowApiAdminVendorsVendorIdGet(
    computed(() => props.id),
    { query: { enabled: isVendors } },
  )

// Load category list for: product category selector + category parent selector
const needsCategories = computed(() => isProducts.value || isCategories.value)
const { data: allCategoriesData } = useApiAdminCategoriesIndexApiAdminCategoriesGet(undefined, {
  query: { enabled: needsCategories },
})
const { data: allVendorsData } = useApiAdminVendorsIndexApiAdminVendorsGet(undefined, {
  query: { enabled: isProducts },
})

const allCategories = computed(() => allCategoriesData.value?.data ?? [])
const allVendors = computed(() => allVendorsData.value?.data ?? [])

// Parent candidates exclude the category being edited (no self-reference)
const parentCandidates = computed(() => allCategories.value.filter((c) => c.id !== props.id))

// Only check the active query — disabled queries stay isPending:true forever in TanStack Query v5.
const loading = computed(() =>
  isProducts.value
    ? loadingProduct.value
    : isCategories.value
      ? loadingCategory.value
      : loadingVendor.value,
)

// immediate: true handles cached responses delivered synchronously before the watcher is registered.
watch(
  productWrapper,
  (wrapper) => {
    const product = wrapper?.data
    if (!product) return
    Object.assign(productForm, {
      name: { ...product.name },
      slug: { ...product.slug },
      description: { ...product.description },
      price: product.price,
      stock_qty: product.stock_qty,
      category_id: product.category_id ?? '',
      vendor_id: product.vendor_id ?? '',
    })
  },
  { immediate: true },
)

watch(
  categoryWrapper,
  (wrapper) => {
    const category = wrapper?.data
    if (!category) return
    Object.assign(categoryForm, {
      name: { ...category.name },
      slug: { ...category.slug },
      parent_id: category.parent_id ?? null,
    })
    categoryIsPublished.value = category.status === 'published'
  },
  { immediate: true },
)

watch(
  vendorWrapper,
  (wrapper) => {
    const vendor = wrapper?.data
    if (!vendor) return
    Object.assign(vendorForm, {
      name: vendor.name,
      slug: vendor.slug,
      description: vendor.description ?? '',
    })
  },
  { immediate: true },
)

// Mutations
const { mutate: updateProduct, isPending: savingProduct } =
  useApiAdminProductsUpdateApiAdminProductsProductIdPatch({
    mutation: {
      onSuccess: async () => {
        toast.success(t('admin.edit.toast_saved'))
        await router.push(`/admin/${props.catalog}`)
      },
      onError: (err: unknown) => {
        const msg = err instanceof Error ? err.message : t('admin.edit.save_failed')
        error.value = msg
        toast.error(msg)
      },
    },
  })

const { mutate: updateCategory, isPending: savingCategory } =
  useApiAdminCategoriesUpdateApiAdminCategoriesCategoryIdPatch({
    mutation: {
      onSuccess: async () => {
        toast.success(t('admin.edit.toast_saved'))
        await router.push(`/admin/${props.catalog}`)
      },
      onError: (err: unknown) => {
        const msg = err instanceof Error ? err.message : t('admin.edit.save_failed')
        error.value = msg
        toast.error(msg)
      },
    },
  })

const { mutate: publishCategory, isPending: publishing } =
  useApiAdminCategoriesPublishApiAdminCategoriesCategoryIdPublishPatch({
    mutation: {
      onSuccess: () => {
        categoryIsPublished.value = true
        toast.success(t('admin.edit.toast_published'))
      },
      onError: (err: unknown) => {
        toast.error(err instanceof Error ? err.message : t('admin.edit.publish_failed'))
      },
    },
  })

const { mutate: unpublishCategory, isPending: unpublishing } =
  useApiAdminCategoriesUnpublishApiAdminCategoriesCategoryIdUnpublishPatch({
    mutation: {
      onSuccess: () => {
        categoryIsPublished.value = false
        toast.success(t('admin.edit.toast_unpublished'))
      },
      onError: (err: unknown) => {
        toast.error(err instanceof Error ? err.message : t('admin.edit.unpublish_failed'))
      },
    },
  })

const { mutate: updateVendor, isPending: savingVendor } =
  useApiAdminVendorsUpdateApiAdminVendorsVendorIdPatch({
    mutation: {
      onSuccess: async () => {
        toast.success(t('admin.edit.toast_saved'))
        await router.push(`/admin/${props.catalog}`)
      },
      onError: (err: unknown) => {
        const msg = err instanceof Error ? err.message : t('admin.edit.save_failed')
        error.value = msg
        toast.error(msg)
      },
    },
  })

const saving = computed(() => savingProduct.value || savingCategory.value || savingVendor.value)

const togglingPublish = computed(() => publishing.value || unpublishing.value)

function handlePublishToggle(): void {
  if (categoryIsPublished.value) {
    unpublishCategory({ categoryId: props.id })
  } else {
    publishCategory({ categoryId: props.id })
  }
}

function handleSave(): void {
  error.value = null
  if (props.catalog === 'products') {
    updateProduct({
      productId: props.id,
      data: {
        name: productForm.name,
        slug: productForm.slug,
        description: productForm.description,
        price: productForm.price,
        stock_qty: productForm.stock_qty,
      },
    })
  } else if (props.catalog === 'categories') {
    updateCategory({
      categoryId: props.id,
      data: {
        name: categoryForm.name,
        slug: categoryForm.slug,
        parent_id: categoryForm.parent_id,
      },
    })
  } else {
    updateVendor({ vendorId: props.id, data: { ...vendorForm } })
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl">
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="flex items-center gap-1 text-sm text-brand hover:underline"
        @click="router.back()"
      >
        <span
          class="material-symbols-outlined text-[18px] leading-none rtl:rotate-180"
          aria-hidden="true"
          >arrow_back</span
        >
        {{ t('admin.edit.back') }}
      </button>
      <h1 class="text-2xl font-bold capitalize text-fg">
        {{ t('admin.edit.title', { item: catalogSingular }) }}
      </h1>
    </div>

    <div v-if="loading" class="space-y-4">
      <div v-for="i in 4" :key="i" class="h-10 animate-pulse rounded-lg bg-app-bg-sunken" />
    </div>

    <form v-else class="space-y-5" @submit.prevent="handleSave">
      <p v-if="error" class="rounded-lg bg-danger/10 px-4 py-2 text-sm text-danger">{{ error }}</p>

      <!-- ── Products form ── -->
      <template v-if="catalog === 'products'">
        <TranslatableInput v-model="productForm.name" :label="t('admin.edit.field_name')" />
        <TranslatableInput v-model="productForm.slug" :label="t('admin.edit.field_slug')" />
        <TranslatableInput
          v-model="productForm.description"
          :label="t('admin.edit.field_description')"
        />
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="text-sm font-medium text-fg">
            {{ t('admin.edit.field_price') }}
            <input
              v-model.number="productForm.price"
              type="number"
              min="0"
              step="0.01"
              required
              class="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand"
            />
          </label>
          <label class="text-sm font-medium text-fg">
            {{ t('admin.edit.field_stock') }}
            <input
              v-model.number="productForm.stock_qty"
              type="number"
              min="0"
              required
              class="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand"
            />
          </label>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="text-sm font-medium text-fg">
            {{ t('admin.edit.field_category') }}
            <select
              v-model="productForm.category_id"
              required
              class="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand"
            >
              <option value="" disabled>{{ t('admin.edit.select_category') }}</option>
              <option v-for="cat in allCategories" :key="cat.id" :value="cat.id">
                {{ pickLocalized(cat.name, 'en') }}
              </option>
            </select>
          </label>
          <label class="text-sm font-medium text-fg">
            {{ t('admin.edit.field_vendor') }}
            <select
              v-model="productForm.vendor_id"
              class="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand"
            >
              <option value="">{{ t('admin.edit.no_vendor') }}</option>
              <option v-for="vendor in allVendors" :key="vendor.id" :value="vendor.id">
                {{ vendor.name }}
              </option>
            </select>
          </label>
        </div>
      </template>

      <!-- ── Categories form ── -->
      <template v-else-if="catalog === 'categories'">
        <TranslatableInput v-model="categoryForm.name" :label="t('admin.edit.field_name')" />
        <TranslatableInput v-model="categoryForm.slug" :label="t('admin.edit.field_slug')" />

        <!-- Parent category -->
        <label class="block text-sm font-medium text-fg">
          {{ t('admin.edit.parent_category') }}
          <select
            v-model="categoryForm.parent_id"
            class="mt-1 w-full rounded-lg border border-border bg-app-bg px-3 py-2 text-sm text-fg outline-none focus:border-brand"
          >
            <option :value="null">{{ t('admin.edit.no_parent') }}</option>
            <option v-for="cat in parentCandidates" :key="cat.id" :value="cat.id">
              {{ pickLocalized(cat.name, 'en') }}
            </option>
          </select>
        </label>

        <!-- Publish toggle -->
        <div class="flex items-center justify-between rounded-lg border border-border px-4 py-3">
          <div>
            <p class="text-sm font-medium text-fg">{{ t('admin.edit.published_label') }}</p>
            <p class="text-xs text-fg-muted">
              {{
                categoryIsPublished
                  ? t('admin.edit.visible_storefront')
                  : t('admin.edit.hidden_storefront')
              }}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            dir="ltr"
            :aria-checked="categoryIsPublished"
            :disabled="togglingPublish"
            class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2 disabled:opacity-50"
            :class="categoryIsPublished ? 'bg-brand' : 'bg-border-strong'"
            @click="handlePublishToggle"
          >
            <span
              class="inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200"
              :class="categoryIsPublished ? 'translate-x-6' : 'translate-x-1'"
            />
          </button>
        </div>
      </template>

      <!-- ── Vendors form ── -->
      <template v-else>
        <label class="block text-sm font-medium text-fg">
          {{ t('admin.edit.field_name') }}
          <input
            v-model="vendorForm.name"
            type="text"
            required
            class="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand"
          />
        </label>
        <label class="block text-sm font-medium text-fg">
          {{ t('admin.edit.field_slug') }}
          <input
            v-model="vendorForm.slug"
            type="text"
            class="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand"
          />
        </label>
        <label class="block text-sm font-medium text-fg">
          {{ t('admin.edit.field_description') }}
          <textarea
            v-model="vendorForm.description"
            rows="3"
            class="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand"
          />
        </label>
      </template>

      <div class="flex gap-3 pt-2">
        <button
          type="submit"
          :disabled="saving"
          class="rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-hover disabled:opacity-50"
        >
          {{ saving ? t('admin.edit.saving') : t('admin.edit.save_changes') }}
        </button>
        <button
          type="button"
          class="rounded-lg border border-border px-5 py-2.5 text-sm font-medium text-fg transition hover:bg-app-bg-raised"
          @click="router.back()"
        >
          {{ t('admin.edit.cancel') }}
        </button>
      </div>
    </form>
  </div>
</template>
