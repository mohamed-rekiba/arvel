<script setup lang="ts">
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()

const kindClasses: Record<string, string> = {
  success: 'bg-status-delivered-bg text-status-delivered-fg border-success/30',
  error: 'bg-danger/10 text-danger border-danger/30',
  warning: 'bg-warning/10 text-warning border-warning/30',
  info: 'bg-info/10 text-info border-info/30',
}

const kindIcons: Record<string, string> = {
  success: '✓',
  error: '✕',
  warning: '!',
  info: 'i',
}
</script>

<template>
  <Teleport to="body">
    <div
      aria-live="polite"
      aria-atomic="false"
      class="pointer-events-none fixed bottom-6 end-6 z-[9999] flex flex-col gap-3"
    >
      <TransitionGroup name="toast">
        <div
          v-for="t in toast.toasts"
          :key="t.id"
          class="pointer-events-auto flex min-w-72 max-w-sm items-start gap-3 rounded-xl border px-4 py-3 shadow-lg"
          :class="kindClasses[t.kind]"
          role="alert"
        >
          <span
            class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-bold"
            :class="{
              'bg-success/20': t.kind === 'success',
              'bg-danger/20': t.kind === 'error',
              'bg-warning/20': t.kind === 'warning',
              'bg-info/20': t.kind === 'info',
            }"
          >
            {{ kindIcons[t.kind] }}
          </span>
          <p class="flex-1 text-sm leading-snug">{{ t.message }}</p>
          <button
            type="button"
            class="shrink-0 opacity-50 transition hover:opacity-100"
            aria-label="Dismiss"
            @click="toast.dismiss(t.id)"
          >
            ×
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.toast-leave-to {
  opacity: 0;
  /* slides toward the anchor edge in both LTR and RTL */
  translate: 12px 0;
}

:dir(rtl) .toast-leave-to {
  translate: -12px 0;
}
</style>
