<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardRevenuePointOut } from '@/api/schemas'
import type { SupportedLocale } from '@/types'
import { formatCurrency } from '@/lib/i18n'

const { t } = useI18n({ useScope: 'global' })

// Server-computed last-7-days series — exact, not capped by the loaded page.
const props = defineProps<{
  series: DashboardRevenuePointOut[]
  locale: SupportedLocale
}>()

// SVG constants
const W = 560
const CHART_H = 96 // bar area height
const LABEL_H = 24 // day label row
const H = CHART_H + LABEL_H
const SLOT_W = W / 7
const BAR_W = Math.round(SLOT_W * 0.52)
const BAR_OFFSET = Math.round((SLOT_W - BAR_W) / 2)
const MAX_BAR_H = CHART_H - 8 // 8px headroom above tallest bar

// Dates come back as YYYY-MM-DD; parse to local midnight for labels.
const days = computed<Date[]>(() =>
  props.series.map((p) => {
    const [y, m, d] = p.date.split('-').map(Number)
    return new Date(y, m - 1, d)
  }),
)

const revenuePerDay = computed<number[]>(() => props.series.map((p) => p.revenue))

const totalPeriod = computed(() => revenuePerDay.value.reduce((a, b) => a + b, 0))
const maxRevenue = computed(() => Math.max(...revenuePerDay.value, 1))
const hasData = computed(() => totalPeriod.value > 0)

function barX(i: number): number {
  return i * SLOT_W + BAR_OFFSET
}

function barH(revenue: number): number {
  return Math.round((revenue / maxRevenue.value) * MAX_BAR_H)
}

function barY(revenue: number): number {
  return CHART_H - barH(revenue)
}

function labelX(i: number): number {
  return i * SLOT_W + SLOT_W / 2
}

function dayLabel(d: Date): string {
  return d.toLocaleDateString(props.locale, { weekday: 'short' })
}

function isToday(d: Date): boolean {
  return d.toDateString() === new Date().toDateString()
}

function tooltipLabel(i: number): string {
  return `${days.value[i].toLocaleDateString(props.locale, { month: 'short', day: 'numeric' })}: ${formatCurrency(revenuePerDay.value[i], props.locale)}`
}
</script>

<template>
  <div
    class="flex flex-col rounded-xl border border-[#eee] bg-admin-surface shadow-sm dark:border-border-subtle"
  >
    <!-- header -->
    <div class="flex items-center justify-between border-b border-border-subtle px-6 py-4">
      <div>
        <h2 class="font-semibold text-fg">{{ t('admin.chart.revenue_7d') }}</h2>
        <p class="mt-0.5 text-xs text-fg-faint">{{ t('admin.chart.last_7_days') }}</p>
      </div>
      <p class="text-xl font-bold tabular-nums text-fg">
        {{ formatCurrency(totalPeriod, locale) }}
      </p>
    </div>

    <!-- chart -->
    <div class="px-4 pb-2 pt-4">
      <svg
        :viewBox="`0 0 ${W} ${H}`"
        :width="W"
        :height="H"
        class="w-full overflow-visible"
        aria-hidden="true"
      >
        <!-- horizontal grid lines (4 levels) -->
        <line
          v-for="n in 4"
          :key="n"
          x1="0"
          :x2="W"
          :y1="CHART_H - Math.round((MAX_BAR_H / 4) * n)"
          :y2="CHART_H - Math.round((MAX_BAR_H / 4) * n)"
          stroke="var(--color-border-subtle)"
          stroke-width="1"
        />

        <!-- bars -->
        <g v-for="(revenue, i) in revenuePerDay" :key="i">
          <title>{{ tooltipLabel(i) }}</title>

          <!-- track (full-height ghost bar) -->
          <rect
            :x="barX(i)"
            y="0"
            :width="BAR_W"
            :height="CHART_H"
            fill="var(--color-app-bg-sunken)"
            rx="5"
          />

          <!-- filled bar (skip when revenue is 0) -->
          <rect
            v-if="revenue > 0"
            :x="barX(i)"
            :y="barY(revenue)"
            :width="BAR_W"
            :height="barH(revenue)"
            :fill="isToday(days[i]) ? 'var(--color-brand)' : 'var(--color-primary-300)'"
            rx="5"
          />

          <!-- day label -->
          <text
            :x="labelX(i)"
            :y="H - 4"
            text-anchor="middle"
            font-size="10"
            :fill="isToday(days[i]) ? 'var(--color-brand)' : 'var(--color-fg-faint)'"
            :font-weight="isToday(days[i]) ? '700' : '400'"
          >
            {{ dayLabel(days[i]) }}
          </text>
        </g>
      </svg>

      <!-- empty state -->
      <p v-if="!hasData" class="py-6 text-center text-sm text-fg-faint">
        {{ t('admin.chart.no_data') }}
      </p>
    </div>
  </div>
</template>
