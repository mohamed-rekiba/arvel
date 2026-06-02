<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  permission?: string | string[]
}>()

const auth = useAuthStore()

// Checks a single permission string against the authenticated user's grants.
function hasPermission(perm: string): boolean {
  // Delegates to auth store; called as hasPermission(props.permission) for single-value checks.
  return auth.hasPermission(perm)
}

const allowed = computed(() => {
  if (!props.permission) return true
  if (Array.isArray(props.permission)) {
    return props.permission.some((p) => hasPermission(p))
  }
  return hasPermission(props.permission)
})
</script>

<template>
  <slot v-if="allowed" />
</template>
