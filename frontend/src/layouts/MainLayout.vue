<script setup lang="ts">
import { computed, defineAsyncComponent, ref, onMounted, watch, onBeforeUnmount, provide } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTemplateApplyStore } from '@/stores/templateApply'
import { useViewport } from '@/composables/useViewport'
import { useI18n } from 'vue-i18n'
import {
  mainLayoutContentRefKey
} from '@/composables/useWorkbenchScrollLock'
import { User as UserIcon, Wand2, History as HistoryIcon, LogOut, Wallet, Compass, Bookmark } from 'lucide-vue-next'
import TaskProgress from '@/components/TaskProgress.vue'
import MobileTabbar from '@/components/MobileTabbar.vue'
import TaskDetailModal from '@/components/TaskDetailModal.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const templateApplyStore = useTemplateApplyStore()
const { isMobile } = useViewport()
const { t } = useI18n()
const TemplateApplyWorkbenchHost = defineAsyncComponent(
  () => import('@/components/template-apply/TemplateApplyWorkbenchHost.vue')
)

const collapsed = ref(false)
const selectedKeys = ref<string[]>([route.name as string || 'Profile'])
const canvasRef = ref<HTMLCanvasElement | null>(null)
const layoutContentRef = ref<HTMLElement | { $el?: HTMLElement } | null>(null)
let animationFrameId: number

const contentRef = computed<HTMLElement | null>(() => {
  if (layoutContentRef.value instanceof HTMLElement) {
    return layoutContentRef.value
  }

  return layoutContentRef.value?.$el ?? null
})

const shouldRenderTemplateApplyWorkbench = computed(() =>
  templateApplyStore.visible
  || templateApplyStore.loading
  || templateApplyStore.status === 'opening'
)

provide(mainLayoutContentRefKey, contentRef)

const handleMenuClick = ({ key }: { key: string }) => {
  router.push({ name: key })
}

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}

const pageTitle = computed(() => {
  const titleMap: Record<string, string> = {
    Profile: t('menu.profile'),
    Gallery: t('menu.gallery'),
    CustomFeatures: t('menu.custom_features'),
    History: t('menu.history'),
    MyFavorites: t('menu.my_favorites'),
    Billing: t('menu.recharge'),
  }
  return titleMap[route.name as string] || ''
})

const initParticles = () => {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  let width = window.innerWidth
  let height = window.innerHeight
  canvas.width = width
  canvas.height = height

  // 灵气粒子 (Spiritual energy particles)
  const particles: any[] = []
  const particleCount = window.innerWidth < 768 ? 30 : 60 // Less particles on mobile

  class Particle {
    x: number
    y: number
    radius: number
    vx: number
    vy: number
    color: string
    alpha: number
    pulse: number

    constructor() {
      this.x = Math.random() * width
      this.y = Math.random() * height
      this.radius = Math.random() * 3 + 1
      this.vx = (Math.random() - 0.5) * 0.4
      this.vy = (Math.random() - 0.5) * 0.4 - 0.3 // Drift upwards
      // 靛蓝、青色、银色系 (Indigo, cyan, silver theme)
      const colors = ['#38bdf8', '#818cf8', '#c084fc', '#e2e8f0', '#67e8f9']
      this.color = colors[Math.floor(Math.random() * colors.length)]
      this.alpha = Math.random() * 0.4 + 0.1
      this.pulse = Math.random() * 0.02 + 0.01
    }

    update() {
      this.x += this.vx
      this.y += this.vy
      this.alpha += Math.sin(Date.now() * this.pulse) * 0.005

      // Wrap around edges
      if (this.x < 0) this.x = width
      if (this.x > width) this.x = 0
      if (this.y < 0) this.y = height
      if (this.y > height) this.y = 0
    }

    draw() {
      if (!ctx) return
      ctx.save()
      ctx.globalAlpha = Math.max(0, Math.min(1, this.alpha))
      ctx.beginPath()
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2)
      ctx.fillStyle = this.color
      ctx.shadowColor = this.color
      ctx.shadowBlur = 15
      ctx.fill()
      ctx.restore()
    }
  }

  // 背景星辰 (Background stars)
  const stars: any[] = []
  const starCount = window.innerWidth < 768 ? 50 : 150
  for (let i = 0; i < starCount; i++) {
    stars.push({
      x: Math.random() * width,
      y: Math.random() * height,
      radius: Math.random() * 1.5,
      alpha: Math.random()
    })
  }

  for (let i = 0; i < particleCount; i++) {
    particles.push(new Particle())
  }

  const animate = () => {
    // Fill canvas with solid background color to remove particle trails while maintaining the dark theme
    ctx.fillStyle = '#0b0e14'
    ctx.fillRect(0, 0, width, height)
    
    // Draw stars
    ctx.save()
    stars.forEach(star => {
      star.alpha += (Math.random() - 0.5) * 0.05
      if (star.alpha < 0) star.alpha = 0
      if (star.alpha > 1) star.alpha = 1
      ctx.globalAlpha = star.alpha * 0.5 // Keep stars subtle
      ctx.fillStyle = '#e2e8f0' // Silver stars
      ctx.beginPath()
      ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2)
      ctx.fill()
    })
    ctx.restore()

    // Draw particles and connecting lines (灵气连接)
    ctx.save()
    for (let i = 0; i < particles.length; i++) {
      particles[i].update()
      particles[i].draw()
      
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x
        const dy = particles[i].y - particles[j].y
        const dist = Math.sqrt(dx * dx + dy * dy)
        
        if (dist < 120) {
          ctx.beginPath()
          ctx.strokeStyle = particles[i].color
          ctx.globalAlpha = (1 - dist / 120) * 0.25 * particles[i].alpha
          ctx.lineWidth = 0.8
          ctx.moveTo(particles[i].x, particles[i].y)
          ctx.lineTo(particles[j].x, particles[j].y)
          ctx.stroke()
        }
      }
    }
    ctx.restore()
    
    animationFrameId = requestAnimationFrame(animate)
  }

  animate()

  const handleResize = () => {
    width = window.innerWidth
    height = window.innerHeight
    canvas.width = width
    canvas.height = height
  }

  window.addEventListener('resize', handleResize)
}

// Ensure selected key matches current route
onMounted(() => {
  selectedKeys.value = [route.name as string || 'Profile']
  void authStore.fetchUser()
  initParticles()
})

onBeforeUnmount(() => {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
  }
})

watch(() => route.name, (newName) => {
  if (newName) {
    selectedKeys.value = [newName as string]
  }
})
</script>

<template>
  <a-layout class="h-screen overflow-hidden bg-[#0b0e14] relative">
    <!-- 动态星空灵气背景 -->
    <canvas ref="canvasRef" class="absolute inset-0 z-0 pointer-events-none"></canvas>
    
    <a-layout-sider v-if="!isMobile" v-model:collapsed="collapsed" collapsible breakpoint="lg" theme="dark" class="sider-custom z-10">
      <div class="logo h-16 flex items-center justify-center relative z-10">
        <div class="absolute inset-0 bg-gradient-to-r from-cyan-500/10 to-indigo-500/10 opacity-50"></div>
        <h1 class="text-slate-100 text-xl font-bold tracking-widest truncate px-4 drop-shadow-[0_2px_4px_rgba(56,189,248,0.5)]" v-if="!collapsed">{{ $t('app.name') }}</h1>
        <h1 class="text-slate-100 text-xl font-bold tracking-widest drop-shadow-[0_2px_4px_rgba(56,189,248,0.5)]" v-else>合欢</h1>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        theme="dark"
        mode="inline"
        @click="handleMenuClick"
      >
        <a-menu-item key="Profile">
          <template #icon><UserIcon :size="18" /></template>
          <span>{{ $t('menu.profile') }}</span>
        </a-menu-item>
        <a-menu-item key="Gallery">
          <template #icon><Compass :size="18" /></template>
          <span>{{ $t('menu.gallery') }}</span>
        </a-menu-item>
        <a-menu-item key="CustomFeatures">
          <template #icon><Wand2 :size="18" /></template>
          <span>{{ $t('menu.custom_features') }}</span>
        </a-menu-item>
        <a-menu-item key="History">
          <template #icon><HistoryIcon :size="18" /></template>
          <span>{{ $t('menu.history') }}</span>
        </a-menu-item>
        <a-menu-item key="MyFavorites">
          <template #icon><Bookmark :size="18" /></template>
          <span>{{ $t('menu.my_favorites') }}</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <!-- 移动端不再需要 Drawer，改为底部导航 -->
    
      <a-layout class="flex flex-col h-screen overflow-hidden bg-transparent">
      <a-layout-header class="header-custom px-4 md:px-6 flex justify-between items-center shrink-0 z-10 sticky top-0">
        <div class="header-left flex items-center">
          <h2 class="text-lg font-bold text-slate-200 tracking-wide m-0 drop-shadow-sm">{{ pageTitle }}</h2>
        </div>
        <div class="header-right flex items-center space-x-4">
          <div class="balance flex items-center bg-slate-500/40 backdrop-blur-md px-3 py-1 rounded-full border border-cyan-500/20 shadow-sm transition-all hover:shadow-[0_0_8px_rgba(56,189,248,0.3)] hover:scale-105">
            <Wallet :size="14" class="text-cyan-400 mr-1.5 drop-shadow-[0_0_3px_rgba(56,189,248,0.5)]" />
            <span class="text-slate-200 font-bold tracking-wide text-sm">{{ authStore.user?.credits || 0 }} <span class="text-slate-400 text-xs font-normal">{{ $t('app.credits') }}</span></span>
          </div>
          
          <a-dropdown placement="bottomRight">
              <div class="user-profile flex items-center cursor-pointer hover:bg-white/5 p-1.5 rounded-lg transition-all border border-transparent hover:border-cyan-500/30">
                <a-avatar class="bg-gradient-to-br from-indigo-500 to-cyan-600 mr-2 shadow-[0_0_10px_rgba(56,189,248,0.2)] border border-white/10 text-white font-bold" :size="32">{{ authStore.user?.username?.charAt(0).toUpperCase() || 'U' }}</a-avatar>
                <span class="font-medium text-slate-200">{{ authStore.user?.username || 'User' }}</span>
              </div>
              <template #overlay>
                <a-menu>
                  <a-menu-item class="text-gray-500" disabled>
                    {{ $t('profile.identity') }}: {{ authStore.user?.current_identity }}
                  </a-menu-item>
                  <a-menu-divider />
                  <a-menu-item @click="handleLogout" class="text-red-500">
                    <div class="flex items-center">
                      <LogOut :size="16" class="mr-2" />
                      <span>{{ $t('menu.logout') }}</span>
                    </div>
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
        </div>
      </a-layout-header>
      
      <a-layout-content ref="layoutContentRef" :class="[
        'm-2 p-3 md:m-6 md:p-6 bg-slate-500/20 backdrop-blur-sm rounded-2xl shadow-[0_8px_32px_rgba(0,0,0,0.4)] border border-slate-400/50 relative overflow-y-auto overflow-x-hidden flex flex-col flex-grow',
        { 'mb-20': isMobile }
      ]">
        <router-view v-slot="{ Component, route: currentRoute }">
          <transition name="fade" mode="out-in">
            <div :key="currentRoute.fullPath" class="flex-grow w-full">
              <component :is="Component" />
            </div>
          </transition>
        </router-view>
      </a-layout-content>
    </a-layout>
    <TaskProgress />
    <TaskDetailModal />
    <TemplateApplyWorkbenchHost v-if="shouldRenderTemplateApplyWorkbench" />
    <MobileTabbar v-if="isMobile" />
  </a-layout>
</template>

<style scoped>
.sider-custom {
  background: rgba(15, 23, 42, 0.4) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-right: 1px solid rgba(56, 189, 248, 0.15);
  position: relative;
  overflow: hidden;
}
.sider-custom::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: radial-gradient(circle at 50% 0%, rgba(56, 189, 248, 0.1) 0%, transparent 50%),
              radial-gradient(circle at 0% 100%, rgba(129, 140, 248, 0.1) 0%, transparent 50%);
  pointer-events: none;
}
:deep(.ant-menu-dark) {
  background: transparent !important;
}
:deep(.ant-layout-sider-children) {
  background: transparent !important;
}
:deep(.ant-menu-dark .ant-menu-item-selected) {
  background: linear-gradient(90deg, rgba(56, 189, 248, 0.1) 0%, rgba(129, 140, 248, 0.1) 100%) !important;
  border-right: 3px solid #38bdf8;
  color: #e2e8f0 !important;
}
:deep(.ant-menu-dark .ant-menu-item:hover) {
  background: rgba(255, 255, 255, 0.05) !important;
  color: #bae6fd !important;
}

.header-custom {
  background: rgba(100, 116, 139, 0.5) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(56, 189, 248, 0.15);
  box-shadow: 0 4px 12px -1px rgba(0, 0, 0, 0.3), 0 2px 6px -1px rgba(0, 0, 0, 0.2);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
