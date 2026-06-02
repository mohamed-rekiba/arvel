import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastKind = 'success' | 'error' | 'info' | 'warning'

export interface Toast {
  id: number
  kind: ToastKind
  message: string
}

let _seq = 0

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([])

  function show(kind: ToastKind, message: string, durationMs = 4000): void {
    const id = ++_seq
    toasts.value.push({ id, kind, message })
    setTimeout(() => dismiss(id), durationMs)
  }

  function dismiss(id: number): void {
    const idx = toasts.value.findIndex((t) => t.id === id)
    if (idx !== -1) toasts.value.splice(idx, 1)
  }

  const success = (msg: string) => show('success', msg)
  const error = (msg: string) => show('error', msg)
  const info = (msg: string) => show('info', msg)
  const warning = (msg: string) => show('warning', msg)

  return { toasts, show, dismiss, success, error, info, warning }
})
