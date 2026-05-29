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

// Set once during bootstrap; called whenever any request gets a 401.
let _onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(fn: () => void): void {
  _onUnauthorized = fn
}

function getToken(): string | null {
  return localStorage.getItem('access_token')
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

// Orval custom mutator. Returns the parsed response body for 2xx.
// Throws ApiError for 4xx/5xx so TanStack Query can track error state.
export async function request<T>(config: RequestConfig, _options?: RequestOptions): Promise<T> {
  const { url, method, headers: configHeaders, data, params, signal } = config

  const headers: Record<string, string> = { ...configHeaders }

  const token = getToken()
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
