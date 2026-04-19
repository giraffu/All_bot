<script setup lang="ts">
import { useTasksStore } from '@/stores/tasks'
import { CloseOutlined, DownloadOutlined, SyncOutlined } from '@ant-design/icons-vue'

const tasksStore = useTasksStore()
</script>

<template>
  <div v-if="tasksStore.activeTasks.length > 0" class="fixed bottom-6 right-6 z-[9999] pointer-events-none flex flex-col items-end">
    <div class="w-80 flex flex-col gap-3 pointer-events-auto max-h-[60vh] overflow-y-auto custom-scrollbar pr-2 pb-2">
      <transition-group name="task-list">
        <div 
          v-for="task in tasksStore.activeTasks" 
          :key="task.id" 
          class="bg-slate-900/80 backdrop-blur-md rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.5)] border border-white/10 overflow-hidden flex-shrink-0"
        >
          <div class="p-3 relative">
            <div class="flex justify-between items-center mb-2">
              <h4 class="font-medium text-slate-200 truncate pr-6 text-sm">{{ task.title }}</h4>
              <button 
                @click="tasksStore.removeTask(task.id)" 
                class="text-slate-400 hover:text-red-400 transition-colors absolute top-3 right-3"
              >
                <close-outlined class="text-xs" />
              </button>
            </div>
            
            <div v-if="task.status === 'pending' || task.status === 'running'">
              <div class="flex justify-between text-[11px] text-slate-400 mb-1.5">
                <span>{{ task.status === 'pending' ? (task.queuePos != null ? `等待分配... (前面 ${task.queuePos} 人)` : '等待分配...') : 'AI 渲染中...' }}</span>
                <span class="text-cyan-400">{{ task.progress }}%</span>
              </div>
              <a-progress :percent="task.progress" :show-info="false" status="active" strokeColor="#06b6d4" trailColor="rgba(255,255,255,0.1)" :strokeWidth="6" />
            </div>
            
            <div v-else-if="task.status === 'success'" class="flex items-center justify-between mt-2">
              <span class="text-xs text-emerald-400 font-medium">✨ 生成完成！</span>
              <a-button 
                type="primary" 
                size="small" 
                :href="task.resultUrl" 
                target="_blank" 
                class="bg-cyan-600 hover:bg-cyan-500 border-none text-xs h-6 flex items-center justify-center"
                download
              >
                <template #icon><download-outlined class="text-xs" /></template>
                查看
              </a-button>
            </div>
            
            <div v-else-if="task.status === 'failed'" class="mt-2">
              <span class="text-xs text-red-400 font-medium block mb-1">❌ 生成失败</span>
              <span class="text-[11px] text-slate-400 line-clamp-2 leading-snug" :title="task.error">{{ task.error }}</span>
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
