<script setup>
import { 
  ThunderboltOutlined, 
  PictureOutlined, 
  VideoCameraOutlined,
  DashboardOutlined,
  SyncOutlined
} from '@ant-design/icons-vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchBotQueue } from '../api/api'

const queue = ref({
  total_active_tasks: 0,
  img2img_active_tasks: 0,
  img2video_active_tasks: 0
})

const loading = ref(false)
let timer = null

const updateQueue = async () => {
  try {
    const data = await fetchBotQueue()
    if (data) {
      queue.value = data
    }
  } catch (err) {
    console.error('Error fetching queue:', err)
  }
}

onMounted(() => {
  updateQueue()
  timer = setInterval(updateQueue, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="mb-6">
    <div class="flex items-center gap-2 mb-4">
      <dashboard-outlined class="text-blue-500 text-lg" />
      <h3 class="text-lg font-bold text-gray-800 m-0">机器人实时排队情况</h3>
      <a-tag color="blue" class="ml-2 flex items-center gap-1">
        <template #icon><sync-outlined spin /></template>
        每秒自动刷新
      </a-tag>
    </div>
    
    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :sm="8">
        <a-card hoverable class="queue-card border-l-4 border-l-blue-500">
          <a-statistic
            title="总排队人数"
            :value="queue.total_active_tasks"
            :value-style="{ color: '#1890ff', fontWeight: 'bold' }"
          >
            <template #prefix>
              <thunderbolt-outlined />
            </template>
            <template #suffix>
              <span class="text-xs text-gray-400 font-normal ml-1">位道友</span>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
      
      <a-col :xs="24" :sm="8">
        <a-card hoverable class="queue-card border-l-4 border-l-orange-500">
          <a-statistic
            title="正在炼丹 (P图)"
            :value="queue.img2img_active_tasks"
            :value-style="{ color: '#fa8c16', fontWeight: 'bold' }"
          >
            <template #prefix>
              <picture-outlined />
            </template>
            <template #suffix>
              <span class="text-xs text-gray-400 font-normal ml-1">炉</span>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
      
      <a-col :xs="24" :sm="8">
        <a-card hoverable class="queue-card border-l-4 border-l-purple-500">
          <a-statistic
            title="正在演武 (视频)"
            :value="queue.img2video_active_tasks"
            :value-style="{ color: '#722ed1', fontWeight: 'bold' }"
          >
            <template #prefix>
              <video-camera-outlined />
            </template>
            <template #suffix>
              <span class="text-xs text-gray-400 font-normal ml-1">场</span>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.queue-card {
  transition: all 0.3s;
  border-radius: 8px;
}
.queue-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
</style>
