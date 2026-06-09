<script setup lang="ts">
import { computed } from 'vue'
import { useWishlistStore } from '@/stores/wishlist'

const props = defineProps<{
  productId: string
}>()

const wishlist = useWishlistStore()
const wished = computed(() => wishlist.has(props.productId))

function toggle(): void {
  wishlist.toggle(props.productId)
}
</script>

<template>
  <button
    type="button"
    class="flex h-9 w-9 items-center justify-center rounded-full bg-white/90 shadow-sm transition hover:scale-110"
    :aria-label="wished ? 'Remove from wishlist' : 'Add to wishlist'"
    @click.stop="toggle"
  >
    <!-- FILL axis toggles between outlined (0) and filled (1) heart -->
    <span
      class="material-symbols-outlined select-none text-[20px] leading-none transition"
      :style="{
        fontVariationSettings: wished
          ? `'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24`
          : `'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24`,
        color: wished ? 'var(--color-wishlist)' : 'var(--color-fg-faint)',
      }"
      aria-hidden="true"
      >favorite</span
    >
  </button>
</template>
