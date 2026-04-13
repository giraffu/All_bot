<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { 
  Video, 
  Wallet,
  Zap,
  Smile
} from 'lucide-vue-next'

const router = useRouter()
const loading = ref(true)

const features = [
  {
    key: 'random_faceswap',
    title: '随机换脸',
    description: '只需提供人脸，系统随机挑选精美模板为你换脸。',
    icon: Smile,
    color: 'bg-pink-100 text-pink-600',
    cost: 1,
    route: 'SingleImage'
  },
  {
    key: 'undress',
    title: '快速脱衣',
    description: '（特殊功能）AI 智能处理图像服饰。',
    icon: Zap,
    color: 'bg-red-100 text-red-600',
    cost: 2,
    route: 'SingleImage'
  },
  {
    key: 'masturbation',
    title: '快速自慰',
    description: '（特殊功能）AI 智能动作生成。',
    icon: Zap,
    color: 'bg-orange-100 text-orange-600',
    cost: 2,
    route: 'SingleImage'
  },
  {
    key: 'penetration',
    title: '快速抽插',
    description: '（特殊功能）AI 智能动作生成。',
    icon: Zap,
    color: 'bg-rose-100 text-rose-600',
    cost: 2,
    route: 'SingleImage'
  },
  {
    key: 'perfect_video_insert',
    title: '动图传教士',
    description: '（视频功能）AI 视频动作生成。',
    icon: Video,
    color: 'bg-sky-100 text-sky-600',
    cost: 6,
    route: 'SingleImageToVideo'
  },
  {
    key: 'doggy_style',
    title: '动图后入',
    description: '（视频功能）AI 视频动作生成。',
    icon: Video,
    color: 'bg-fuchsia-100 text-fuchsia-600',
    cost: 6,
    route: 'SingleImageToVideo'
  },
  {
    key: 'blowjob',
    title: '口交黑人',
    description: '（视频功能）AI 视频动作生成。',
    icon: Video,
    color: 'bg-stone-100 text-stone-600',
    cost: 6,
    route: 'SingleImageToVideo'
  },
  {
    key: 'undress_tongue',
    title: '脱衣吐舌',
    description: '（视频功能）AI 视频动作生成。',
    icon: Video,
    color: 'bg-violet-100 text-violet-600',
    cost: 6,
    route: 'SingleImageToVideo'
  },
  {
    key: 'closeup_blowjob',
    title: '特写口交',
    description: '（视频功能）AI 视频动作生成。',
    icon: Video,
    color: 'bg-emerald-100 text-emerald-600',
    cost: 6,
    route: 'SingleImageToVideo'
  }
]

const handleFeatureClick = (route: string, feature: any) => {
  router.push({ 
    name: route,
    query: { 
      type: feature.key,
      title: feature.title,
      cost: feature.cost
    }
  })
}

onMounted(() => {
  setTimeout(() => {
    loading.value = false
  }, 500)
})
</script>

<template>
  <div class="dashboard-container space-y-6">
    <div>
      <h2 class="text-xl font-bold text-slate-200 mb-4 flex items-center drop-shadow-sm">
        <span class="w-1.5 h-6 bg-cyan-500 rounded-full mr-2 shadow-[0_0_8px_rgba(56,189,248,0.5)]"></span>
        懒人功能
      </h2>
      
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        <a-card 
          v-for="feature in features" 
          :key="feature.key"
          hoverable 
          class="feature-card h-full flex flex-col overflow-hidden transition-all duration-300 border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-cyan-500/30 hover:shadow-[0_8px_24px_rgba(56,189,248,0.15)] hover:-translate-y-1 group"
          :bodyStyle="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column' }"
          @click="handleFeatureClick(feature.route, feature)"
        >
          <div class="p-5 flex-grow relative overflow-hidden">
            <!-- Decorative glow on hover -->
            <div class="absolute -top-10 -right-10 w-24 h-24 bg-cyan-500/10 rounded-full blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>

            <div class="flex justify-between items-start mb-3 relative z-10">
              <div class="w-10 h-10 rounded-lg flex items-center justify-center bg-slate-700/50 border border-slate-600 text-cyan-400 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(56,189,248,0.4)]">
                <component :is="feature.icon" :size="20" />
              </div>
              <span class="bg-slate-900/50 text-cyan-300/90 border border-cyan-500/20 px-2 py-0.5 rounded-full text-xs font-medium flex items-center shadow-inner">
                <Wallet :size="12" class="mr-1 text-cyan-400"/> {{ feature.cost }}
              </span>
            </div>
            <h3 class="text-base font-bold text-slate-100 mb-1 relative z-10 drop-shadow-sm">{{ feature.title }}</h3>
            <p class="text-slate-400 text-sm line-clamp-2 relative z-10">{{ feature.description }}</p>
          </div>
        </a-card>
      </div>
    </div>
  </div>
</template>

<style scoped>
.feature-card {
  border-radius: 12px;
  background: transparent !important;
}
:deep(.ant-card-body) {
  background: transparent;
}
</style>
