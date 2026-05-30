<script setup lang="ts">
defineProps<{
  rating: number
  count?: number
}>()

function starFill(index: number, rating: number): string {
  if (rating >= index) return 'text-rating-star'
  if (rating >= index - 0.5) return 'text-rating-star/60'
  return 'text-rating-empty'
}
</script>

<template>
  <div class="flex items-center gap-1">
    <span v-for="i in 5" :key="i" class="text-sm" :class="starFill(i, rating)"> ★ </span>
    <span v-if="count !== undefined" class="ms-1 text-xs text-fg-muted">({{ count }})</span>
  </div>
</template>
