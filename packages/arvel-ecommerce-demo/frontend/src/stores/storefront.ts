import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useStorefrontStore = defineStore('storefront', () => {
  const currentProductId = ref<string | null>(null)

  function setCurrentProduct(id: string | null): void {
    currentProductId.value = id
  }

  return { currentProductId, setCurrentProduct }
})
