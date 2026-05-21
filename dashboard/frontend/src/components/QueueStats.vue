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
  ClearOutlined,
  LockOutlined
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { useQueueStatsMonitor } from '../composables/useQueueStatsMonitor'

const {
  status,
  workers,
  concurrencyStats,
  cleaning,
  syncing,
  queueByTypeDisplay,
  cleanZombies,
  syncLock,
} = useQueueStatsMonitor()

const handleCleanZombies = () => {
  Modal.confirm({
    title: '确认清理卡死任务？',
    content: '这将强制终止所有排队超过10分钟的任务，并自动为用户退款、释放并发锁。',
    okText: '确认清理',
    cancelText: '取消',
    okType: 'danger',
    onOk: async () => {
      try {
        const res = await cleanZombies()
        if (res.status === 'success') {
          message.success(`清理成功！共清除了 ${res.removed} 个卡死任务。`)
        } else {
          message.error('清理失败: ' + res.message)
        }
      } catch (err) {
        console.error(err)
        message.error('清理过程中发生错误')
      }
    }
  })
}

const formatDuration = (timestamp) => {
  if (!timestamp) return '-'
  const diff = Math.floor(Date.now() / 1000) - Math.floor(timestamp)
  if (diff < 0) return '0s'
  if (diff < 60) return `${diff}s`
  const m = Math.floor(diff / 60)
  const s = diff % 60
  return `${m}m ${s}s`
}

const handleSyncLock = async (userId) => {
  try {
    const res = await syncLock(userId)
    if (res.status === 'success') {
      message.success(res.message)
    } else {
      message.info(res.message)
    }
  } catch (err) {
    console.error(err)
    message.error('同步并发锁失败')
  }
}
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
    
    <a-row :gutter="[16, 16]" class="mb-4">
      <a-col :xs="24" :sm="6">
        <a-card hoverable class="queue-card border-l-4 border-l-blue-500 h-full">
          <a-statistic
            title="总活跃任务"
            :value="status.queue_size"
            :value-style="{ color: '#1890ff', fontWeight: 'bold' }"
          >
            <template #prefix>
              <thunderbolt-outlined />
            </template>
            <template #suffix>
              <span class="text-xs text-gray-400 font-normal ml-1">排队或执行中</span>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
      
      <a-col :xs="24" :sm="6">
        <a-card hoverable class="queue-card border-l-4 border-l-green-500 h-full">
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

      <a-col :xs="24" :sm="6">
        <a-card hoverable class="queue-card border-l-4 border-l-orange-500 h-full">
          <a-statistic
            title="用户并发锁"
            :value="status.concurrency_locks || 0"
            :value-style="{ color: '#fa8c16', fontWeight: 'bold' }"
          >
            <template #prefix>
              <lock-outlined />
            </template>
            <template #suffix>
              <span class="text-xs text-gray-400 font-normal ml-1">个活动锁</span>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
      
      <a-col :xs="24" :sm="6" v-if="queueByTypeDisplay.length > 0">
        <a-card hoverable class="queue-card border-l-4 border-l-purple-500 h-full">
           <div class="text-gray-500 mb-1">活跃任务详情</div>
           <div class="flex flex-col gap-1 max-h-24 overflow-y-auto pr-2 custom-scrollbar">
             <div v-for="item in queueByTypeDisplay" :key="item.type" class="flex justify-between items-center text-sm border-b border-gray-100 pb-1 last:border-0">
               <span class="truncate pr-2" :title="item.type">{{ item.type }}</span>
               <span class="font-bold text-purple-600 shrink-0">{{ item.count }}</span>
             </div>
           </div>
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="6" v-else>
        <a-card hoverable class="queue-card border-l-4 border-l-gray-300 h-full">
          <a-statistic
            title="活跃任务详情"
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

    <!-- Worker 实时状态卡片组 -->
    <div class="mb-2 mt-6">
      <h4 class="text-md font-bold text-gray-700 flex items-center gap-2">
        <robot-outlined class="text-green-500" /> Worker 节点实时状态
      </h4>
    </div>
    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :sm="12" :md="8" :lg="6" v-for="worker in workers" :key="worker.agent_id">
        <a-card size="small" hoverable class="worker-card h-full flex flex-col" :class="{'border-t-2 border-t-green-500': worker.status === 'running', 'border-t-2 border-t-gray-300': worker.status === 'idle'}">
          <template #title>
            <div class="flex justify-between items-center w-full">
              <span class="font-mono text-sm font-bold truncate pr-2" :title="worker.agent_id">{{ worker.agent_id }}</span>
              <a-badge :status="worker.status === 'running' ? 'processing' : 'default'" :text="worker.status === 'running' ? '忙碌' : '空闲'" />
            </div>
          </template>
          
          <div class="flex flex-col gap-2 flex-grow">
            <!-- 正在执行的任务信息 -->
            <div v-if="worker.status === 'running' && worker.current_task_id" class="bg-gray-50 p-2 rounded text-sm flex-grow flex flex-col justify-between">
              <div>
                <div class="flex justify-between mb-1">
                  <span class="text-gray-500 text-xs">任务类型</span>
                  <a-tag color="purple" size="small" class="m-0 border-0">{{ worker.current_task_type || 'Unknown' }}</a-tag>
                </div>
                <div class="flex justify-between mb-2">
                  <span class="text-gray-500 text-xs">已执行</span>
                  <span class="font-mono text-xs text-gray-700">{{ formatDuration(worker.current_task_created_at) }}</span>
                </div>
                <div class="truncate text-xs text-gray-400 font-mono mb-2" :title="worker.current_task_id">
                  ID: {{ worker.current_task_id.substring(0, 8) }}...
                </div>
              </div>
              <div>
                <div class="flex justify-between text-xs mb-1">
                  <span class="text-gray-500">进度</span>
                  <span class="text-blue-600 font-bold">{{ Math.round((worker.current_task_progress || 0) * 100) }}%</span>
                </div>
                <a-progress :percent="Math.round((worker.current_task_progress || 0) * 100)" :show-info="false" size="small" strokeColor="#1890ff" class="m-0" />
              </div>
            </div>
            
            <!-- 空闲状态 -->
            <div v-else class="flex-grow flex flex-col items-center justify-center py-4 text-gray-400">
              <picture-outlined class="text-2xl mb-2 opacity-50" />
              <span class="text-xs">等待任务分发中...</span>
            </div>
            
            <div class="mt-auto pt-2 border-t border-gray-100 text-xs text-gray-400 flex justify-between">
              <span class="truncate" :title="worker.types">支持: {{ worker.types.split(',').length }} 类</span>
              <span>心跳: {{ formatDuration(worker.last_seen) }} 前</span>
            </div>
          </div>
        </a-card>
      </a-col>
      <a-col :span="24" v-if="workers.length === 0">
        <a-empty description="暂无在线的 Worker 节点" />
      </a-col>
    </a-row>

    <!-- 用户并发锁与活跃任务表 -->
    <div class="mb-2 mt-6">
      <h4 class="text-md font-bold text-gray-700 flex items-center gap-2">
        <lock-outlined class="text-orange-500" /> 用户并发锁状态监控
      </h4>
    </div>
    <a-card class="mb-4">
      <a-table 
        :dataSource="concurrencyStats" 
        :rowKey="record => record.user_id" 
        size="small"
        :pagination="{ pageSize: 5 }"
      >
        <a-table-column title="用户 ID" dataIndex="user_id" key="user_id">
          <template #default="{ text }">
            <span class="font-mono text-gray-600">{{ text }}</span>
          </template>
        </a-table-column>
        <a-table-column title="用户名" dataIndex="username" key="username">
          <template #default="{ text }">
            <span class="font-bold text-gray-800">{{ text }}</span>
          </template>
        </a-table-column>
        <a-table-column title="当前并发锁" dataIndex="concurrency_locks" key="concurrency_locks">
          <template #default="{ text }">
            <a-tag :color="text > 0 ? 'orange' : 'default'">{{ text }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="活跃排队任务数" dataIndex="active_tasks" key="active_tasks">
          <template #default="{ text }">
            <a-tag :color="text > 0 ? 'blue' : 'default'">{{ text }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="状态评估" key="status_eval">
          <template #default="{ record }">
            <a-tag v-if="record.concurrency_locks > record.active_tasks" color="red">可能有锁遗留</a-tag>
            <a-tag v-else-if="record.concurrency_locks === record.active_tasks && record.active_tasks > 0" color="green">正常执行</a-tag>
            <a-tag v-else-if="record.active_tasks > record.concurrency_locks" color="purple">超限排队</a-tag>
            <span v-else class="text-gray-400 text-xs">空闲</span>
          </template>
        </a-table-column>
        <a-table-column title="操作" key="action">
          <template #default="{ record }">
            <a-button 
              v-if="record.concurrency_locks > record.active_tasks" 
              type="primary" 
              size="small" 
              danger
              @click="handleSyncLock(record.user_id)"
              :loading="syncing[record.user_id]"
            >
              一键修复
            </a-button>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

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
.worker-card {
  transition: all 0.3s;
  border-radius: 6px;
}
.worker-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #e5e7eb;
  border-radius: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #d1d5db;
}
</style>
