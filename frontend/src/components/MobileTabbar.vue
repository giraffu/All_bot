<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User, Wand2, History as HistoryIcon, Compass, Bookmark, Star } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()

const navItems = [
  { key: 'Gallery', label: '市集', icon: Compass },
  { key: 'CustomFeatures', label: '练功房', icon: Wand2 },
  { key: 'History', label: '闪回瓶', icon: HistoryIcon },
  { key: 'Profile', label: '我的', icon: User },
]

const currentRouteName = computed(() => route.name as string)

const handleNavigation = (key: string) => {
  router.push({ name: key })
}
</script>

<template>
  <div class="fixed bottom-0 left-0 right-0 z-50 bg-[#0b0e14]/90 backdrop-blur-lg border-t border-slate-700/50 pb-safe">
    <div class="flex items-center justify-around h-16 px-2">
      <button 
        v-for="item in navItems" 
        :key="item.key"
        @click="handleNavigation(item.key)"
        class="flex flex-col items-center justify-center w-full h-full space-y-1 transition-colors relative"
        :class="currentRouteName === item.key ? 'text-cyan-400' : 'text-slate-500 hover:text-slate-300'"
      >
        <!-- 激活状态的顶部指示条 -->
        <div 
          v-if="currentRouteName === item.key" 
          class="absolute top-0 w-8 h-0.5 bg-cyan-400 rounded-b-full shadow-[0_2px_8px_rgba(34,211,238,0.6)]"
        ></div>
        
        <component :is="item.icon" :size="22" :stroke-width="currentRouteName === item.key ? 2.5 : 2" />
        <span class="text-[10px] font-medium tracking-wide">{{ item.label }}</span>
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
