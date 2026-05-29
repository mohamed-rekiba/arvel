<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type { LocalizedText } from '@/types'

const props = defineProps<{
  modelValue: LocalizedText
  label: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: LocalizedText]
}>()

const tabs = ['en', 'ar', 'tr'] as const
const selected = ref<(typeof tabs)[number]>('en')

// Local copy so rapid updates don't race against stale prop values.
const local = reactive<LocalizedText>({ ...props.modelValue })

watch(
  () => props.modelValue,
  (v) => Object.assign(local, v),
  { deep: true },
)

function updateField(tab: string, value: string): void {
  local[tab as keyof LocalizedText] = value as LocalizedText[keyof LocalizedText]
  emit('update:modelValue', { ...local })
}
</script>

<template>
  <div class="space-y-2">
    <label class="text-sm font-medium text-fg">{{ label }}</label>
    <div class="flex gap-1 rounded-lg bg-app-bg-sunken p-1">
      <button
        v-for="tab in tabs"
        :key="tab"
        type="button"
        class="rounded-md px-3 py-1 text-xs font-medium uppercase transition"
        :class="
          selected === tab ? 'bg-admin-surface text-brand shadow-sm' : 'text-fg-muted hover:text-fg'
        "
        @click="selected = tab"
      >
        {{ tab }}
      </button>
    </div>
    <input
      v-for="tab in tabs"
      v-show="selected === tab"
      :key="tab"
      :value="local[tab] ?? ''"
      type="text"
      :dir="tab === 'ar' ? 'rtl' : 'ltr'"
      class="w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand-soft"
      @input="updateField(tab, ($event.target as HTMLInputElement).value)"
    />
  </div>
</template>
