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

// ── Admin list resources ──────────────────────────────────────────────────────

export type AdminListResource = 'orders' | 'users' | 'roles' | 'permissions' | 'translations'

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
