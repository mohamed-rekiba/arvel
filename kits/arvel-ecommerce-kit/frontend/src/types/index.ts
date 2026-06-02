export type LocalizedText = Record<string, string>

export type OrderStatus =
  | 'pending'
  | 'confirmed'
  | 'processing'
  | 'shipped'
  | 'delivered'
  | 'cancelled'

export type RealStatus =
  | 'visible'
  | 'draft'
  | 'not_scheduled'
  | 'scheduled'
  | 'category_deleted'
  | 'category_hidden'
  | 'vendor_deleted'
  | 'vendor_hidden'

export type SupportedLocale = 'en' | 'ar' | 'tr'

export const ADMIN_PERMISSIONS = [
  'products.view',
  'orders.view',
  'users.manage',
  'roles.manage',
] as const

export type AdminPermissionName = (typeof ADMIN_PERMISSIONS)[number]

// Shipping address as returned by the backend. The generated schema types
// shipping_address as { [key: string]: unknown } so we narrow it here.
export interface ShippingAddress {
  name?: string
  street?: string
  city?: string
  country?: string
}

const ORDER_STATUSES: readonly string[] = [
  'pending',
  'confirmed',
  'processing',
  'shipped',
  'delivered',
  'cancelled',
]

export function isOrderStatus(status: string): status is OrderStatus {
  return ORDER_STATUSES.includes(status)
}

export function getShippingField(
  address: Record<string, unknown>,
  key: keyof ShippingAddress,
): string {
  const val = address[key]
  return typeof val === 'string' ? val : ''
}
