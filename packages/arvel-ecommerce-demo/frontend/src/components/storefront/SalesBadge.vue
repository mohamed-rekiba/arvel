<!-- generated-from: specs/sales-badge.md -->
<script setup lang="ts">
defineProps<{
  discount: number
}>()
</script>

<template>
  <span class="rounded-full bg-discount-badge px-2 py-0.5 text-xs font-bold text-white">
    -{{ discount }}%
  </span>
</template>
