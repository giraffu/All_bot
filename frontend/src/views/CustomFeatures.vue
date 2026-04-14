<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { 
  PlayCircle, 
  Video, 
  Wallet,
  Wand2,
  Sparkles,
  Repeat
} from 'lucide-vue-next'

const router = useRouter()
const loading = ref(true)

const features = [
  {
    key: 'i2i_pro',
    title: '幻想换脸',
    description: '上传一张人脸图片，AI 将根据你的文字提示词为你实现无缝换脸，生成逼真的图像。',
    icon: Sparkles,
    color: 'bg-purple-100 text-purple-600',
    cost: 6,
    route: 'ImageAndPrompt' 
  },
  {
    key: 'edit',
    title: '自由P图',
    description: '上传图片并提供文字指令，AI将根据你的描述修改图片内容。',
    icon: Wand2,
    color: 'bg-teal-100 text-teal-600',
    cost: 2,
    route: 'ImageAndPrompt'
  },
  {
    key: 'faceswap',
    title: '快速换脸',
    description: '极速人脸替换体验，适合标准场景的快速处理。',
    icon: Repeat,
    color: 'bg-indigo-100 text-indigo-600',
    cost: 1,
    route: 'FaceSwap'
  },
  {
    key: 'face_video',
    title: '视频换脸',
    description: '上传人脸和一段视频，AI 将逐帧替换视频中的人脸，生成自然流畅的换脸视频。',
    icon: Video,
    color: 'bg-blue-100 text-blue-600',
    cost: 20,
    route: 'VideoSwap'
  },
  {
    key: 'custom_video',
    title: '自定义图生视频',
    description: '上传图像，AI 将其转化为生动的视频片段。',
    icon: PlayCircle,
    color: 'bg-cyan-100 text-cyan-600',
    cost: 6,
    route: 'SingleImageToVideo'
  },
  {
    key: 'video_lora',
    title: '图生视频 (附加模型)',
    description: '上传图像，输入提示词并指定动作模型，生成定制动作视频。',
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
        自定义功能
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
