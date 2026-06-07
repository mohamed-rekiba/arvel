<script setup lang="ts">
import { useDark, useScroll } from '@vueuse/core'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  applyDocumentLocale,
  pickLocalized,
  setStoredLocale,
  SUPPORTED_LOCALES,
  toSupportedLocale,
} from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import { useCartStore } from '@/stores/cart'
import { useCategoriesStore } from '@/stores/categories'
import { useStorefrontStore } from '@/stores/storefront'
import type { SupportedLocale } from '@/types'
import ArvelLogo from '@/components/ArvelLogo.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const cart = useCartStore()
const categoriesStore = useCategoriesStore()
const storefrontStore = useStorefrontStore()
const { locale, t } = useI18n({ useScope: 'global' })

const searchQuery = ref('')
const { y } = useScroll(window)
const isScrolled = computed(() => y.value > 8)

const isDark = useDark({
  selector: 'html',
  attribute: 'data-theme',
  valueDark: 'dark',
  valueLight: 'light',
  storageKey: 'theme',
})

const iconMap: Record<string, string> = {
  mobiles: 'phone_iphone',
  phones: 'phone_iphone',
  smartphones: 'phone_iphone',
  laptops: 'laptop_mac',
  speakers: 'speaker',
  'tv-sets': 'tv',
  watches: 'watch',
  headsets: 'headphones',
  electronics: 'devices',
  books: 'menu_book',
  fiction: 'auto_stories',
}

const currentLocale = computed(() => toSupportedLocale(locale.value))

const categoryLinks = computed(() =>
  categoriesStore.list.map((cat) => {
    const enSlug = pickLocalized(cat.slug, 'en') || Object.values(cat.slug ?? {})[0] || ''
    const slug = pickLocalized(cat.slug, currentLocale.value) || enSlug
    const label =
      pickLocalized(cat.name, currentLocale.value) || Object.values(cat.name ?? {})[0] || ''
    return { slug, label, icon: iconMap[enSlug] ?? 'shopping_bag' }
  }),
)

onMounted(() => categoriesStore.load())

watch(
  () => auth.isAuthenticated,
  (authenticated: boolean) => {
    if (authenticated) void cart.load()
    else cart.clear()
  },
)

function handleSearch(event: Event): void {
  event.preventDefault()
  const q = searchQuery.value.trim()
  if (!q) return
  void router.push({ name: 'search', query: { q } })
}

function changeLocale(next: SupportedLocale): void {
  locale.value = next
  setStoredLocale(next)
  applyDocumentLocale(next)
}

async function handleLogout(): Promise<void> {
  auth.logout()
  cart.clear()
  await router.push({ name: 'home' })
}
</script>

<template>
  <div class="flex min-h-screen flex-col bg-app-bg">
    <!-- ── Admin topbar (visible to users with product edit access) ────── -->
    <!-- Midnight = #26223C, the framework announce-bar chrome color (same in light and dark) -->
    <div
      v-if="auth.hasPermission('products.view')"
      class="flex items-center gap-1 bg-[#26223C] px-4 py-1.5 text-xs font-medium text-white/80 lg:px-8"
    >
      <span
        class="material-symbols-outlined select-none text-[16px]! leading-none text-white/60 rtl:rotate-90"
        aria-hidden="true"
        >build</span
      >
      <span>{{ t('nav.admin_mode', 'Admin mode') }}</span>
      <span class="text-white/40">·</span>
      <RouterLink
        v-if="route.name === 'product-detail' && storefrontStore.currentProductId"
        :to="{ name: 'admin-product-edit', params: { editId: storefrontStore.currentProductId } }"
        class="text-accent underline underline-offset-2 hover:text-cyan-300"
      >
        {{ t('nav.edit_product', 'Edit this product') }}
      </RouterLink>
      <RouterLink
        v-else
        :to="{ name: 'admin-products' }"
        class="text-accent underline underline-offset-2 hover:text-cyan-300"
      >
        {{ t('nav.manage_products', 'Manage products') }}
      </RouterLink>
      <div class="flex-1" />
      <RouterLink
        :to="{ name: 'admin-dashboard' }"
        class="text-accent underline underline-offset-2 hover:text-cyan-300"
        dir="ltr"
      >
        {{ t('nav.admin_panel', 'Admin panel →') }}
      </RouterLink>
    </div>

    <!-- ── Main header ─────────────────────────────────────────────────── -->
    <header
      class="sticky top-0 z-50 transition-shadow duration-200"
      :class="{ 'shadow-md': isScrolled }"
    >
      <!-- Row 1: dark bar — logo, nav, search, icons -->
      <div class="bg-header-bg" style="background-color: var(--color-header-bg)">
        <div class="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 lg:px-8">
          <RouterLink to="/" class="flex items-center shrink-0" aria-label="Arvel home">
            <ArvelLogo variant="dark" :height="35" />
          </RouterLink>

          <nav class="hidden items-center gap-5 md:flex">
            <RouterLink
              to="/"
              class="text-sm font-medium text-white/70 transition hover:text-white"
              :class="{
                'text-white font-semibold underline decoration-accent underline-offset-4':
                  route.name === 'home',
              }"
            >
              {{ t('nav.home', 'Home') }}
            </RouterLink>
            <RouterLink
              to="/products"
              class="text-sm font-medium text-white/70 transition hover:text-white"
              :class="{
                'text-white font-semibold underline decoration-accent underline-offset-4':
                  route.name === 'products',
              }"
            >
              {{ t('nav.products', 'Products') }}
            </RouterLink>
          </nav>

          <div class="flex-1" />

          <form class="hidden max-w-xs flex-1 md:block lg:max-w-sm" @submit="handleSearch">
            <div class="relative">
              <span
                class="pointer-events-none absolute inset-y-0 start-0 flex items-center ps-3 text-white/50"
              >
                <span
                  class="material-symbols-outlined select-none text-[20px] leading-none"
                  aria-hidden="true"
                  >search</span
                >
              </span>
              <input
                v-model="searchQuery"
                type="search"
                :placeholder="t('search.placeholder', 'Search products…')"
                class="w-full rounded-full border border-white/20 bg-white/10 py-1.5 pe-4 ps-9 text-sm text-white placeholder-white/50 outline-none transition focus:border-accent focus:bg-white/15 focus:ring-2 focus:ring-accent/30"
              />
            </div>
          </form>

          <!-- Cart -->
          <RouterLink
            to="/cart"
            class="relative flex h-9 w-9 items-center justify-center rounded-full text-white transition hover:bg-white/15"
            :aria-label="t('nav.cart', 'Cart')"
          >
            <span
              class="material-symbols-outlined select-none text-[22px] leading-none"
              aria-hidden="true"
              >shopping_cart</span
            >
            <span
              v-if="cart.itemCount > 0"
              class="absolute -end-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-cart-cta px-1 text-xs font-bold text-white"
            >
              {{ cart.itemCount }}
            </span>
          </RouterLink>

          <!-- Account dropdown -->
          <div class="relative group">
            <button
              type="button"
              class="flex h-9 w-9 items-center justify-center rounded-full text-white transition hover:bg-white/15"
              :aria-label="t('nav.account', 'Account')"
            >
              <span
                class="material-symbols-outlined select-none text-[22px] leading-none"
                aria-hidden="true"
                >person</span
              >
            </button>
            <div
              class="invisible absolute end-0 top-full z-50 w-52 opacity-0 transition group-hover:visible group-hover:opacity-100"
            >
              <div class="mt-2 rounded-xl border border-border bg-app-bg py-2 shadow-xl">
                <template v-if="auth.isAuthenticated">
                  <p class="truncate px-4 py-2 text-sm font-semibold text-fg">
                    {{ auth.user?.name }}
                  </p>
                  <hr class="mx-3 my-1 border-border" />
                  <RouterLink
                    to="/account"
                    class="block px-4 py-2 text-sm text-fg-muted hover:bg-brand-soft hover:text-fg"
                  >
                    {{ t('nav.orders', 'My Orders') }}
                  </RouterLink>
                  <RouterLink
                    v-if="auth.hasAdminAccess"
                    to="/admin"
                    class="block px-4 py-2 text-sm text-fg-muted hover:bg-brand-soft hover:text-fg"
                  >
                    {{ t('nav.admin', 'Admin') }}
                  </RouterLink>
                  <button
                    type="button"
                    class="block w-full px-4 py-2 text-start text-sm text-fg-muted hover:bg-brand-soft hover:text-fg"
                    @click="handleLogout"
                  >
                    {{ t('nav.logout', 'Log out') }}
                  </button>
                </template>
                <template v-else>
                  <RouterLink
                    to="/login"
                    class="block px-4 py-2 text-sm text-fg-muted hover:bg-brand-soft hover:text-fg"
                  >
                    {{ t('nav.login', 'Log in') }}
                  </RouterLink>
                </template>
              </div>
            </div>
          </div>

          <button
            type="button"
            class="flex h-9 w-9 items-center justify-center rounded-full text-white transition hover:bg-white/15"
            :aria-label="t('nav.theme', 'Toggle theme')"
            @click="isDark = !isDark"
          >
            <span
              class="material-symbols-outlined select-none text-[22px] leading-none"
              aria-hidden="true"
            >
              {{ isDark ? 'light_mode' : 'dark_mode' }}
            </span>
          </button>

          <select
            :value="locale"
            class="rounded-lg border border-white/20 bg-transparent px-2 py-1 text-sm text-white outline-none focus:border-accent"
            @change="changeLocale(($event.target as HTMLSelectElement).value as SupportedLocale)"
          >
            <option
              v-for="loc in SUPPORTED_LOCALES"
              :key="loc"
              :value="loc"
              class="text-fg bg-app-bg"
            >
              {{ loc.toUpperCase() }}
            </option>
          </select>
        </div>
      </div>

      <!-- Row 2: white category bar -->
      <div class="border-b border-border bg-app-bg">
        <div
          class="mx-auto flex h-12 max-w-7xl items-center gap-1 overflow-x-auto px-4 scrollbar-hide lg:px-8"
        >
          <RouterLink
            v-for="cat in categoryLinks"
            :key="cat.slug"
            :to="`/products?category=${cat.slug}`"
            class="flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-fg-muted transition hover:bg-brand-soft hover:text-brand"
            :class="{
              'bg-brand text-white hover:bg-brand-hover hover:text-white':
                route.query.category === cat.slug,
            }"
          >
            <span
              class="material-symbols-outlined select-none text-[18px] leading-none"
              aria-hidden="true"
              >{{ cat.icon }}</span
            >
            <span>{{ cat.label }}</span>
          </RouterLink>
        </div>
      </div>
    </header>

    <main class="flex-1">
      <RouterView />
    </main>

    <!-- ── Footer ──────────────────────────────────────────────────────── -->
    <footer class="border-t border-border bg-app-bg-raised">
      <div class="mx-auto grid max-w-7xl gap-10 px-4 py-14 md:grid-cols-3 lg:px-8">
        <div>
          <ArvelLogo :variant="isDark ? 'dark' : 'light'" :height="28" />
          <p class="mt-2 max-w-xs text-sm text-fg-muted">
            {{ t('footer.tagline', 'Thoughtfully designed essentials for everyday life.') }}
          </p>
        </div>
        <div>
          <h3 class="text-sm font-semibold uppercase tracking-wide text-fg-muted">
            {{ t('footer.quick_links', 'Quick Links') }}
          </h3>
          <ul class="mt-4 space-y-2 text-sm text-fg-muted">
            <li>
              <RouterLink to="/products" class="hover:text-brand">
                {{ t('footer.products', 'Products') }}
              </RouterLink>
            </li>
            <li>
              <RouterLink to="/search" class="hover:text-brand">
                {{ t('footer.search', 'Search') }}
              </RouterLink>
            </li>
            <li>
              <RouterLink to="/account" class="hover:text-brand">
                {{ t('footer.account', 'Account') }}
              </RouterLink>
            </li>
          </ul>
        </div>
        <div>
          <h3 class="text-sm font-semibold uppercase tracking-wide text-fg-muted">
            {{ t('footer.support', 'Support') }}
          </h3>
          <ul class="mt-4 space-y-2 text-sm text-fg-muted">
            <li>{{ t('footer.shipping', 'Free shipping over $75') }}</li>
            <li>{{ t('footer.returns', '30-day returns') }}</li>
            <li><a href="mailto:help@arvel.dev" class="hover:text-brand">help@arvel.dev</a></li>
          </ul>
        </div>
      </div>
      <div class="border-t border-border py-6 text-center text-xs text-fg-faint">
        © {{ new Date().getFullYear() }} {{ t('footer.copyright', 'Arvel. All rights reserved.') }}
      </div>
    </footer>
  </div>
</template>
