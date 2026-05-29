import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { routeParam } from '@/lib/i18n'

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
          path: 'products',
          name: 'products',
          component: () => import('@/pages/StorefrontProducts.vue'),
        },
        {
          path: 'products/:slug',
          name: 'product-detail',
          component: () => import('@/pages/StorefrontProductDetail.vue'),
        },
        {
          path: 'categories/:slug',
          name: 'category',
          component: () => import('@/pages/StorefrontCategoryPage.vue'),
        },
        {
          path: 'search',
          name: 'search',
          component: () => import('@/pages/StorefrontSearch.vue'),
        },
        {
          path: 'cart',
          name: 'cart',
          meta: { requiresAuth: true },
          component: () => import('@/pages/StorefrontCart.vue'),
        },
        {
          path: 'checkout',
          name: 'checkout',
          meta: { requiresAuth: true },
          component: () => import('@/pages/StorefrontCheckout.vue'),
        },
        {
          path: 'account',
          name: 'account',
          meta: { requiresAuth: true },
          component: () => import('@/pages/StorefrontAccount.vue'),
        },
        {
          path: 'login',
          name: 'login',
          component: () => import('@/pages/StorefrontAuth.vue'),
        },
        {
          path: 'register',
          redirect: { name: 'login', query: { tab: 'register' } },
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
      meta: { requiresAdmin: true },
      children: [
        { path: '', redirect: '/admin/dashboard' },
        {
          path: 'dashboard',
          name: 'admin-dashboard',
          component: () => import('@/pages/AdminDashboard.vue'),
        },
        // Catalog list pages
        {
          path: 'products',
          name: 'admin-products',
          component: () => import('@/pages/AdminCatalogPage.vue'),
          props: { catalog: 'products' },
        },
        {
          path: 'categories',
          name: 'admin-categories',
          component: () => import('@/pages/AdminCatalogPage.vue'),
          props: { catalog: 'categories' },
        },
        {
          path: 'vendors',
          name: 'admin-vendors',
          component: () => import('@/pages/AdminCatalogPage.vue'),
          props: { catalog: 'vendors' },
        },
        // Catalog edit pages
        {
          path: 'products/:id/edit',
          name: 'admin-product-edit',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: (route) => ({ catalog: 'products', id: routeParam(route.params.id) }),
        },
        {
          path: 'categories/:id/edit',
          name: 'admin-category-edit',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: (route) => ({ catalog: 'categories', id: routeParam(route.params.id) }),
        },
        {
          path: 'vendors/:id/edit',
          name: 'admin-vendor-edit',
          component: () => import('@/pages/AdminCatalogEditPage.vue'),
          props: (route) => ({ catalog: 'vendors', id: routeParam(route.params.id) }),
        },
        // Orders
        {
          path: 'orders',
          name: 'admin-orders',
          component: () => import('@/pages/AdminListPage.vue'),
          props: { listType: 'orders' },
        },
        {
          path: 'orders/:id',
          name: 'admin-order-detail',
          component: () => import('@/pages/AdminOrderDetailPage.vue'),
        },
        // Users
        {
          path: 'users',
          name: 'admin-users',
          component: () => import('@/pages/AdminListPage.vue'),
          props: { listType: 'users' },
        },
        {
          path: 'users/:id',
          name: 'admin-user-detail',
          component: () => import('@/pages/AdminUserDetailPage.vue'),
        },
        // RBAC
        {
          path: 'roles',
          name: 'admin-roles',
          component: () => import('@/pages/AdminRolesPage.vue'),
        },
        {
          path: 'permissions',
          name: 'admin-permissions',
          component: () => import('@/pages/AdminPermissionsPage.vue'),
        },
      ],
    },
  ],
})

function isAdminRoute(to: RouteLocationNormalized): boolean {
  return to.path.startsWith('/admin') && to.path !== '/admin/login'
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (!auth.user && localStorage.getItem('access_token')) {
    await auth.hydrate()
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (isAdminRoute(to)) {
    if (!auth.isAuthenticated) {
      return { name: 'admin-login', query: { redirect: to.fullPath } }
    }
    if (!auth.hasAdminAccess) {
      return { name: 'home' }
    }
  }

  return true
})

export default router
