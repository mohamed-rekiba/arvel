<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  permission?: string | string[]
}>()

const auth = useAuthStore()

const allowed = computed(() => {
  if (!props.permission) return true
  const list = Array.isArray(props.permission) ? props.permission : [props.permission]
  return list.some((p) => auth.hasPermission(p))
})
</script>

<template>
  <slot v-if="allowed" />
</template>
