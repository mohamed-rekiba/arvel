import { useAuthStore } from '@/stores/auth'

export function useAuth() {
  const store = useAuthStore()

  function hasAdminAccess(user?: { permissions?: string[] } | null): boolean {
    const u = user ?? store.user
    return Boolean(
      u?.permissions?.some(
        (p) =>
          p.startsWith('products.') ||
          p.startsWith('orders.') ||
          p.startsWith('users.') ||
          p.startsWith('roles.'),
      ),
    )
  }

  return {
    user: store.user,
    isAuthenticated: store.isAuthenticated,
    hasAdminAccess,
    hasPermission: store.hasPermission,
    login: store.login,
    register: store.register,
    logout: store.logout,
  }
}
