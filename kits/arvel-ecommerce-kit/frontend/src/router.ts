import { createRouter, createWebHistory } from 'vue-router'
import { hasStoredSession, clearSession } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    requiresAdmin?: boolean
    // Backend permission(s) the route's primary endpoint enforces. The guard
    // mirrors the API so deep links can't render a shell the API will 403.
    permission?: string | readonly string[]
    permissionMatch?: 'all' | 'any'
  }
}

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior() {
    return { top: 0 }
  },
  routes: [
    {
      path: '/',
      component: () => import('@/layouts/StorefrontLayout.vue'),
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('@/pages/StorefrontHome.vue'),
        },
        {
          path: '/products',
          name: 'products',
          component: () => import('@/pages/StorefrontProducts.vue'),
        },
        {
          path: '/products/:slug',
          name: 'product-detail',
          component: () => import('@/pages/StorefrontProductDetail.vue'),
        },
        {
          path: '/categories/:slug',
          name: 'category',
          component: () => import('@/pages/StorefrontCategoryPage.vue'),
        },
        {
          path: '/search',
          name: 'search',
          component: () => import('@/pages/StorefrontSearch.vue'),
        },
        {
          path: '/cart',
          name: 'cart',
          meta: { requiresAuth: true },
          component: () => import('@/pages/StorefrontCart.vue'),
        },
        {
          path: '/checkout',
          name: 'checkout',
          meta: { requiresAuth: true },
          component: () => import('@/pages/StorefrontCheckout.vue'),
        },
        {
          path: '/account',
          name: 'account',
          meta: { requiresAuth: true },
          component: () => import('@/pages/StorefrontAccount.vue'),
        },
        {
          path: '/account/orders',
          name: 'account-orders',
          meta: { requiresAuth: true },
          component: () => import('@/pages/StorefrontAccount.vue'),
        },
        {
          path: '/login',
          name: 'login',
          component: () => import('@/pages/StorefrontAuth.vue'),
        },
        {
          path: '/register',
          name: 'register',
          component: () => import('@/pages/StorefrontAuth.vue'),
          props: { defaultTab: 'register' },
        },
      ],
    },
    {
      path: '/admin/login',
      name: 'admin-login',
      component: () => import('@/pages/StorefrontAuth.vue'),
      props: { adminRedirect: true },
    },
    {
      path: '/admin',
      component: () => import('@/layouts/AdminLayout.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        { path: '', redirect: '/admin/dashboard' },
        {
          path: '/admin/dashboard',
          name: 'admin-dashboard',
          component: () => import('@/pages/AdminDashboard.vue'),
        },
        {
          path: '/admin/products',
          name: 'admin-products',
          component: () => import('@/pages/AdminCatalogPage.vue'),
          props: { catalog: 'products' },
          meta: { permission: 'products.view' },
        },
        {
          path: '/admin/categories',
          name: 'admin-categories',
          component: () => import('@/pages/AdminCatalogPage.vue'),
          props: { catalog: 'categories' },
          meta: { permission: 'categories.view' },
        },
        {
          path: '/admin/vendors',
          name: 'admin-vendors',
          component: () => import('@/pages/AdminCatalogPage.vue'),
          props: { catalog: 'vendors' },
          meta: { permission: 'vendors.view' },
        },
        {
          path: '/admin/products/new',
          name: 'admin-product-new',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: { catalog: 'products', mode: 'create' },
          meta: { permission: 'products.create' },
        },
        {
          path: '/admin/categories/new',
          name: 'admin-category-new',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: { catalog: 'categories', mode: 'create' },
          meta: { permission: 'categories.create' },
        },
        {
          path: '/admin/vendors/new',
          name: 'admin-vendor-new',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: { catalog: 'vendors', mode: 'create' },
          meta: { permission: 'vendors.create' },
        },
        {
          path: '/admin/products/:editId/edit',
          name: 'admin-product-edit',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: (route) => ({ catalog: 'products', id: route.params.editId }),
          meta: { permission: 'products.view' },
        },
        {
          path: '/admin/categories/:editId/edit',
          name: 'admin-category-edit',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: (route) => ({ catalog: 'categories', id: route.params.editId }),
          meta: { permission: 'categories.view' },
        },
        {
          path: '/admin/vendors/:editId/edit',
          name: 'admin-vendor-edit',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: (route) => ({ catalog: 'vendors', id: route.params.editId }),
          meta: { permission: 'vendors.view' },
        },
        {
          path: '/admin/orders',
          name: 'admin-orders',
          component: () => import('@/pages/AdminListPage.vue'),
          props: { listType: 'orders' },
          meta: { permission: 'orders.view' },
        },
        {
          path: '/admin/orders/:orderId',
          name: 'admin-order-detail',
          component: () => import('@/pages/AdminOrderDetailPage.vue'),
          meta: { permission: 'orders.view' },
        },
        {
          path: '/admin/users',
          name: 'admin-users',
          component: () => import('@/pages/AdminListPage.vue'),
          props: { listType: 'users' },
          meta: { permission: 'users.manage' },
        },
        {
          path: '/admin/users/:userId',
          name: 'admin-user-detail',
          component: () => import('@/pages/AdminUserDetailPage.vue'),
          meta: { permission: 'users.manage' },
        },
        {
          path: '/admin/roles',
          name: 'admin-roles',
          component: () => import('@/pages/AdminRolesPage.vue'),
          meta: { permission: 'roles.manage' },
        },
        {
          path: '/admin/permissions',
          name: 'admin-permissions',
          component: () => import('@/pages/AdminPermissionsPage.vue'),
          meta: { permission: 'roles.manage' },
        },
        {
          path: '/admin/translations',
          name: 'admin-translations',
          component: () => import('@/pages/AdminPlaceholderPage.vue'),
          props: { pageType: 'translations' },
          // Backend requires both (match="all"); mirror it.
          meta: { permission: ['products.view', 'categories.view'], permissionMatch: 'all' },
        },
        {
          path: '/admin/analytics',
          name: 'admin-analytics',
          component: () => import('@/pages/AdminPlaceholderPage.vue'),
          props: { pageType: 'coming-soon', title: 'Analytics' },
          meta: { permission: 'analytics.view' },
        },
        {
          path: '/admin/settings',
          name: 'admin-settings',
          component: () => import('@/pages/AdminPlaceholderPage.vue'),
          props: { pageType: 'coming-soon', title: 'Settings' },
          meta: { permission: 'settings.view' },
        },
        {
          // Nested so an unknown /admin/* path inherits requiresAuth + requiresAdmin
          // (and the admin shell) instead of rendering unguarded at the top level.
          path: '/admin/:pathMatch(.*)*',
          name: 'admin-catch-all',
          component: () => import('@/pages/AdminPlaceholderPage.vue'),
          props: { pageType: 'coming-soon', title: 'Not found' },
        },
      ],
    },
  ],
})

function satisfiesPermission(
  auth: ReturnType<typeof useAuthStore>,
  permission: string | readonly string[],
  match: 'all' | 'any' = 'all',
): boolean {
  const perms = typeof permission === 'string' ? [permission] : permission
  return match === 'any'
    ? perms.some((p) => auth.hasPermission(p))
    : perms.every((p) => auth.hasPermission(p))
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // Admin routes carry both requiresAuth and requiresAdmin. Handle them first
  // so unauthenticated users land on the admin login, not the storefront one.
  if (to.meta.requiresAdmin) {
    // Re-fetch /me on every admin entry so a role/permission change applies on
    // the next navigation instead of lingering in the cached session until
    // re-login. Admin traffic is low, so the extra request is cheap.
    if (hasStoredSession()) {
      await auth.hydrate()
    }
    if (!auth.isAuthenticated) {
      return { name: 'admin-login', query: { redirect: to.fullPath } }
    }
    if (!auth.hasAdminAccess) {
      return { name: 'home' }
    }
    // Per-route check mirrors the backend permission. Dashboard has none, so
    // it's the safe fallback any admin can reach.
    if (
      to.meta.permission &&
      !satisfiesPermission(auth, to.meta.permission, to.meta.permissionMatch)
    ) {
      return { name: 'admin-dashboard' }
    }
    return true
  }

  if (!auth.user && hasStoredSession()) {
    await auth.hydrate()
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  return true
})

export { clearSession }
export default router
