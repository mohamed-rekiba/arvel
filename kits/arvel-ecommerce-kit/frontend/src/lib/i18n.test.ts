import { describe, expect, it } from 'vitest'
import {
  formatCurrency,
  isRtlLocale,
  pickLocalized,
  routeParam,
  routeQuery,
  toSupportedLocale,
} from '@/lib/i18n'

describe('toSupportedLocale', () => {
  it('passes through supported locales', () => {
    expect(toSupportedLocale('ar')).toBe('ar')
    expect(toSupportedLocale('tr')).toBe('tr')
    expect(toSupportedLocale('en')).toBe('en')
  })

  it('falls back to en for anything else', () => {
    expect(toSupportedLocale('fr')).toBe('en')
    expect(toSupportedLocale('')).toBe('en')
  })
})

describe('isRtlLocale', () => {
  it('only treats Arabic as RTL', () => {
    expect(isRtlLocale('ar')).toBe(true)
    expect(isRtlLocale('en')).toBe(false)
    expect(isRtlLocale('tr')).toBe(false)
  })
})

describe('routeParam', () => {
  it('returns a plain string unchanged', () => {
    expect(routeParam('shoes')).toBe('shoes')
  })

  it('takes the first element of an array, empty when missing', () => {
    expect(routeParam(['shoes', 'bags'])).toBe('shoes')
    expect(routeParam([])).toBe('')
  })
})

describe('routeQuery', () => {
  it('returns the value or empty for null', () => {
    expect(routeQuery('q')).toBe('q')
    expect(routeQuery(null)).toBe('')
  })

  it('returns the first non-null array value', () => {
    expect(routeQuery([null, 'b'])).toBe('b')
    expect(routeQuery([null, null])).toBe('')
  })
})

describe('pickLocalized', () => {
  it('prefers the requested locale', () => {
    expect(pickLocalized({ en: 'Hello', ar: 'مرحبا' }, 'ar')).toBe('مرحبا')
  })

  it('falls back to en, then any value', () => {
    expect(pickLocalized({ en: 'Hello' }, 'tr')).toBe('Hello')
    expect(pickLocalized({ tr: 'Merhaba' }, 'ar')).toBe('Merhaba')
    expect(pickLocalized({}, 'en')).toBe('')
  })
})

describe('formatCurrency', () => {
  it('uses USD for en', () => {
    const out = formatCurrency(19.99, 'en')
    expect(out).toContain('19.99')
    expect(out).toContain('$')
  })

  it('switches currency per locale', () => {
    // Different locales must not produce identical strings for the same amount.
    expect(formatCurrency(10, 'en')).not.toBe(formatCurrency(10, 'tr'))
  })
})
