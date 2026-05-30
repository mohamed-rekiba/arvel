import { defineStore } from 'pinia'
import { ref } from 'vue'
import { storefrontCategoriesIndexApiCategoriesGet } from '@/api/default/default'
import type { AdminCategoryOut } from '@/api/schemas'

export const useCategoriesStore = defineStore('storefront-categories', () => {
  const list = ref<AdminCategoryOut[]>([])
  const loaded = ref(false)
  const loading = ref(false)

  async function load(): Promise<void> {
    if (loaded.value || loading.value) return
    loading.value = true
    try {
      const result = await storefrontCategoriesIndexApiCategoriesGet()
      list.value = result.data ?? []
    } finally {
      loading.value = false
      loaded.value = true
    }
  }

  return { list, loaded, loading, load }
})
