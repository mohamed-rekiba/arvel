import type { Directive, DirectiveBinding } from 'vue'

// Fades + lifts an element into view the first time it scrolls into the viewport.
// Usage: v-reveal  |  v-reveal="120" (delay ms, for stagger)  |  v-reveal="{ delay: 120 }"
// Goes inert under prefers-reduced-motion — the element just shows immediately.

interface RevealOptions {
  delay?: number
}

const REVEALED_CLASS = 'is-revealed'

function resolveDelay(value: number | RevealOptions | undefined): number {
  if (typeof value === 'number') return value
  return value?.delay ?? 0
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

const observers = new WeakMap<HTMLElement, IntersectionObserver>()

export const vReveal: Directive<HTMLElement, number | RevealOptions | undefined> = {
  mounted(el: HTMLElement, binding: DirectiveBinding<number | RevealOptions | undefined>) {
    el.classList.add('reveal')

    if (prefersReducedMotion()) {
      el.classList.add(REVEALED_CLASS)
      return
    }

    const delay = resolveDelay(binding.value)
    if (delay > 0) el.style.transitionDelay = `${delay}ms`

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          el.classList.add(REVEALED_CLASS)
          observer.disconnect()
          observers.delete(el)
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    )

    observer.observe(el)
    observers.set(el, observer)
  },

  unmounted(el: HTMLElement) {
    observers.get(el)?.disconnect()
    observers.delete(el)
  },
}
