<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n({ useScope: 'global' })

defineProps<{
  label: string
  value: string
  trend?: number
  icon: string
  tone: 'amber' | 'indigo' | 'emerald' | 'violet'
}>()

const iconClasses: Record<string, string> = {
  amber: 'bg-kpi-amber-bg text-kpi-amber-fg',
  indigo: 'bg-kpi-indigo-bg text-kpi-indigo-fg',
  emerald: 'bg-kpi-emerald-bg text-kpi-emerald-fg',
  violet: 'bg-brand-soft text-brand',
}
</script>

<template>
  <div
    class="rounded-xl border border-[#eee] bg-admin-surface p-6 shadow-sm dark:border-border-subtle"
  >
    <div class="flex items-start justify-between">
      <div class="min-w-0 flex-1">
        <p class="text-sm font-medium text-fg-muted">{{ label }}</p>
        <p class="mt-2 text-3xl font-bold tracking-tight text-fg">{{ value }}</p>
      </div>
      <div
        class="ms-4 flex h-12 w-12 shrink-0 items-center justify-center rounded-xl"
        :class="iconClasses[tone]"
      >
        <span
          class="material-symbols-outlined text-2xl leading-none"
          style="font-variation-settings: 'FILL' 1"
          aria-hidden="true"
          >{{ icon }}</span
        >
      </div>
    </div>

    <div v-if="trend !== undefined" class="mt-4 flex items-center gap-2">
      <span
        class="inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold"
        :class="
          trend >= 0
            ? 'bg-kpi-emerald-bg text-kpi-emerald-fg'
            : 'bg-kpi-danger-bg text-kpi-danger-fg'
        "
      >
        <span class="material-symbols-outlined text-[14px] leading-none" aria-hidden="true">
          {{ trend >= 0 ? 'arrow_upward' : 'arrow_downward' }}
        </span>
        {{ trend >= 0 ? '+' : '' }}{{ trend }}%
      </span>
      <span class="text-xs text-fg-faint">{{ t('admin.stat.vs_last_month') }}</span>
    </div>
  </div>
</template>
