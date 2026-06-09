import { createI18n } from 'vue-i18n'

// Shared instance so non-component code (Pinia stores, API handlers) can
// translate too — useI18n() only works inside component setup. main.ts fills in
// the messages per locale once they're loaded.
export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: {},
})

export function translate(key: string): string {
  return i18n.global.t(key)
}
