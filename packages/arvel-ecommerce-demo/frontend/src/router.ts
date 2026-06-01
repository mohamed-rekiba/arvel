import { createRouter, createWebHistory } from 'vue-router'
import { hasStoredSession, loadCurrentUser, clearSession } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

function hasAdminAccess(user: { permissions?: string[] } | null): boolean {
  if (!user) return false
  return Boolean(
    user.permissions?.some(
      (p) =>
        p.startsWith('products.') ||
        p.startsWith('orders.') ||
        p.startsWith('users.') ||
        p.startsWith('roles.'),
    ),
  )
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
      props: { adminRedirect: true, redirectTo: '/admin' },
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
        },
        {
          path: '/admin/categories',
          name: 'admin-categories',
          component: () => import('@/pages/AdminCatalogPage.vue'),
          props: { catalog: 'categories' },
        },
        {
          path: '/admin/vendors',
          name: 'admin-vendors',
          component: () => import('@/pages/AdminCatalogPage.vue'),
          props: { catalog: 'vendors' },
        },
        {
          path: '/admin/products/new',
          name: 'admin-product-new',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: { catalog: 'products', mode: 'create' },
        },
        {
          path: '/admin/categories/new',
          name: 'admin-category-new',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: { catalog: 'categories', mode: 'create' },
        },
        {
          path: '/admin/vendors/new',
          name: 'admin-vendor-new',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: { catalog: 'vendors', mode: 'create' },
        },
        {
          path: '/admin/products/:editId/edit',
          name: 'admin-product-edit',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: (route) => ({ catalog: 'products', id: route.params.editId }),
        },
        {
          path: '/admin/categories/:editId/edit',
          name: 'admin-category-edit',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: (route) => ({ catalog: 'categories', id: route.params.editId }),
        },
        {
          path: '/admin/vendors/:editId/edit',
          name: 'admin-vendor-edit',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: (route) => ({ catalog: 'vendors', id: route.params.editId }),
        },
        {
          path: '/admin/orders',
          name: 'admin-orders',
          component: () => import('@/pages/AdminListPage.vue'),
          props: { listType: 'orders' },
        },
        {
          path: '/admin/orders/:orderId',
          name: 'admin-order-detail',
          component: () => import('@/pages/AdminOrderDetailPage.vue'),
        },
        {
          path: '/admin/users',
          name: 'admin-users',
          component: () => import('@/pages/AdminListPage.vue'),
          props: { listType: 'users' },
        },
        {
          path: '/admin/users/:userId',
          name: 'admin-user-detail',
          component: () => import('@/pages/AdminUserDetailPage.vue'),
        },
        {
          path: '/admin/roles',
          name: 'admin-roles',
          component: () => import('@/pages/AdminRolesPage.vue'),
        },
        {
          path: '/admin/permissions',
          name: 'admin-permissions',
          component: () => import('@/pages/AdminPermissionsPage.vue'),
        },
        {
          path: '/admin/translations',
          name: 'admin-translations',
          component: () => import('@/pages/AdminPlaceholderPage.vue'),
          props: { title: 'Translations' },
        },
        {
          path: '/admin/analytics',
          name: 'admin-analytics',
          component: () => import('@/pages/AdminPlaceholderPage.vue'),
          props: { title: 'Analytics' },
        },
        {
          path: '/admin/settings',
          name: 'admin-settings',
          component: () => import('@/pages/AdminPlaceholderPage.vue'),
          props: { title: 'Settings' },
        },
        {
          path: 'AdminUserDetailPage',
          redirect: '/admin/users',
        },
      ],
    },
    {
      path: '/admin/:pathMatch(.*)*',
      name: 'admin-catch-all',
      component: () => import('@/pages/AdminPlaceholderPage.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (!auth.user && hasStoredSession()) {
    await loadCurrentUser()
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.requiresAdmin) {
    if (!auth.isAuthenticated) {
      return { name: 'admin-login', query: { redirect: to.fullPath } }
    }
    const user = auth.user
    if (!hasAdminAccess(user)) {
      return { name: 'home' }
    }
  }

  return true
})

export { clearSession }
export default router
