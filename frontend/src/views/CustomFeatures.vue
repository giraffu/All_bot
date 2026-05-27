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
    key: 'txt2img',
    title: 'lab.cards.txt2img_title',
    description: 'lab.cards.txt2img_desc',
    icon: Sparkles,
    color: 'bg-fuchsia-100 text-fuchsia-600',
    cost: 2,
    route: 'TextToImage'
  },
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
      <h2 class="lab-section-title text-xl font-bold mb-4 flex items-center drop-shadow-sm">
        <span class="w-1.5 h-6 bg-cyan-500 rounded-full mr-2 shadow-[0_0_8px_rgba(56,189,248,0.5)]"></span>
        {{ $t('lab.title') }}
      </h2>
      
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 sm:gap-6">
        <a-card 
          v-for="feature in features" 
          :key="feature.key"
          hoverable 
          class="feature-card h-full flex flex-col overflow-hidden transition-all duration-300 backdrop-blur-md group"
          :bodyStyle="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column' }"
          @click="handleFeatureClick(feature.route, feature)"
        >
          <div class="p-3 sm:p-5 flex-grow relative overflow-hidden flex flex-col">
            <!-- Decorative glow on hover -->
            <div class="absolute -top-10 -right-10 w-24 h-24 bg-cyan-500/10 rounded-full blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            
            <div class="flex justify-between items-start mb-2 sm:mb-3 relative z-10">
              <div class="feature-icon-wrap w-8 h-8 sm:w-10 sm:h-10 shrink-0 rounded-lg flex items-center justify-center group-hover:scale-110 transition-transform">
                <component :is="feature.icon" :size="16" class="sm:hidden" />
                <component :is="feature.icon" :size="20" class="hidden sm:block" />
              </div>
              <span class="feature-cost-badge px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium flex items-center whitespace-nowrap shrink-0 ml-1">
                <Wallet :size="10" class="feature-cost-icon mr-1 sm:hidden"/>
                <Wallet :size="12" class="feature-cost-icon mr-1 hidden sm:block"/>
                {{ feature.cost }}
              </span>
            </div>
            <div class="flex flex-col flex-grow justify-start">
              <h3 class="feature-title text-sm sm:text-base font-bold mb-1 relative z-10 truncate">{{ $t(feature.title) }}</h3>
              <p class="feature-description text-xs sm:text-sm line-clamp-2 relative z-10 leading-snug">{{ $t(feature.description) }}</p>
            </div>
          </div>
        </a-card>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lab-section-title {
  color: var(--theme-text-primary);
}

.feature-card {
  border-radius: 12px;
  background: var(--theme-card-bg) !important;
  border: 1px solid var(--theme-border) !important;
  box-shadow: var(--theme-shadow);
}

.feature-card:hover {
  background: var(--theme-card-hover-bg) !important;
  border-color: var(--theme-border-strong) !important;
  box-shadow: 0 8px 24px rgba(56, 189, 248, 0.12);
  transform: translateY(-0.25rem);
}

.feature-icon-wrap {
  background: var(--theme-pill-bg);
  border: 1px solid var(--theme-border);
  color: #06b6d4;
}

.feature-card:hover .feature-icon-wrap {
  box-shadow: 0 0 12px rgba(56, 189, 248, 0.28);
}

.feature-cost-badge {
  background: var(--theme-panel-bg);
  color: #0891b2;
  border: 1px solid rgba(34, 211, 238, 0.24);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.feature-cost-icon {
  color: #06b6d4;
}

.feature-title {
  color: var(--theme-text-primary);
}

.feature-description {
  color: var(--theme-text-secondary);
}

:deep(.ant-card-body) {
  background: transparent;
}
</style>
