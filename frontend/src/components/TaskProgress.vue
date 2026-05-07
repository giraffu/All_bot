<script setup lang="ts">
import { useTasksStore } from '@/stores/tasks'
import { CloseOutlined, CheckOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'

const tasksStore = useTasksStore()
const router = useRouter()

const handleClose = (task: any) => {
  tasksStore.removeTask(task.id)
  message.info('任务进入后台，完成后可在闪回瓶查看')
}

const handleTaskClick = (task: any) => {
  if (task.status === 'success' && task.resultUrl) {
    // 移除任务（关闭悬浮球）
    tasksStore.removeTask(task.id)
    // 跳转到闪回瓶，并带上 task_id 参数，以便自动打开详情
    router.push({ path: '/history', query: { task_id: task.id } })
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
          <a-progress 
            v-if="task.status === 'pending' || task.status === 'running'"
            type="circle" 
            :percent="task.progress" 
            :width="56"
            :show-info="false" 
            status="active" 
            strokeColor="#06b6d4" 
            trailColor="rgba(255,255,255,0.1)" 
            :strokeWidth="6" 
            class="absolute inset-0"
          />
          
          <!-- 中心状态指示 -->
          <div class="z-10 flex flex-col items-center justify-center">
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
            <template v-else-if="task.status === 'running'">
              <span class="text-[11px] text-cyan-400 font-medium font-mono">{{ task.progress }}%</span>
            </template>
            <template v-else-if="task.status === 'success'">
              <check-outlined class="text-emerald-400 text-2xl" />
            </template>
            <template v-else-if="task.status === 'failed'">
              <close-outlined class="text-red-400 text-xl" />
            </template>
          </div>
        </div>

        <!-- 右上角关闭按钮 -->
        <button 
          @click.stop="handleClose(task)" 
          class="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-slate-600 border border-slate-500 text-white flex items-center justify-center hover:bg-red-500 hover:border-red-400 transition-colors z-20 shadow-md"
        >
          <close-outlined class="text-[10px]" />
        </button>
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
</style>
