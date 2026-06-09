<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { pickLocalized, toSupportedLocale } from '@/lib/i18n'
import type { AdminCategoryOut } from '@/api/schemas'

const props = defineProps<{
  categories: AdminCategoryOut[]
}>()

const { locale } = useI18n({ useScope: 'global' })
const currentLocale = computed(() => toSupportedLocale(locale.value))

const iconMap: Record<string, string> = {
  mobiles: 'phone_iphone',
  phones: 'phone_iphone',
  smartphones: 'phone_iphone',
  laptops: 'laptop_mac',
  speakers: 'speaker',
  'tv-sets': 'tv',
  watches: 'watch',
  headsets: 'headphones',
  electronics: 'devices',
  books: 'menu_book',
  fiction: 'auto_stories',
}

const displayCategories = computed(() =>
  props.categories.slice(0, 10).map((cat) => {
    const slug = pickLocalized(cat.slug, currentLocale.value)
    return {
      ...cat,
      name: pickLocalized(cat.name, currentLocale.value),
      slug,
      icon: iconMap[slug] ?? 'shopping_bag',
    }
  }),
)
</script>

<template>
  <div class="flex gap-4 pb-2 scrollbar-hide sm:gap-6">
    <RouterLink v-for="(category, i) in displayCategories" :key="category.id" v-reveal="i * 50"
      :to="`/products?category=${category.slug}`" class="group flex shrink-0 flex-col items-center gap-2">
      <div
        class="flex h-20 w-20 items-center justify-center rounded-full border-2 border-transparent bg-primary-50 shadow-sm transition duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] group-hover:-translate-y-1 group-hover:border-brand group-hover:bg-primary-100 group-hover:shadow-md">
        <span
          class="material-symbols-outlined select-none text-[32px] leading-none text-primary-600 transition group-hover:text-primary-700"
          aria-hidden="true">{{ category.icon }}</span>
      </div>
      <span class="max-w-[80px] text-center text-xs font-medium text-fg-muted transition group-hover:text-brand">
        {{ category.name }}
      </span>
    </RouterLink>
  </div>
</template>
