<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { routeQuery } from '@/lib/i18n'

const props = withDefaults(
  defineProps<{
    adminRedirect?: boolean
    defaultTab?: 'login' | 'register'
  }>(),
  { adminRedirect: false, defaultTab: 'login' },
)

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n({ useScope: 'global' })

// Admin login never shows the register tab — admins are provisioned, not self-registered.
const wantsRegister = props.defaultTab === 'register' || route.query.tab === 'register'
const activeTab = ref<'login' | 'register'>(
  !props.adminRedirect && wantsRegister ? 'register' : 'login',
)

const loginForm = ref({ email: '', password: '' })
const registerForm = ref({ name: '', email: '', password: '' })
const localError = ref<string | null>(null)
const notice = ref<string | null>(null)

const redirectPath = computed(() => {
  if (props.adminRedirect) return '/admin/dashboard'
  return routeQuery(route.query.redirect) || '/'
})

async function handleLogin(): Promise<void> {
  localError.value = null
  try {
    await auth.login(loginForm.value.email, loginForm.value.password)
    await router.push(redirectPath.value)
  } catch {
    localError.value = auth.error
  }
}

async function handleRegister(): Promise<void> {
  localError.value = null
  notice.value = null
  try {
    await auth.register(
      registerForm.value.name,
      registerForm.value.email,
      registerForm.value.password,
    )
    // Login needs a verified email, so send them to the login tab with a prompt
    // to verify rather than failing an immediate auto-login.
    loginForm.value.email = registerForm.value.email
    registerForm.value = { name: '', email: '', password: '' }
    activeTab.value = 'login'
    notice.value = t('auth.verify_sent')
  } catch {
    localError.value = auth.error
  }
}
</script>

<template>
  <div class="mx-auto flex min-h-[60vh] max-w-md flex-col justify-center px-4 py-16">
    <h1 class="text-center text-3xl font-bold text-fg">
      {{ props.adminRedirect ? t('auth.admin_sign_in') : t('auth.welcome') }}
    </h1>

    <div v-if="!props.adminRedirect" class="mt-8 flex rounded-lg bg-app-bg-sunken p-1">
      <button
        type="button"
        class="flex-1 rounded-md py-2 text-sm font-medium transition"
        :class="activeTab === 'login' ? 'bg-app-bg text-brand shadow-sm' : 'text-fg-muted'"
        @click="activeTab = 'login'"
      >
        {{ t('auth.login') }}
      </button>
      <button
        type="button"
        class="flex-1 rounded-md py-2 text-sm font-medium transition"
        :class="activeTab === 'register' ? 'bg-app-bg text-brand shadow-sm' : 'text-fg-muted'"
        @click="activeTab = 'register'"
      >
        {{ t('auth.register') }}
      </button>
    </div>

    <form v-if="activeTab === 'login'" class="mt-6 space-y-4" @submit.prevent="handleLogin">
      <p
        v-if="notice"
        class="rounded-lg bg-stock-in/10 px-4 py-3 text-sm text-stock-in"
        role="status"
      >
        {{ notice }}
      </p>
      <input
        v-model="loginForm.email"
        type="email"
        required
        :placeholder="t('auth.email')"
        class="w-full rounded-lg border border-border px-4 py-3 text-sm outline-none focus:border-brand"
      />
      <input
        v-model="loginForm.password"
        type="password"
        required
        :placeholder="t('auth.password')"
        class="w-full rounded-lg border border-border px-4 py-3 text-sm outline-none focus:border-brand"
      />
      <p v-if="localError" class="text-sm text-red-600">{{ localError }}</p>
      <button
        type="submit"
        class="w-full rounded-xl bg-brand py-3 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-50"
        :disabled="auth.loading"
      >
        {{ auth.loading ? t('auth.signing_in') : t('auth.login') }}
      </button>
    </form>

    <form v-else class="mt-6 space-y-4" @submit.prevent="handleRegister">
      <input
        v-model="registerForm.name"
        type="text"
        required
        :placeholder="t('auth.full_name')"
        class="w-full rounded-lg border border-border px-4 py-3 text-sm outline-none focus:border-brand"
      />
      <input
        v-model="registerForm.email"
        type="email"
        required
        :placeholder="t('auth.email')"
        class="w-full rounded-lg border border-border px-4 py-3 text-sm outline-none focus:border-brand"
      />
      <input
        v-model="registerForm.password"
        type="password"
        required
        minlength="8"
        :placeholder="t('auth.password')"
        class="w-full rounded-lg border border-border px-4 py-3 text-sm outline-none focus:border-brand"
      />
      <p v-if="localError" class="text-sm text-red-600">{{ localError }}</p>
      <button
        type="submit"
        class="w-full rounded-xl bg-brand py-3 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-50"
        :disabled="auth.loading"
      >
        {{ auth.loading ? t('auth.creating_account') : t('auth.register') }}
      </button>
    </form>
  </div>
</template>
