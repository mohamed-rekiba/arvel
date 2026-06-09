import { describe, expect, it } from 'vitest'
import { safeInternalPath } from './navigation'

describe('safeInternalPath', () => {
  it('keeps a rooted internal path', () => {
    expect(safeInternalPath('/account/orders')).toBe('/account/orders')
    expect(safeInternalPath('/cart?step=2')).toBe('/cart?step=2')
  })

  it('rejects protocol-relative URLs', () => {
    expect(safeInternalPath('//evil.test/phish')).toBe('/')
    expect(safeInternalPath('/\\evil.test')).toBe('/')
  })

  it('rejects absolute and scheme URLs', () => {
    expect(safeInternalPath('https://evil.test')).toBe('/')
    expect(safeInternalPath('javascript:alert(1)')).toBe('/')
  })

  it('rejects backslash tricks', () => {
    expect(safeInternalPath('/foo\\bar')).toBe('/')
  })

  it('falls back when empty or missing', () => {
    expect(safeInternalPath('')).toBe('/')
    expect(safeInternalPath(null)).toBe('/')
    expect(safeInternalPath(undefined)).toBe('/')
  })

  it('honors a custom fallback', () => {
    expect(safeInternalPath(null, '/admin/dashboard')).toBe('/admin/dashboard')
  })
})
