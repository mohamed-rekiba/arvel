import type { LocalizedText, SupportedLocale } from '@/types'

export function toSupportedLocale(locale: string): SupportedLocale {
  if (locale === 'ar' || locale === 'tr') return locale
  return 'en'
}

const RTL_LOCALES = new Set<SupportedLocale>(['ar'])

export function isRtlLocale(locale: SupportedLocale): boolean {
  return RTL_LOCALES.has(locale)
}

export function applyDocumentLocale(locale: SupportedLocale): void {
  document.documentElement.lang = locale
  document.documentElement.dir = isRtlLocale(locale) ? 'rtl' : 'ltr'
}

// Vue Router types route params as string | string[]. In this app every param
// is a single path segment, so we always get a plain string, but we handle
// the array case defensively.
export function routeParam(param: string | string[]): string {
  return Array.isArray(param) ? (param[0] ?? '') : param
}

// Vue Router types query values as string | null | (string | null)[].
// Returns the first non-null string value, or '' when nothing is present.
export function routeQuery(param: string | null | (string | null)[]): string {
  if (Array.isArray(param)) {
    const first = param.find((v) => v !== null)
    return first ?? ''
  }
  return param ?? ''
}

const I18N_CACHE_PREFIX = 'i18n_cache_'
const LOCALE_KEY = 'locale'

export const SUPPORTED_LOCALES: SupportedLocale[] = ['en', 'ar', 'tr']

export function getStoredLocale(): SupportedLocale {
  const stored = localStorage.getItem(LOCALE_KEY)
  if (stored === 'en' || stored === 'ar' || stored === 'tr') {
    return stored
  }
  return 'en'
}

export function setStoredLocale(locale: SupportedLocale): void {
  localStorage.setItem(LOCALE_KEY, locale)
}

export function getCachedTranslations(locale: SupportedLocale): Record<string, string> | null {
  const raw = localStorage.getItem(`${I18N_CACHE_PREFIX}${locale}`)
  if (!raw) return null
  try {
    return JSON.parse(raw) as Record<string, string>
  } catch {
    return null
  }
}

export function cacheTranslations(locale: SupportedLocale, messages: Record<string, string>): void {
  localStorage.setItem(`${I18N_CACHE_PREFIX}${locale}`, JSON.stringify(messages))
}

export function pickLocalized(text: LocalizedText, locale: SupportedLocale): string {
  return text[locale] ?? text.en ?? Object.values(text)[0] ?? ''
}

export function formatCurrency(amount: number, locale: SupportedLocale): string {
  const currencyMap: Record<SupportedLocale, string> = {
    en: 'USD',
    ar: 'SAR',
    tr: 'TRY',
  }
  return new Intl.NumberFormat(locale === 'ar' ? 'ar-SA' : locale === 'tr' ? 'tr-TR' : 'en-US', {
    style: 'currency',
    currency: currencyMap[locale],
  }).format(amount)
}

export function formatDate(date: string, locale: SupportedLocale): string {
  return new Intl.DateTimeFormat(locale === 'ar' ? 'ar-SA' : locale === 'tr' ? 'tr-TR' : 'en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(date))
}
