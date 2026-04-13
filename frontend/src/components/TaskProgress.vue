<script setup lang="ts">
import { useTasksStore } from '@/stores/tasks'
import { CloseOutlined, DownloadOutlined, SyncOutlined } from '@ant-design/icons-vue'

const tasksStore = useTasksStore()
</script>

<template>
  <div v-if="tasksStore.activeTasks.length > 0" class="fixed top-20 left-0 right-0 z-50 pointer-events-none p-4 md:p-6 lg:left-64 flex justify-end">
    <div class="w-full max-w-sm flex flex-col gap-3 pointer-events-auto max-h-[50vh] overflow-y-auto custom-scrollbar">
      <transition-group name="task-list">
        <div 
          v-for="task in tasksStore.activeTasks" 
          :key="task.id" 
          class="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden"
        >
          <div class="p-4 relative">
            <div class="flex justify-between items-center mb-2">
              <h4 class="font-medium text-gray-800 truncate pr-6">{{ task.title }}</h4>
              <button 
                @click="tasksStore.removeTask(task.id)" 
                class="text-gray-400 hover:text-red-500 transition-colors absolute top-4 right-4"
              >
                <close-outlined />
              </button>
            </div>
            
            <div v-if="task.status === 'pending' || task.status === 'running'">
              <div class="flex justify-between text-xs text-gray-500 mb-1">
                <span>{{ task.status === 'pending' ? (task.queuePos != null ? `等待分配资源... (前面还有 ${task.queuePos} 人)` : '等待分配资源...') : 'AI 渲染中...' }}</span>
                <span>{{ task.progress }}%</span>
              </div>
              <a-progress :percent="task.progress" :show-info="false" status="active" strokeColor="#3b82f6" />
            </div>
            
            <div v-else-if="task.status === 'success'" class="flex items-center justify-between mt-2">
              <span class="text-sm text-green-600 font-medium">生成完成！</span>
              <a-button 
                type="primary" 
                size="small" 
                :href="task.resultUrl" 
                target="_blank" 
                class="bg-green-600 hover:bg-green-700 border-none"
                download
              >
                <template #icon><download-outlined /></template>
                查看 / 下载
              </a-button>
            </div>
            
            <div v-else-if="task.status === 'failed'" class="mt-2">
              <span class="text-sm text-red-600 font-medium block mb-1">生成失败</span>
              <span class="text-xs text-gray-500 line-clamp-2" :title="task.error">{{ task.error }}</span>
            </div>
          </div>
        </div>
      </transition-group>
    </div>
  </div>
</template>

<style scoped>
.task-list-enter-active,
.task-list-leave-active {
  transition: all 0.3s ease;
}
.task-list-enter-from,
.task-list-leave-to {
  opacity: 0;
  transform: translateX(30px);
}
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.5);
  border-radius: 20px;
}
</style>
