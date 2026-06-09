<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AdminSidebar from '@/components/admin/AdminSidebar.vue'
import { clearSession } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

onMounted(async () => {
  if (!auth.user) {
    await auth.hydrate()
  }
})

function handleLogout(): void {
  clearSession()
  auth.logout()
}

// Collapse automatically when the viewport is too narrow to fit the full sidebar comfortably.
// 1280px = xl breakpoint — at that width the sidebar + content both have breathing room.
const COLLAPSE_BELOW = 1280
const collapsed = ref(window.innerWidth < COLLAPSE_BELOW)

function onResize() {
  if (window.innerWidth < COLLAPSE_BELOW && !collapsed.value) {
    collapsed.value = true
  } else if (window.innerWidth > COLLAPSE_BELOW && collapsed.value) {
    collapsed.value = false
  }
}

onMounted(() => window.addEventListener('resize', onResize, { passive: true }))
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<template>
  <div class="flex min-h-screen bg-admin-canvas">
    <AdminSidebar :collapsed="collapsed" @toggle="collapsed = !collapsed" @logout="handleLogout" />
    <div class="flex min-h-screen flex-1 flex-col">
      <main class="flex-1 p-6 lg:p-8">
        <!-- key forces a fresh mount on every path change so onMounted always
             fetches the correct data, even when the same component handles
             multiple routes (AdminCatalogPage, AdminListPage, detail pages). -->
        <RouterView :key="route.path" />
      </main>
    </div>
  </div>
</template>
