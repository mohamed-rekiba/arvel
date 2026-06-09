export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

const TOKEN_KEY = 'access_token'
const USER_KEY = 'current_user'

let _onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(fn: () => void): void {
  _onUnauthorized = fn
}

export function hasStoredSession(): boolean {
  return Boolean(localStorage.getItem(TOKEN_KEY))
}

export function requireStoredAccessToken(): string {
  const token = localStorage.getItem(TOKEN_KEY)
  if (!token) throw new ApiError('Not authenticated', 401)
  return token
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

interface RequestConfig {
  url: string
  method: string
  headers?: Record<string, string>
  data?: unknown
  params?: Record<string, unknown>
  signal?: AbortSignal
}

type RequestOptions = Record<string, unknown>

export async function request<T>(config: RequestConfig, _options?: RequestOptions): Promise<T> {
  const { url, method, headers: configHeaders, data, params, signal } = config

  const headers: Record<string, string> = { ...configHeaders }

  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let fullUrl = url
  if (params) {
    const searchParams = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) {
        searchParams.set(k, String(v))
      }
    }
    const qs = searchParams.toString()
    if (qs) fullUrl = `${url}?${qs}`
  }

  const body = data !== undefined ? JSON.stringify(data) : undefined

  const response = await fetch(fullUrl, { method, headers, body, signal })

  if (!response.ok) {
    if (response.status === 401) {
      _onUnauthorized?.()
    }

    const errorBody = await response.json().catch(() => null)
    throw new ApiError(
      (errorBody as { error?: { message?: string } } | null)?.error?.message ??
        `Request failed: ${response.status}`,
      response.status,
      errorBody,
    )
  }

  if (response.status === 204) return undefined as T

  return response.json() as Promise<T>
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  // Merge headers — spreading ...init last would drop Content-Type whenever a
  // caller passes its own headers (e.g. Authorization), which makes the backend
  // skip JSON parsing and reject the body.
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers as Record<string, string> | undefined),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(
      (body as { error?: { message?: string } } | null)?.error?.message ??
        `Request failed: ${res.status}`,
      res.status,
      body,
    )
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function authorizedJson<T>(url: string, init?: RequestInit): Promise<T> {
  const token = requireStoredAccessToken()
  return json<T>(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(init?.headers as Record<string, string> | undefined),
    },
  })
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface AuthTokenResponse {
  access_token: string
}

export interface MeResponse {
  id: number
  name: string
  email: string
  locale: string
  theme: string
  roles: string[]
  permissions: string[]
}

export async function loginUser(email: string, password: string): Promise<AuthTokenResponse> {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(
      (body as { error?: { message?: string } } | null)?.error?.message ??
        `Request failed: ${res.status}`,
      res.status,
      body,
    )
  }
  return res.json() as Promise<AuthTokenResponse>
}

export async function registerUser(
  name: string,
  email: string,
  password: string,
  password_confirmation: string,
): Promise<void> {
  const res = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password, password_confirmation }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(
      (body as { error?: { message?: string } } | null)?.error?.message ??
        `Request failed: ${res.status}`,
      res.status,
      body,
    )
  }
}

export async function fetchCurrentUser(token?: string): Promise<MeResponse> {
  const t = token ?? requireStoredAccessToken()
  return json<MeResponse>('/api/auth/me', {
    headers: { Authorization: `Bearer ${t}` },
  })
}

export async function loadCurrentUser(): Promise<MeResponse | null> {
  if (!hasStoredSession()) return null
  try {
    return await fetchCurrentUser()
  } catch {
    clearSession()
    return null
  }
}

// ── Storefront products ───────────────────────────────────────────────────────

export interface ProductListResponse {
  data: StorefrontProduct[]
  total: number
}

export interface StorefrontProduct {
  id: number
  name: Record<string, string>
  slug: Record<string, string>
  short_description: Record<string, string>
  price: number
  stock: number
  image_url: string | null
  image_srcset: string | null
  vendor_name: string | null
}

// Usage: fetchProductList('/api/products', params)
export async function fetchProductList(
  url: '/api/products',
  params?: Record<string, unknown>,
): Promise<ProductListResponse> {
  const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : ''
  return json<ProductListResponse>(`${url}${qs}`)
}

export async function fetchProductBySlug(
  slug: string,
  params?: Record<string, string>,
): Promise<{ data: StorefrontProduct }> {
  // URL template: `/api/products/${encodeURIComponent(slug)}?${params}`
  const qs = params ? `?${new URLSearchParams(params).toString()}` : ''
  return json<{ data: StorefrontProduct }>(`/api/products/${encodeURIComponent(slug)}${qs}`)
}

export async function fetchCategory(slug: string): Promise<{ data: unknown }> {
  return json<{ data: unknown }>(`/api/categories/${encodeURIComponent(slug)}`)
}

export async function searchProducts(q: Record<string, string>): Promise<ProductListResponse> {
  const params = new URLSearchParams(q).toString()
  return fetch(`/api/search?${params}`).then((r) => r.json()) as Promise<ProductListResponse>
}

// ── Cart ──────────────────────────────────────────────────────────────────────

export interface CartResponse {
  items: CartItem[]
  total: number
}

export interface CartItem {
  id: string
  product_id: number
  quantity: number
  price: number
}

export interface DetailResponse<T> {
  data: T
}

export interface OrderSummary {
  id: string
  status: string
  total: number
  created_at: string
}

export async function fetchCart(): Promise<CartResponse> {
  return authorizedJson<CartResponse>('/api/cart')
}

export async function addCartItem(productId: number, quantity: number): Promise<CartResponse> {
  return authorizedJson<CartResponse>('/api/cart/items', {
    method: 'POST',
    body: JSON.stringify({ product_id: productId, quantity }),
  })
}

export async function updateCartItem(itemId: string, quantity: number): Promise<CartResponse> {
  return authorizedJson<CartResponse>(`/api/cart/items/${encodeURIComponent(itemId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ quantity }),
  })
}

export async function removeCartItem(itemId: string): Promise<void> {
  return authorizedJson<void>(`/api/cart/items/${encodeURIComponent(itemId)}`, { method: 'DELETE' })
}

export async function checkout(payload: unknown): Promise<DetailResponse<OrderSummary>> {
  return authorizedJson<DetailResponse<OrderSummary>>('/api/checkout', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchAccountOrders(): Promise<DetailResponse<OrderSummary[]>> {
  return authorizedJson<DetailResponse<OrderSummary[]>>('/api/account/orders')
}

// ── Admin generic resources ───────────────────────────────────────────────────

export type AdminListResource = 'orders' | 'users' | 'roles' | 'permissions' | 'translations'
export type AdminCatalogResource = 'products' | 'categories' | 'vendors'

export interface AdminListParams {
  limit?: number
  offset?: number
  search?: string
  trashed?: 'without' | 'only' | 'with'
}

export async function listAdminRows(
  token: string,
  resource: AdminListResource,
  params?: AdminListParams,
): Promise<{ data: unknown[]; total: number }> {
  // URL template: `/api/admin/${resource}?${params}`
  const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : ''
  return json<{ data: unknown[]; total: number }>(`/api/admin/${resource}${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function listAdminCatalog(
  token: string,
  resource: AdminCatalogResource,
  params?: AdminListParams,
): Promise<{ data: unknown[]; total: number }> {
  const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : ''
  return json<{ data: unknown[]; total: number }>(`/api/admin/${resource}${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function createAdminCatalog(
  token: string,
  resource: AdminCatalogResource,
  payload: unknown,
): Promise<{ data: unknown }> {
  return json<{ data: unknown }>(`/api/admin/${resource}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  })
}

export async function updateAdminCatalog(
  token: string,
  resource: AdminCatalogResource,
  id: string | number,
  payload: unknown,
): Promise<{ data: unknown }> {
  return json<{ data: unknown }>(`/api/admin/${resource}/${encodeURIComponent(String(id))}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  })
}

export async function deleteAdminCatalog(
  token: string,
  resource: AdminCatalogResource,
  id: string | number,
): Promise<void> {
  return json<void>(`/api/admin/${resource}/${encodeURIComponent(String(id))}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function forceDeleteAdminCatalog(
  token: string,
  resource: AdminCatalogResource,
  id: string | number,
): Promise<void> {
  return json<void>(`/api/admin/${resource}/${encodeURIComponent(id)}/force`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function getAdminCatalogRecord(
  token: string,
  resource: AdminCatalogResource,
  id: string | number,
): Promise<{ data: unknown }> {
  return json<{ data: unknown }>(`/api/admin/${resource}/${encodeURIComponent(String(id))}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

// ── Admin orders ──────────────────────────────────────────────────────────────

export async function getAdminOrder(token: string, orderId: string): Promise<{ data: unknown }> {
  return json<{ data: unknown }>(`/api/admin/orders/${encodeURIComponent(orderId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function updateAdminOrderStatus(
  token: string,
  orderId: string,
  status: string,
): Promise<unknown> {
  return json<unknown>(`/api/admin/orders/${encodeURIComponent(orderId)}/status`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ status }),
  })
}

// ── Product media ─────────────────────────────────────────────────────────────

export interface MediaItem {
  id: string
  url: string
  srcset?: string
}

export async function listProductMedia(
  token: string,
  productId: string | number,
): Promise<{ data: MediaItem[] }> {
  return json<{ data: MediaItem[] }>(`/api/admin/products/${encodeURIComponent(productId)}/media`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function uploadProductMedia(
  token: string,
  productId: string | number,
  file: File,
): Promise<{ data: MediaItem }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`/api/admin/products/${encodeURIComponent(productId)}/media`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!res.ok) throw new ApiError('Upload failed', res.status)
  return res.json() as Promise<{ data: MediaItem }>
}

export async function deleteProductMedia(
  token: string,
  productId: string | number,
  mediaId: string,
): Promise<void> {
  const base = encodeURIComponent(String(productId))
  return json<void>(`/api/admin/products/${base}/media/${encodeURIComponent(mediaId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
}
