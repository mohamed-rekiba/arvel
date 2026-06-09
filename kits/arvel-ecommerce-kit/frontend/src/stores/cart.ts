import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  cartItemsStoreApiCartItemsPost,
  cartItemsDestroyApiCartItemsItemIdDelete,
  cartItemsUpdateApiCartItemsItemIdPatch,
  cartShowApiCartGet,
} from '@/api/cart/cart'
import type { CartOut } from '@/api/schemas'
import { translate } from '@/lib/i18n-instance'
import { useAuthStore } from '@/stores/auth'

export const useCartStore = defineStore('cart', () => {
  const cart = ref<CartOut | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const itemCount = computed(
    () => cart.value?.items.reduce((sum, item) => sum + item.quantity, 0) ?? 0,
  )

  // Snapshot prices (what checkout charges), not live product.price which can drift.
  const subtotal = computed(() => cart.value?.total ?? 0)

  async function load(): Promise<void> {
    const auth = useAuthStore()
    if (!auth.isAuthenticated) {
      cart.value = null
      return
    }
    loading.value = true
    error.value = null
    try {
      cart.value = (await cartShowApiCartGet()).data
    } catch (err) {
      error.value = err instanceof Error ? err.message : translate('cart.error_load')
    } finally {
      loading.value = false
    }
  }

  async function addItem(productId: string, quantity = 1): Promise<void> {
    loading.value = true
    error.value = null
    try {
      cart.value = (await cartItemsStoreApiCartItemsPost({ product_id: productId, quantity })).data
    } catch (err) {
      error.value = err instanceof Error ? err.message : translate('cart.error_add')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updateQuantity(itemId: string, quantity: number): Promise<void> {
    loading.value = true
    error.value = null
    try {
      if (quantity <= 0) {
        cart.value = (await cartItemsDestroyApiCartItemsItemIdDelete(itemId)).data
      } else {
        cart.value = (await cartItemsUpdateApiCartItemsItemIdPatch(itemId, { quantity })).data
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : translate('cart.error_update')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function removeItem(itemId: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      cart.value = (await cartItemsDestroyApiCartItemsItemIdDelete(itemId)).data
    } catch (err) {
      error.value = err instanceof Error ? err.message : translate('cart.error_remove')
      throw err
    } finally {
      loading.value = false
    }
  }

  function clear(): void {
    cart.value = null
  }

  return {
    cart,
    loading,
    error,
    itemCount,
    subtotal,
    load,
    addItem,
    updateQuantity,
    removeItem,
    clear,
  }
})
