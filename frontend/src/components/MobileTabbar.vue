<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User, Plus, History as HistoryIcon, Compass, Bookmark } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const navItems = [
  { key: 'Gallery', labelKey: 'menu.gallery', icon: Compass },
  { key: 'MyFavorites', labelKey: 'menu.my_favorites', icon: Bookmark },
  { key: 'CustomFeatures', labelKey: 'menu.custom_features', icon: Plus },
  { key: 'History', labelKey: 'menu.history', icon: HistoryIcon },
  { key: 'Profile', labelKey: 'menu.profile', icon: User },
]

const currentRouteName = computed(() => route.name as string)

const handleNavigation = (key: string) => {
  router.push({ name: key })
}
</script>

<template>
  <div class="fixed bottom-0 left-0 right-0 z-50 bg-[#0b0e14]/90 backdrop-blur-lg border-t border-slate-400/50 pb-safe">
    <div class="flex items-center justify-around h-16 px-2">
      <button 
        v-for="item in navItems" 
        :key="item.key"
        @click="handleNavigation(item.key)"
        class="flex flex-col items-center justify-center w-full h-full transition-colors relative"
        :class="[
          item.key === 'CustomFeatures' ? 'z-10' : '',
          currentRouteName === item.key && item.key !== 'CustomFeatures' ? 'text-cyan-400' : 'text-slate-500 hover:text-slate-300'
        ]"
      >
        <template v-if="item.key === 'CustomFeatures'">
          <!-- 悬浮凸起的加号按钮 (FAB) -->
          <div 
            class="absolute -translate-y-4 w-14 h-14 rounded-full flex items-center justify-center bg-gradient-to-r from-indigo-500 to-cyan-500 shadow-lg shadow-cyan-500/30 border-4 border-[#0b0e14]"
            :class="currentRouteName === item.key ? 'scale-110 shadow-cyan-500/50 transition-all' : 'transition-all hover:scale-105'"
          >
            <component :is="item.icon" :size="28" :stroke-width="2.5" class="text-white" />
          </div>
        </template>
        <template v-else>
          <!-- 激活状态的顶部指示条 -->
          <div 
            v-if="currentRouteName === item.key" 
            class="absolute top-0 w-8 h-0.5 bg-cyan-400 rounded-b-full shadow-[0_2px_8px_rgba(34,211,238,0.6)]"
          ></div>
          
          <component :is="item.icon" :size="22" :stroke-width="currentRouteName === item.key ? 2.5 : 2" class="mb-1" />
          <span class="text-[10px] font-medium tracking-wide">{{ t(item.labelKey) }}</span>
        </template>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* 适配 iOS 底部安全区 */
.pb-safe {
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
</style>
