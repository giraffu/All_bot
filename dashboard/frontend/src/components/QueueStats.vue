<script setup>
import { 
  ThunderboltOutlined, 
  PictureOutlined, 
  VideoCameraOutlined,
  DashboardOutlined,
  SyncOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClearOutlined
} from '@ant-design/icons-vue'
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { fetchSystemStatus, cleanZombieTasks } from '../api/api'
import { message, Modal } from 'ant-design-vue'

const status = ref({
  queue_size: 0,
  queue_by_type: {},
  active_workers: 0,
  comfy_online: false
})

const loading = ref(false)
const cleaning = ref(false)
let timer = null

const updateQueue = async () => {
  try {
    const data = await fetchSystemStatus()
    if (data) {
      status.value = data
    }
  } catch (err) {
    console.error('Error fetching system status:', err)
  }
}

const handleCleanZombies = () => {
  Modal.confirm({
    title: '确认清理卡死任务？',
    content: '这将强制终止所有排队超过10分钟的任务，并自动为用户退款、释放并发锁。',
    okText: '确认清理',
    cancelText: '取消',
    okType: 'danger',
    onOk: async () => {
      cleaning.value = true
      try {
        const res = await cleanZombieTasks()
        if (res.status === 'success') {
          message.success(`清理成功！共清除了 ${res.removed} 个卡死任务。`)
          updateQueue()
        } else {
          message.error('清理失败: ' + res.message)
        }
      } catch (err) {
        console.error(err)
        message.error('清理过程中发生错误')
      } finally {
        cleaning.value = false
      }
    }
  })
}

const queueByTypeDisplay = computed(() => {
  if (!status.value.queue_by_type || Object.keys(status.value.queue_by_type).length === 0) {
    return []
  }
  return Object.entries(status.value.queue_by_type).map(([type, count]) => ({
    type,
    count
  }))
})

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
      <h3 class="text-lg font-bold text-gray-800 m-0">系统实时监控</h3>
      <a-tag color="blue" class="ml-2 flex items-center gap-1">
        <template #icon><sync-outlined spin /></template>
        每秒自动刷新
      </a-tag>
      
      <div class="ml-auto flex items-center gap-3">
        <a-button type="primary" danger ghost @click="handleCleanZombies" :loading="cleaning">
          <template #icon><clear-outlined /></template>
          一键清理卡死任务
        </a-button>
        <a-tag :color="status.comfy_online ? 'success' : 'error'">
          <template #icon>
            <check-circle-outlined v-if="status.comfy_online" />
            <close-circle-outlined v-else />
          </template>
          ComfyUI {{ status.comfy_online ? '在线' : '离线' }}
        </a-tag>
      </div>
    </div>
    
    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :sm="8">
        <a-card hoverable class="queue-card border-l-4 border-l-blue-500">
          <a-statistic
            title="总排队任务"
            :value="status.queue_size"
            :value-style="{ color: '#1890ff', fontWeight: 'bold' }"
          >
            <template #prefix>
              <thunderbolt-outlined />
            </template>
            <template #suffix>
              <span class="text-xs text-gray-400 font-normal ml-1">个任务</span>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
      
      <a-col :xs="24" :sm="8">
        <a-card hoverable class="queue-card border-l-4 border-l-green-500">
          <a-statistic
            title="活跃 Worker"
            :value="status.active_workers"
            :value-style="{ color: '#52c41a', fontWeight: 'bold' }"
          >
            <template #prefix>
              <robot-outlined />
            </template>
            <template #suffix>
              <span class="text-xs text-gray-400 font-normal ml-1">个节点</span>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
      
      <a-col :xs="24" :sm="8" v-if="queueByTypeDisplay.length > 0">
        <a-card hoverable class="queue-card border-l-4 border-l-purple-500">
           <div class="text-gray-500 mb-1">队列详情</div>
           <div class="flex flex-col gap-1">
             <div v-for="item in queueByTypeDisplay" :key="item.type" class="flex justify-between items-center text-sm">
               <span>{{ item.type }}</span>
               <span class="font-bold text-purple-600">{{ item.count }}</span>
             </div>
           </div>
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="8" v-else>
        <a-card hoverable class="queue-card border-l-4 border-l-gray-300">
          <a-statistic
            title="队列详情"
            value="暂无排队"
            :value-style="{ color: '#8c8c8c', fontSize: '16px' }"
          >
            <template #prefix>
              <picture-outlined />
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
