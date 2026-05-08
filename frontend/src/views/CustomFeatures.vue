<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { 
  PlayCircle, 
  Video, 
  Wallet,
  Wand2,
  Sparkles,
  Repeat
} from 'lucide-vue-next'

const router = useRouter()
const { t } = useI18n()
const loading = ref(true)

const features = [
  {
    key: 'i2i_pro',
    title: 'lab.cards.face_swap_title',
    description: 'lab.cards.face_swap_desc',
    icon: Sparkles,
    color: 'bg-purple-100 text-purple-600',
    cost: 6,
    route: 'ImageAndPrompt' 
  },
  {
    key: 'i2i_draw',
    title: 'lab.cards.i2i_draw_title',
    description: 'lab.cards.i2i_draw_desc',
    icon: Wand2,
    color: 'bg-pink-100 text-pink-600',
    cost: 3,
    route: 'ImageAndPrompt' 
  },
  {
    key: 'edit',
    title: 'lab.cards.custom_edit_title',
    description: 'lab.cards.custom_edit_desc',
    icon: Wand2,
    color: 'bg-teal-100 text-teal-600',
    cost: 2,
    route: 'ImageAndPrompt'
  },
  {
    key: 'faceswap',
    title: 'lab.cards.fast_face_swap_title',
    description: 'lab.cards.fast_face_swap_desc',
    icon: Repeat,
    color: 'bg-indigo-100 text-indigo-600',
    cost: 1,
    route: 'FaceSwap'
  },
  {
    key: 'face_video',
    title: 'lab.cards.video_face_swap_title',
    description: 'lab.cards.video_face_swap_desc',
    icon: Video,
    color: 'bg-blue-100 text-blue-600',
    cost: 18,
    route: 'VideoSwap'
  },
  {
    key: 'custom_video',
    title: 'lab.cards.custom_video_title',
    description: 'lab.cards.custom_video_desc',
    icon: PlayCircle,
    color: 'bg-cyan-100 text-cyan-600',
    cost: 6,
    route: 'SingleImageToVideo'
  },
  {
    key: 'video_lora',
    title: 'lab.cards.img2video_title',
    description: 'lab.cards.img2video_desc',
    icon: Video,
    color: 'bg-emerald-100 text-emerald-600',
    cost: 6,
    route: 'SingleImageToVideo'
  },
  {
    key: 'ltx_video',
    title: 'lab.cards.high_res_video_title',
    description: 'lab.cards.high_res_video_desc',
    icon: Sparkles,
    color: 'bg-amber-100 text-amber-600',
    cost: 10,
    route: 'SingleImageToVideo'
  }
]

const handleFeatureClick = (route: string, feature: any) => {
  router.push({ 
    name: route,
    query: { 
      type: feature.key,
      title: t(feature.title),
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
        {{ $t('lab.title') }}
      </h2>
      
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 sm:gap-6">
        <a-card 
          v-for="feature in features" 
          :key="feature.key"
          hoverable 
          class="feature-card h-full flex flex-col overflow-hidden transition-all duration-300 border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-cyan-500/30 hover:shadow-[0_8px_24px_rgba(56,189,248,0.15)] hover:-translate-y-1 group"
          :bodyStyle="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column' }"
          @click="handleFeatureClick(feature.route, feature)"
        >
          <div class="p-3 sm:p-5 flex-grow relative overflow-hidden flex flex-col">
            <!-- Decorative glow on hover -->
            <div class="absolute -top-10 -right-10 w-24 h-24 bg-cyan-500/10 rounded-full blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            
            <div class="flex justify-between items-start mb-2 sm:mb-3 relative z-10">
              <div class="w-8 h-8 sm:w-10 sm:h-10 shrink-0 rounded-lg flex items-center justify-center bg-slate-500/50 border border-slate-400 text-cyan-400 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(56,189,248,0.4)]">
                <component :is="feature.icon" :size="16" class="sm:hidden" />
                <component :is="feature.icon" :size="20" class="hidden sm:block" />
              </div>
              <span class="bg-white/20 text-cyan-200 border border-cyan-300/30 px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium flex items-center shadow-inner whitespace-nowrap shrink-0 ml-1">
                <Wallet :size="10" class="mr-1 text-cyan-200 sm:hidden"/>
                <Wallet :size="12" class="mr-1 text-cyan-200 hidden sm:block"/>
                {{ feature.cost }}
              </span>
            </div>
            <div class="flex flex-col flex-grow justify-start">
              <h3 class="text-sm sm:text-base font-bold text-slate-100 mb-1 relative z-10 drop-shadow-sm truncate">{{ $t(feature.title) }}</h3>
              <p class="text-slate-400 text-xs sm:text-sm line-clamp-2 relative z-10 leading-snug">{{ $t(feature.description) }}</p>
            </div>
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
