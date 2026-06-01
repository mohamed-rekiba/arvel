import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  authLoginApiAuthLoginPost,
  authMeApiAuthMeGet,
  authRegisterApiAuthRegisterPost,
} from '@/api/auth/auth'
import type { MeOut } from '@/api/schemas'
import { ADMIN_PERMISSIONS } from '@/types'

const TOKEN_KEY = 'access_token'
const USER_KEY = 'current_user'

function readStoredUser(): MeOut | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as MeOut
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<MeOut | null>(readStoredUser())
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => user.value !== null)

  const permissions = computed(() => new Set(user.value?.permissions ?? []))

  const hasAdminAccess = computed(() =>
    ADMIN_PERMISSIONS.some((permission) => permissions.value.has(permission)),
  )

  function hasPermission(permission: string): boolean {
    return permissions.value.has(permission)
  }

  function persistUser(next: MeOut | null): void {
    user.value = next
    if (next) {
      localStorage.setItem(USER_KEY, JSON.stringify(next))
    } else {
      localStorage.removeItem(USER_KEY)
    }
  }

  function persistToken(token: string | null): void {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  }

  async function login(email: string, password: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { access_token } = await authLoginApiAuthLoginPost({ email, password })
      persistToken(access_token)
      const me = await authMeApiAuthMeGet()
      persistUser(me)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Login failed'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function register(name: string, email: string, password: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await authRegisterApiAuthRegisterPost({
        name,
        email,
        password,
        password_confirmation: password,
      })
      await login(email, password)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Registration failed'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function hydrate(): Promise<void> {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      persistUser(null)
      return
    }
    try {
      const me = await authMeApiAuthMeGet()
      persistUser(me)
    } catch {
      logout()
    }
  }

  function logout(): void {
    persistToken(null)
    persistUser(null)
    error.value = null
  }

  return {
    user,
    loading,
    error,
    isAuthenticated,
    hasAdminAccess,
    hasPermission,
    login,
    register,
    hydrate,
    logout,
  }
})
