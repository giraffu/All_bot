<script setup lang="ts">
import { useTasksStore } from '@/stores/tasks'
import { CloseOutlined, CheckOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { ref } from 'vue'

const tasksStore = useTasksStore()
const router = useRouter()
const expandedTaskId = ref<string | null>(null)

const isTaskInProgress = (task: any) =>
  task.status === 'pending' || task.status === 'running'

const getProgressStatus = (task: any) => {
  if (task.cancelRequested || task.status === 'cancelled') {
    return 'normal'
  }
  return 'active'
}

const handleClose = (task: any) => {
  tasksStore.removeTask(task.id)
  if (task.status === 'cancelled') {
    message.info(task.refundMessage || '任务已取消')
    return
  }
  message.info('任务进入后台，完成后可在闪回瓶查看')
}

const handleTaskClick = (task: any) => {
  if (task.status === 'pending') {
    expandedTaskId.value = expandedTaskId.value === task.id ? null : task.id
  } else if (task.status === 'success' && task.resultUrl) {
    // 触发全局弹窗，传入 task.id，并用现有信息作为 fallback 
    tasksStore.openDetailModal(task.id, {
      task_id: task.id,
      type: task.type,
      output_file: task.resultUrl
    })
    // 移除任务（关闭悬浮球）
    tasksStore.removeTask(task.id)
  }
}

const doCancelTask = async (taskId: string) => {
  const success = await tasksStore.cancelActiveTask(taskId)
  if (success) {
    expandedTaskId.value = null
  }
}
</script>

<template>
  <div v-if="tasksStore.activeTasks.length > 0" class="fixed bottom-24 right-4 z-[9999] pointer-events-none flex flex-col items-end gap-3">
    <transition-group name="task-list">
      <div 
        v-for="task in tasksStore.activeTasks" 
        :key="task.id" 
        class="relative pointer-events-auto"
      >
        <!-- 主圆球区域 -->
        <div 
          @click="handleTaskClick(task)"
          class="w-14 h-14 rounded-full bg-slate-800/80 backdrop-blur-md shadow-[0_8px_32px_rgba(0,0,0,0.5)] border border-white/10 flex items-center justify-center relative cursor-pointer hover:bg-slate-700/80 transition-colors"
          :class="{'cursor-default': task.status !== 'success'}"
        >
          <!-- 环形进度条 -->
          <div
            v-if="isTaskInProgress(task)"
            class="absolute inset-0 flex items-center justify-center"
          >
            <a-progress 
              type="circle" 
              :percent="task.progress" 
              :size="42"
              :show-info="false" 
              :status="getProgressStatus(task)" 
              strokeColor="#06b6d4" 
              trailColor="rgba(255,255,255,0.1)" 
              :strokeWidth="5" 
            />
          </div>
          
          <!-- 中心状态指示 -->
          <div class="z-10 flex h-10 w-10 items-center justify-center rounded-full bg-slate-900/95 border border-white/8 shadow-inner shadow-black/30">
            <div class="flex flex-col items-center justify-center leading-none">
            <template v-if="task.status === 'pending'">
              <span class="text-[11px] text-cyan-400 font-medium font-mono">
                <template v-if="task.queuePos != null">
                  第<span class="text-[13px] mx-0.5">{{ task.queuePos + 1 }}</span>位
                </template>
                <template v-else>
                  排队中
                </template>
              </span>
            </template>
            <template v-else-if="task.cancelRequested">
              <loading-outlined class="text-amber-400 text-lg" />
            </template>
            <template v-else-if="task.status === 'running'">
              <span class="text-[11px] text-cyan-400 font-medium font-mono">{{ task.progress }}%</span>
            </template>
            <template v-else-if="task.status === 'cancelled'">
              <close-outlined class="text-amber-400 text-xl" />
            </template>
            <template v-else-if="task.status === 'success'">
              <check-outlined class="text-emerald-400 text-2xl" />
            </template>
            <template v-else-if="task.status === 'failed'">
              <close-outlined class="text-red-400 text-xl" />
            </template>
            </div>
          </div>
        </div>

        <!-- 右上角关闭按钮 -->
        <button 
          @click.stop="handleClose(task)" 
          class="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-slate-600 border border-slate-500 text-white flex items-center justify-center hover:bg-red-500 hover:border-red-400 transition-colors z-20 shadow-md"
        >
          <close-outlined class="text-[10px]" />
        </button>

        <!-- 悬浮撤销面板 -->
        <transition name="fade-slide">
          <div v-if="expandedTaskId === task.id && task.status === 'pending'"
               class="absolute right-16 top-1/2 -translate-y-1/2 bg-slate-800 border border-slate-600 rounded-lg p-2 shadow-lg flex items-center whitespace-nowrap z-50">
            <span class="text-xs text-slate-300 mr-3">任务排队中</span>
            <a-button type="primary" danger size="small" @click.stop="doCancelTask(task.id)">
              撤销任务
            </a-button>
          </div>
        </transition>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.task-list-enter-active,
.task-list-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.task-list-enter-from,
.task-list-leave-to {
  opacity: 0;
  transform: scale(0.8) translateY(20px);
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.2s ease;
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translate(10px, -50%);
}
</style>
