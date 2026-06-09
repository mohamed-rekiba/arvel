import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import type { CartItemOut, CartOut, ProductCardOut } from '@/api/schemas'
import { useCartStore } from '@/stores/cart'

function makeProduct(price: number): ProductCardOut {
  return {
    id: 'p1',
    name: 'Test',
    slug: 'test',
    short_description: null,
    price,
    stock: 10,
    original_price: null,
    thumbnail_url: null,
    image_srcset: '',
    image_sizes: '',
    rating: null,
    rating_count: null,
    is_new: false,
    is_bestseller: false,
    category_id: null,
    category_name: null,
    category_slug: null,
    category_parent_id: null,
    parent_category_name: null,
    parent_category_slug: null,
    vendor_id: null,
    vendor_name: null,
    vendor_slug: null,
  }
}

function makeItem(id: string, quantity: number, price: number): CartItemOut {
  return {
    id,
    product_id: 'p1',
    quantity,
    unit_price: price,
    subtotal: price * quantity,
    product: makeProduct(price),
  }
}

function makeCart(items: CartItemOut[]): CartOut {
  const total = items.reduce((sum, i) => sum + i.subtotal, 0)
  return { id: 'cart-1', items, total }
}

describe('cart store getters', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('itemCount and subtotal are zero for an empty cart', () => {
    const store = useCartStore()
    expect(store.itemCount).toBe(0)
    expect(store.subtotal).toBe(0)
  })

  it('sums quantities across items', () => {
    const store = useCartStore()
    store.cart = makeCart([makeItem('a', 2, 5), makeItem('b', 3, 5)])
    expect(store.itemCount).toBe(5)
  })

  it('computes subtotal from price times quantity', () => {
    const store = useCartStore()
    store.cart = makeCart([makeItem('a', 2, 10), makeItem('b', 1, 4.5)])
    expect(store.subtotal).toBe(24.5)
  })

  it('clear() resets the cart to null', () => {
    const store = useCartStore()
    store.cart = makeCart([makeItem('a', 1, 10)])
    store.clear()
    expect(store.cart).toBeNull()
    expect(store.itemCount).toBe(0)
  })
})
