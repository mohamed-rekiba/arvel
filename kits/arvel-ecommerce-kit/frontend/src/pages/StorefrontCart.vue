<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { formatCurrency, toSupportedLocale } from '@/lib/i18n'
import { requireStoredAccessToken } from '@/lib/api'
import { useCartStore } from '@/stores/cart'

const { locale, t } = useI18n({ useScope: 'global' })
const cart = useCartStore()
const currentLocale = computed(() => toSupportedLocale(locale.value))

const SHIPPING = 0
const TAXES = 0

const itemCount = computed(() => cart.itemCount)
const subtotal = computed(() => cart.subtotal)
const total = computed(() => subtotal.value + SHIPPING + TAXES)

onMounted(() => {
  requireStoredAccessToken()
  void cart.load()
})

async function updateQty(itemId: string, quantity: number): Promise<void> {
  if (quantity <= 0) {
    await cart.removeItem(itemId)
  } else {
    await cart.updateQuantity(itemId, quantity)
  }
}

async function remove(itemId: string): Promise<void> {
  await cart.removeItem(itemId)
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-10 lg:px-8">
    <h1 class="text-3xl font-bold text-fg">{{ t('cart.title', 'Your Cart') }}</h1>

    <!-- Loading skeletons -->
    <div v-if="cart.loading" class="mt-8 space-y-4">
      <div v-for="i in 3" :key="i" class="h-20 animate-pulse rounded-xl bg-app-bg-sunken" />
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!cart.cart?.items.length"
      class="mt-20 flex flex-col items-center gap-3 text-center"
    >
      <span class="material-symbols-outlined select-none text-[56px] leading-none text-fg-faint">
        shopping_cart
      </span>
      <p class="text-fg-faint">{{ t('cart.empty', 'Your cart is empty') }}</p>
      <RouterLink
        to="/products"
        class="mt-2 rounded-xl bg-brand px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand-hover"
      >
        {{ t('cart.continue', 'Continue Shopping') }}
      </RouterLink>
    </div>

    <!-- Cart content -->
    <div v-else class="mt-8 items-start gap-6 lg:grid lg:grid-cols-[1fr_320px]">
      <!-- ── Product table ───────────────────────────────────────────── -->
      <div class="overflow-hidden rounded-xl border border-border-subtle bg-app-bg shadow-sm">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[520px]">
            <thead>
              <tr class="bg-brand text-white">
                <th class="w-10 px-4 py-3.5" />
                <th class="px-4 py-3.5 text-start text-sm font-semibold">
                  {{ t('order.product') }}
                </th>
                <th class="px-4 py-3.5 text-center text-sm font-semibold">
                  {{ t('order.price') }}
                </th>
                <th class="px-4 py-3.5 text-center text-sm font-semibold">
                  {{ t('order.quantity') }}
                </th>
                <th class="px-4 py-3.5 text-end text-sm font-semibold">
                  {{ t('order.subtotal') }}
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border-subtle">
              <tr v-for="item in cart.cart.items" :key="item.id" class="group">
                <!-- Remove -->
                <td class="px-4 py-4">
                  <button
                    type="button"
                    :disabled="cart.loading"
                    class="flex h-6 w-6 items-center justify-center rounded-full border border-border text-fg-muted transition hover:border-danger hover:bg-danger/10 hover:text-danger disabled:opacity-40"
                    @click="remove(item.id)"
                  >
                    <span class="material-symbols-outlined select-none text-[14px] leading-none">
                      close
                    </span>
                  </button>
                </td>

                <!-- Product -->
                <td class="px-4 py-4">
                  <div class="flex items-center gap-3">
                    <div class="h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-app-bg-sunken">
                      <img
                        v-if="item.product.thumbnail_url"
                        :src="item.product.thumbnail_url"
                        :alt="item.product.name"
                        class="h-full w-full object-cover"
                      />
                      <div v-else class="flex h-full w-full items-center justify-center">
                        <span
                          class="material-symbols-outlined select-none text-[24px] leading-none text-fg-faint"
                        >
                          image
                        </span>
                      </div>
                    </div>
                    <div>
                      <p class="text-sm font-semibold text-fg">{{ item.product.name }}</p>
                      <p v-if="item.product.category_name" class="mt-0.5 text-xs text-fg-muted">
                        {{ item.product.category_name }}
                      </p>
                    </div>
                  </div>
                </td>

                <!-- Price -->
                <td class="px-4 py-4 text-center text-sm text-fg">
                  {{ formatCurrency(item.product.price, currentLocale) }}
                </td>

                <!-- Quantity stepper -->
                <td class="px-4 py-4">
                  <div class="flex items-center justify-center gap-2">
                    <button
                      type="button"
                      :disabled="cart.loading || item.quantity <= 1"
                      class="flex h-7 w-7 items-center justify-center rounded-full border border-border text-fg hover:bg-app-bg-raised disabled:opacity-40"
                      @click="updateQty(item.id, item.quantity - 1)"
                    >
                      <span class="material-symbols-outlined select-none text-[14px] leading-none">
                        remove
                      </span>
                    </button>
                    <span class="w-8 text-center text-sm font-semibold text-fg">
                      {{ item.quantity }}
                    </span>
                    <button
                      type="button"
                      :disabled="cart.loading"
                      class="flex h-7 w-7 items-center justify-center rounded-full border border-border text-fg hover:bg-app-bg-raised disabled:opacity-40"
                      @click="updateQty(item.id, item.quantity + 1)"
                    >
                      <span class="material-symbols-outlined select-none text-[14px] leading-none">
                        add
                      </span>
                    </button>
                  </div>
                </td>

                <!-- Subtotal -->
                <td class="px-4 py-4 text-end text-sm font-bold text-fg">
                  {{ formatCurrency(item.product.price * item.quantity, currentLocale) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Order summary panel ─────────────────────────────────────── -->
      <div
        class="mt-6 self-start rounded-xl border border-border-subtle bg-app-bg p-6 shadow-sm lg:mt-0"
      >
        <h2 class="text-lg font-bold text-fg">{{ t('order.summary') }}</h2>

        <div class="mt-5 space-y-3">
          <div class="flex justify-between text-sm text-fg-muted">
            <span>{{ t('order.items') }}</span>
            <span>{{ itemCount }}</span>
          </div>
          <div class="flex justify-between text-sm text-fg-muted">
            <span>{{ t('order.subtotal') }}</span>
            <span>{{ formatCurrency(subtotal, currentLocale) }}</span>
          </div>
          <div class="flex justify-between text-sm text-fg-muted">
            <span>{{ t('order.shipping') }}</span>
            <span>{{ formatCurrency(SHIPPING, currentLocale) }}</span>
          </div>
          <div class="flex justify-between text-sm text-fg-muted">
            <span>{{ t('order.taxes') }}</span>
            <span>{{ formatCurrency(TAXES, currentLocale) }}</span>
          </div>
        </div>

        <div
          class="mt-4 flex justify-between border-t border-border-subtle pt-4 text-base font-bold text-fg"
        >
          <span>{{ t('order.total') }}</span>
          <span>{{ formatCurrency(total, currentLocale) }}</span>
        </div>

        <RouterLink
          to="/checkout"
          class="mt-5 block w-full rounded-xl bg-brand py-3 text-center text-sm font-semibold text-white hover:bg-brand-hover"
        >
          {{ t('cart.checkout', 'Proceed to Checkout') }}
        </RouterLink>

        <RouterLink
          to="/products"
          class="mt-3 block w-full rounded-xl border border-border py-2.5 text-center text-sm font-medium text-fg-muted hover:bg-app-bg-raised"
        >
          {{ t('cart.continue', 'Continue Shopping') }}
        </RouterLink>
      </div>
    </div>
  </div>
</template>
