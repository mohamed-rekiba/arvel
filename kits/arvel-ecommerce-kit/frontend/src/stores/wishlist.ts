import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

const STORAGE_KEY = 'wishlist'

function readStored(): string[] {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

export const useWishlistStore = defineStore('wishlist', () => {
  const ids = ref<Set<string>>(new Set(readStored()))

  const count = computed(() => ids.value.size)

  function has(productId: string): boolean {
    return ids.value.has(productId)
  }

  function toggle(productId: string): void {
    const next = new Set(ids.value)
    if (next.has(productId)) next.delete(productId)
    else next.add(productId)
    ids.value = next
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]))
  }

  // Guest-only: persists in localStorage, no account sync (there's no backend
  // wishlist). Survives navigation and reloads; shared across all product cards.
  return { ids, count, has, toggle }
})
