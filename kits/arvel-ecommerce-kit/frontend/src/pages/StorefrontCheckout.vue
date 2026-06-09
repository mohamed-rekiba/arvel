<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { requireStoredAccessToken } from '@/lib/api'
import { checkoutApiCheckoutPost } from '@/api/checkout/checkout'
import type { OrderOut } from '@/api/schemas'
import { formatCurrency, toSupportedLocale } from '@/lib/i18n'
import { useCartStore } from '@/stores/cart'

const { locale, t } = useI18n({ useScope: 'global' })
const currentLocale = computed(() => toSupportedLocale(locale.value))
const cart = useCartStore()

onMounted(() => {
  requireStoredAccessToken()
  // Don't rely on boot-time hydration — a direct load/refresh on /checkout
  // must still populate the cart for the review step (mirrors StorefrontCart).
  void cart.load()
})

const step = ref(1)
const submitting = ref(false)
const error = ref<string | null>(null)
const placedOrder = ref<OrderOut | null>(null)

const form = reactive({
  name: '',
  street: '',
  city: '',
  country: '',
})

const STEPS = computed(() => [
  { key: 'shipping', label: t('checkout.steps.shipping', 'Shipping') },
  { key: 'review', label: t('checkout.steps.review', 'Review') },
  { key: 'confirmation', label: t('checkout.steps.confirmation', 'Confirmation') },
])

const DELIVERY_FEE = 0
const TAXES = 0
const subtotal = computed(() => cart.subtotal)
const total = computed(() => subtotal.value + DELIVERY_FEE + TAXES)

const estimatedDelivery = computed(() => {
  const d = new Date()
  d.setDate(d.getDate() + 5)
  return d.toLocaleDateString(currentLocale.value, {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
  })
})

async function placeOrder(): Promise<void> {
  submitting.value = true
  error.value = null
  try {
    const wrapper = await checkoutApiCheckoutPost({
      shipping_address: {
        name: form.name,
        street: form.street,
        city: form.city,
        country: form.country,
      },
    })
    placedOrder.value = wrapper.data
    cart.clear()
    step.value = 3
  } catch (err) {
    error.value =
      err instanceof Error
        ? err.message
        : t('checkout.failed', 'Checkout failed. Please try again.')
  } finally {
    submitting.value = false
  }
}

function itemShipping(index: number): string {
  return index === 0 && DELIVERY_FEE > 0
    ? formatCurrency(DELIVERY_FEE, currentLocale.value)
    : t('order.free', 'Free')
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-10 lg:px-8">
    <!-- Step indicator — always LTR so steps read 1→2→3 in any locale -->
    <div class="flex items-start justify-center" dir="ltr">
      <template v-for="(s, i) in STEPS" :key="s.key">
        <div class="flex flex-col items-center gap-2">
          <div
            class="flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold transition-colors"
            :class="
              i + 1 < step
                ? 'bg-brand text-white'
                : i + 1 === step
                  ? 'border-2 border-brand bg-app-bg text-brand'
                  : 'border-2 border-border-subtle bg-app-bg text-fg-faint'
            "
          >
            <span
              v-if="i + 1 < step"
              class="material-symbols-outlined select-none text-[18px] leading-none"
              style="font-variation-settings: 'FILL' 1"
              >check</span
            >
            <span v-else>{{ i + 1 }}</span>
          </div>
          <span
            class="whitespace-nowrap text-xs font-medium"
            :class="i + 1 <= step ? 'text-brand' : 'text-fg-faint'"
            >{{ s.label }}</span
          >
        </div>
        <div
          v-if="i < STEPS.length - 1"
          class="mt-4 h-0.5 w-12 shrink-0 transition-colors sm:w-24"
          :class="i + 1 < step ? 'bg-brand' : 'bg-border-subtle'"
        />
      </template>
    </div>

    <!-- Content card -->
    <div class="mt-8 overflow-hidden rounded-2xl border border-border-subtle bg-app-bg shadow-sm">
      <!-- Card heading -->
      <div class="border-b border-border-subtle px-6 pb-5 pt-6 text-center">
        <h1 class="text-2xl font-bold text-fg">
          {{
            step === 3
              ? t('checkout.confirmed_title', 'Order Confirmation')
              : t('checkout.title', 'Checkout')
          }}
        </h1>
        <p v-if="step === 3" class="mt-1 text-sm text-fg-muted">
          {{ t('checkout.confirmed_sub', 'Thank you for your order!') }}
        </p>
      </div>

      <!-- ── Step 1: Shipping ─────────────────────────────────────────── -->
      <div v-if="step === 1" class="p-6">
        <form class="space-y-5" @submit.prevent="step = 2">
          <div>
            <label class="block text-sm font-medium text-fg">{{ t('checkout.full_name') }}</label>
            <input
              v-model="form.name"
              required
              :placeholder="t('checkout.full_name_placeholder')"
              class="mt-1.5 w-full rounded-lg border border-border px-4 py-2.5 text-sm text-fg outline-none placeholder:text-fg-faint focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-fg">{{ t('checkout.street') }}</label>
            <input
              v-model="form.street"
              required
              :placeholder="t('checkout.street_placeholder')"
              class="mt-1.5 w-full rounded-lg border border-border px-4 py-2.5 text-sm text-fg outline-none placeholder:text-fg-faint focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div>
              <label class="block text-sm font-medium text-fg">{{ t('checkout.city') }}</label>
              <input
                v-model="form.city"
                required
                :placeholder="t('checkout.city_placeholder')"
                class="mt-1.5 w-full rounded-lg border border-border px-4 py-2.5 text-sm text-fg outline-none placeholder:text-fg-faint focus:border-accent focus:ring-2 focus:ring-accent/20"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-fg">{{ t('checkout.country') }}</label>
              <input
                v-model="form.country"
                required
                :placeholder="t('checkout.country_placeholder')"
                class="mt-1.5 w-full rounded-lg border border-border px-4 py-2.5 text-sm text-fg outline-none placeholder:text-fg-faint focus:border-accent focus:ring-2 focus:ring-accent/20"
              />
            </div>
          </div>

          <!-- COD notice -->
          <div
            class="flex items-center gap-3 rounded-xl border border-border-subtle bg-app-bg-raised px-4 py-3"
          >
            <span
              class="material-symbols-outlined select-none text-[22px] leading-none text-brand"
              style="font-variation-settings: 'FILL' 1"
              >local_shipping</span
            >
            <div>
              <p class="text-sm font-medium text-fg">{{ t('order.cod') }}</p>
              <p class="text-xs text-fg-muted">{{ t('checkout.cod_sub') }}</p>
            </div>
          </div>

          <div class="flex justify-end pt-1">
            <button
              type="submit"
              class="rounded-xl bg-brand px-8 py-2.5 text-sm font-semibold text-white hover:bg-brand-hover"
            >
              {{ t('checkout.review_order') }}
            </button>
          </div>
        </form>
      </div>

      <!-- ── Steps 2 + 3: shared order layout ───────────────────────── -->
      <template v-else-if="step === 2 || step === 3">
        <!-- Order meta (confirmation only) -->
        <div
          v-if="step === 3 && placedOrder"
          class="grid grid-cols-2 gap-4 border-b border-border-subtle px-6 py-5 sm:grid-cols-4"
        >
          <div>
            <p class="text-xs text-fg-muted">{{ t('order.delivery_date') }}</p>
            <p class="mt-0.5 text-sm font-semibold text-fg" dir="ltr">{{ estimatedDelivery }}</p>
          </div>
          <div>
            <p class="text-xs text-fg-muted">{{ t('order.id') }}</p>
            <p class="mt-0.5 text-sm font-semibold text-fg" dir="ltr">
              #{{ placedOrder.id.slice(0, 10) }}
            </p>
          </div>
          <div>
            <p class="text-xs text-fg-muted">{{ t('order.payment') }}</p>
            <div class="mt-1 flex items-center gap-1.5">
              <span
                class="material-symbols-outlined select-none text-[16px] leading-none text-brand"
                style="font-variation-settings: 'FILL' 1"
                >payments</span
              >
              <span class="text-xs font-medium text-fg">{{ t('order.cod') }}</span>
            </div>
          </div>
          <div>
            <p class="text-xs text-fg-muted">{{ t('order.address') }}</p>
            <p class="mt-0.5 truncate text-sm font-semibold text-fg">
              {{ form.street }}, {{ form.city }}
            </p>
          </div>
        </div>

        <!-- Items table -->
        <div class="overflow-x-auto">
          <table class="w-full min-w-[480px]">
            <thead>
              <tr class="border-b border-border-subtle">
                <th
                  class="px-6 py-4 text-start text-xs font-medium uppercase tracking-wide text-fg-muted"
                >
                  {{ t('order.product') }}
                </th>
                <th
                  class="px-4 py-4 text-center text-xs font-medium uppercase tracking-wide text-fg-muted"
                >
                  {{ t('order.shipping') }}
                </th>
                <th
                  class="px-4 py-4 text-center text-xs font-medium uppercase tracking-wide text-fg-muted"
                >
                  {{ t('order.quantity') }}
                </th>
                <th
                  class="px-6 py-4 text-end text-xs font-medium uppercase tracking-wide text-fg-muted"
                >
                  {{ t('order.total') }}
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border-subtle">
              <!-- Step 2: cart items with editable quantity -->
              <template v-if="step === 2">
                <tr v-for="(item, i) in cart.cart?.items ?? []" :key="item.id">
                  <td class="px-6 py-4">
                    <div class="flex items-center gap-3">
                      <div class="h-14 w-14 shrink-0 overflow-hidden rounded-lg bg-app-bg-sunken">
                        <img
                          v-if="item.product.thumbnail_url"
                          :src="item.product.thumbnail_url"
                          :alt="item.product.name"
                          class="h-full w-full object-cover"
                        />
                        <div v-else class="flex h-full w-full items-center justify-center">
                          <span
                            class="material-symbols-outlined select-none text-[28px] leading-none text-fg-faint"
                            >image</span
                          >
                        </div>
                      </div>
                      <div>
                        <p class="text-sm font-semibold text-fg">{{ item.product.name }}</p>
                        <p v-if="item.product.category_name" class="text-xs text-fg-muted">
                          {{ item.product.category_name }}
                        </p>
                        <p class="text-xs font-medium text-brand">
                          {{ formatCurrency(item.product.price, currentLocale) }}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td class="px-4 py-4 text-center text-sm text-fg">{{ itemShipping(i) }}</td>
                  <td class="px-4 py-4">
                    <div class="flex items-center justify-center gap-2">
                      <button
                        type="button"
                        :disabled="item.quantity <= 1"
                        class="flex h-7 w-7 items-center justify-center rounded-full border border-border text-fg hover:bg-app-bg-raised disabled:opacity-40"
                        @click="cart.updateQuantity(item.id, item.quantity - 1)"
                      >
                        <span class="material-symbols-outlined select-none text-[14px] leading-none"
                          >remove</span
                        >
                      </button>
                      <span class="w-6 text-center text-sm font-medium text-fg">{{
                        item.quantity
                      }}</span>
                      <button
                        type="button"
                        class="flex h-7 w-7 items-center justify-center rounded-full border border-border text-fg hover:bg-app-bg-raised"
                        @click="cart.updateQuantity(item.id, item.quantity + 1)"
                      >
                        <span class="material-symbols-outlined select-none text-[14px] leading-none"
                          >add</span
                        >
                      </button>
                    </div>
                  </td>
                  <td class="px-6 py-4 text-end text-sm font-semibold text-brand">
                    {{ formatCurrency(item.product.price * item.quantity, currentLocale) }}
                  </td>
                </tr>
              </template>

              <!-- Step 3: placed order items (read-only) -->
              <template v-else-if="step === 3 && placedOrder">
                <tr v-for="(item, i) in placedOrder.items" :key="item.id">
                  <td class="px-6 py-4">
                    <div class="flex items-center gap-3">
                      <div
                        class="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-app-bg-sunken"
                      >
                        <span
                          class="material-symbols-outlined select-none text-[28px] leading-none text-fg-faint"
                          >shopping_bag</span
                        >
                      </div>
                      <div>
                        <p class="text-sm font-semibold text-fg">{{ item.product_name }}</p>
                        <p class="text-xs font-medium text-brand">
                          {{ formatCurrency(item.unit_price, currentLocale) }}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td class="px-4 py-4 text-center text-sm text-fg">{{ itemShipping(i) }}</td>
                  <td class="px-4 py-4 text-center">
                    <span
                      class="inline-flex h-7 min-w-[2rem] items-center justify-center rounded-full border border-border px-2 text-sm font-medium text-fg"
                    >
                      {{ item.quantity }}
                    </span>
                  </td>
                  <td class="px-6 py-4 text-end text-sm font-semibold text-brand">
                    {{ formatCurrency(item.subtotal, currentLocale) }}
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <!-- Totals -->
        <div class="grid gap-4 border-t border-border-subtle px-6 py-5 sm:grid-cols-2">
          <div class="space-y-2 rounded-xl border border-border-subtle bg-app-bg-raised p-4">
            <div class="flex justify-between text-sm text-fg-muted">
              <span>{{ t('order.shipping') }}</span>
              <span>{{ formatCurrency(DELIVERY_FEE, currentLocale) }}</span>
            </div>
            <div class="flex justify-between text-sm text-fg-muted">
              <span>{{ t('order.taxes') }}</span>
              <span>{{ formatCurrency(TAXES, currentLocale) }}</span>
            </div>
          </div>
          <div class="space-y-2 rounded-xl border border-border-subtle bg-app-bg-raised p-4">
            <div class="flex justify-between text-sm text-fg-muted">
              <span>{{ t('order.subtotal') }}</span>
              <span>{{
                formatCurrency(
                  step === 3 && placedOrder ? placedOrder.total : subtotal,
                  currentLocale,
                )
              }}</span>
            </div>
            <div
              class="flex justify-between border-t border-border-subtle pt-2 text-sm font-bold text-fg"
            >
              <span>{{ t('order.total') }}</span>
              <span>{{
                formatCurrency(step === 3 && placedOrder ? placedOrder.total : total, currentLocale)
              }}</span>
            </div>
          </div>
        </div>

        <p v-if="error" class="px-6 pb-2 text-sm text-danger">{{ error }}</p>

        <!-- Action buttons -->
        <div class="flex gap-3 border-t border-border-subtle px-6 py-5">
          <button
            v-if="step === 2"
            type="button"
            class="flex-1 rounded-xl border border-border bg-fg py-3 text-sm font-semibold text-app-bg hover:opacity-90"
            @click="step = 1"
          >
            {{ t('checkout.back') }}
          </button>
          <RouterLink
            v-else
            to="/"
            class="flex-1 rounded-xl border border-border bg-fg py-3 text-center text-sm font-semibold text-app-bg hover:opacity-90"
          >
            {{ t('checkout.back_to_shop') }}
          </RouterLink>

          <button
            v-if="step === 2"
            type="button"
            :disabled="submitting || !cart.cart?.items.length"
            class="flex-1 rounded-xl bg-brand py-3 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-50"
            @click="placeOrder"
          >
            {{ submitting ? t('checkout.placing') : t('checkout.place_order', 'Place Order') }}
          </button>
          <RouterLink
            v-else
            :to="placedOrder ? { path: '/account', query: { order: placedOrder.id } } : '/account'"
            class="flex-1 rounded-xl bg-brand py-3 text-center text-sm font-semibold text-white hover:bg-brand-hover"
          >
            {{ t('checkout.view_orders') }}
          </RouterLink>
        </div>
      </template>
    </div>
  </div>
</template>
