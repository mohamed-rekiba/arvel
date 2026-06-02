<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'light' | 'dark' | 'mark-only'
    height?: number
  }>(),
  { variant: 'dark', height: 50 },
)
</script>

<template>
  <!-- mark-only: just the A monogram, no wordmark text -->
  <svg
    v-if="variant === 'mark-only'"
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 32 32"
    role="img"
    aria-label="Arvel"
    direction="ltr"
    :height="height"
    :width="height"
  >
    <title>Arvel</title>
    <path fill="#A78BFA" d="M13.58 23.64 L13.58 2.62 L3.07 23.64 Z" />
    <path fill="#22D3EE" d="M13.58 2.62 L21.84 2.62 L28.92 29.37 L19.20 24.25 Z" />
    <rect x="4" y="15" width="23" height="2" rx="0.5" fill="#A78BFA" />
  </svg>

  <!-- dark variant: logo on dark backgrounds -->
  <svg
    v-else-if="variant === 'dark'"
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 100 35"
    role="img"
    aria-label="Arvel"
    direction="ltr"
    :height="height"
    :width="(100 / 35) * height"
  >
    <title>Arvel</title>
    <g transform="translate(2 2)">
      <path fill="#A78BFA" d="M13.58 23.64 L13.58 2.62 L3.07 23.64 Z" />
      <path fill="#22D3EE" d="M13.58 2.62 L21.84 2.62 L28.92 29.37 L19.20 24.25 Z" />
      <rect x="4" y="15" width="23" height="2" rx="0.5" fill="#A78BFA" />
    </g>
    <text
      x="42"
      y="25"
      font-family="Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
      font-size="22"
      font-weight="700"
      letter-spacing="-0.6"
      fill="#F4F4F8"
      direction="ltr"
      unicode-bidi="bidi-override"
    >
      arvel
    </text>
  </svg>

  <!-- light variant: logo on light backgrounds -->
  <svg
    v-else
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 100 35"
    role="img"
    aria-label="Arvel"
    direction="ltr"
    :height="height"
    :width="(100 / 35) * height"
  >
    <title>Arvel</title>
    <g transform="translate(2 2)">
      <path fill="#6D28D9" d="M13.58 23.64 L13.58 2.62 L3.07 23.64 Z" />
      <path fill="#06B6D4" d="M13.58 2.62 L21.84 2.62 L28.92 29.37 L19.20 24.25 Z" />
      <rect x="4" y="15" width="23" height="2" rx="0.5" fill="#6D28D9" />
    </g>
    <text
      x="42"
      y="25"
      font-family="Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
      font-size="22"
      font-weight="700"
      letter-spacing="-0.6"
      fill="#0B0B12"
      direction="ltr"
      unicode-bidi="bidi-override"
    >
      arvel
    </text>
  </svg>
</template>
