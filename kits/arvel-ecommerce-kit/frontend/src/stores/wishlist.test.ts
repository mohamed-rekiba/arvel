import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useWishlistStore } from '@/stores/wishlist'

describe('wishlist store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('starts empty', () => {
    const store = useWishlistStore()
    expect(store.count).toBe(0)
    expect(store.has('p1')).toBe(false)
  })

  it('toggle adds then removes a product', () => {
    const store = useWishlistStore()
    store.toggle('p1')
    expect(store.has('p1')).toBe(true)
    expect(store.count).toBe(1)
    store.toggle('p1')
    expect(store.has('p1')).toBe(false)
    expect(store.count).toBe(0)
  })

  it('persists to localStorage and rehydrates', () => {
    useWishlistStore().toggle('p1')
    setActivePinia(createPinia())
    const fresh = useWishlistStore()
    expect(fresh.has('p1')).toBe(true)
  })
})
