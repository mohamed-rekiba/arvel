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

const LOCALES = [
  { code: 'en', label: 'English', dir: 'ltr' },
  { code: 'ar', label: 'Arabic', dir: 'rtl' },
  { code: 'tr', label: 'Turkish', dir: 'ltr' },
] as const

type LocaleCode = (typeof LOCALES)[number]['code']
const selected = ref<LocaleCode>('en')

// Local copy so rapid updates don't race against stale prop values.
const local = reactive<LocalizedText>({ ...props.modelValue })

watch(
  () => props.modelValue,
  (v) => Object.assign(local, v),
  { deep: true },
)

function updateTranslation(code: string, value: string): void {
  local[code as keyof LocalizedText] = value as LocalizedText[keyof LocalizedText]
  emit('update:modelValue', { ...local })
}

function updateField(tab: string, value: string): void {
  updateTranslation(tab, value)
}
</script>

<template>
  <div class="space-y-2">
    <label class="text-sm font-medium text-fg">{{ label }}</label>
    <div class="flex gap-1 rounded-lg bg-app-bg-sunken p-1">
      <button
        v-for="locale in LOCALES"
        :key="locale.code"
        type="button"
        class="rounded-md px-3 py-1 text-xs font-medium uppercase transition"
        :class="
          selected === locale.code
            ? 'bg-admin-surface text-brand shadow-sm'
            : 'text-fg-muted hover:text-fg'
        "
        @click="selected = locale.code"
      >
        {{ locale.label }}
      </button>
    </div>
    <input
      v-for="locale in LOCALES"
      v-show="selected === locale.code"
      :key="locale.code"
      :value="local[locale.code] ?? ''"
      type="text"
      :dir="locale.dir"
      class="w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand-soft"
      @input="updateField(locale.code, ($event.target as HTMLInputElement).value)"
    />
  </div>
</template>
