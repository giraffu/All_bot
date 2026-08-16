<script setup lang="ts">
import { useTasksStore } from '@/stores/tasks'
import { CloseOutlined, CheckOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const tasksStore = useTasksStore()
const { t } = useI18n()
const expandedTaskId = ref<string | null>(null)

const getTaskLabel = (task: any) => {
  if (task.status === 'pending') {
    return task.queuePos != null ? `第 ${task.queuePos + 1} 位` : '排队中'
  }

  if (task.cancelRequested) {
    return '取消中'
  }

  if (task.status === 'running') {
    return task.awaitingResult ? '保存结果中' : '生成中'
  }

  if (task.status === 'success') {
    return '已完成'
  }

  if (task.status === 'cancelled') {
    return '已取消'
  }

  return '失败'
}

const getCloseButtonLabel = (task: any) => {
  if (task.status === 'pending' && !task.cancelRequested) {
    return '撤销任务'
  }
  return '收起任务'
}

const handleClose = async (task: any) => {
  if (task.status === 'pending' && !task.cancelRequested) {
    await doCancelTask(task.id)
    return
  }

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
  <div
    v-if="tasksStore.activeTasks.length > 0"
    class="task-fab-list fixed bottom-24 right-4 z-[9999] flex flex-col items-end gap-3"
    :aria-label="t('profile.my_tasks_title')"
  >
    <transition-group name="task-list">
      <div 
        v-for="task in tasksStore.activeTasks" 
        :key="task.id" 
        class="relative pointer-events-auto"
      >
        <!-- 主圆球区域 -->
        <div 
          @click="handleTaskClick(task)"
          class="task-fab-shell"
          :class="{'cursor-default': task.status !== 'success'}"
          :aria-label="getTaskLabel(task)"
          :title="getTaskLabel(task)"
        >
          <!-- 中心状态指示 -->
          <div class="task-fab-core">
            <div class="flex flex-col items-center justify-center leading-none">
            <template v-if="task.status === 'pending'">
              <span
                v-if="task.queuePos != null"
                class="task-fab-queue-number"
              >
                {{ task.queuePos + 1 }}
              </span>
              <span
                v-else
                class="task-fab-label"
              >
                排队中
              </span>
              <span
                v-if="task.queuePos != null"
                class="task-fab-label"
              >
                排队
              </span>
            </template>
            <template v-else-if="task.cancelRequested">
              <loading-outlined class="task-fab-icon task-fab-icon-warn" />
              <span class="task-fab-label">取消中</span>
            </template>
            <template v-else-if="task.status === 'running'">
              <loading-outlined class="task-fab-icon task-fab-icon-running" />
              <span class="task-fab-label">{{ task.awaitingResult ? '保存中' : '生成中' }}</span>
            </template>
            <template v-else-if="task.status === 'cancelled'">
              <close-outlined class="task-fab-icon task-fab-icon-warn" />
            </template>
            <template v-else-if="task.status === 'success'">
              <check-outlined class="task-fab-icon task-fab-icon-success" />
            </template>
            <template v-else-if="task.status === 'failed'">
              <close-outlined class="task-fab-icon task-fab-icon-danger" />
            </template>
            </div>
          </div>

          <div
            v-if="task.status === 'pending' && task.queuePos != null"
            class="task-fab-badge"
          >
            <span class="task-fab-badge-label">队列</span>
            <span class="task-fab-badge-value">{{ task.queuePos + 1 }}</span>
          </div>
        </div>

        <!-- 右上角关闭按钮 -->
        <button 
          @click.stop="handleClose(task)" 
          class="task-fab-close"
          :title="getCloseButtonLabel(task)"
          :aria-label="getCloseButtonLabel(task)"
        >
          <close-outlined class="text-[10px]" />
        </button>

        <!-- 悬浮撤销面板 -->
        <transition name="fade-slide">
          <div v-if="expandedTaskId === task.id && task.status === 'pending'"
               class="task-fab-popover">
            <span class="task-fab-popover-text">
                <template v-if="task.queuePos != null">
                  当前排在第 {{ task.queuePos + 1 }} 位
                </template>
                <template v-else>
                  排队中
                </template>
            </span>
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
.task-fab-list {
  max-height: calc(100dvh - 8rem);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0.5rem;
  scrollbar-width: thin;
}

.task-fab-shell {
  position: relative;
  display: flex;
  height: 3.5rem;
  width: 3.5rem;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid var(--task-fab-shell-border);
  background: var(--task-fab-shell-bg);
  box-shadow: var(--task-fab-shell-shadow);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  transition: background-color 0.2s ease, border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

.task-fab-shell:hover {
  background: var(--task-fab-shell-hover-bg);
  border-color: var(--task-fab-shell-hover-border);
  box-shadow: var(--task-fab-shell-hover-shadow);
  transform: translateY(-1px);
}

.task-fab-core {
  z-index: 10;
  display: flex;
  height: 2.45rem;
  width: 2.45rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid var(--task-fab-core-border);
  background: var(--task-fab-core-bg);
  box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.08), inset 0 -6px 12px rgba(15, 23, 42, 0.16);
}

.task-fab-queue-number,
.task-fab-running-value {
  font-family: ui-monospace, SFMono-Regular, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.95rem;
  font-weight: 700;
  line-height: 1;
  color: var(--task-fab-accent);
  text-shadow: 0 0 10px var(--task-fab-accent-glow);
}

.task-fab-label {
  margin-top: 0.12rem;
  font-size: 0.54rem;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.04em;
  color: var(--task-fab-label);
}

.task-fab-icon {
  font-size: 1.1rem;
}

.task-fab-icon-success {
  color: var(--task-fab-success);
}

.task-fab-icon-warn {
  color: var(--task-fab-warn);
}

.task-fab-icon-running {
  color: var(--task-fab-accent);
}

.task-fab-icon-danger {
  color: var(--task-fab-danger);
}

.task-fab-badge {
  position: absolute;
  top: -0.45rem;
  left: -0.45rem;
  z-index: 15;
  display: flex;
  min-width: 1.8rem;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.02rem;
  border-radius: 9999px;
  border: 1px solid var(--task-fab-badge-border);
  background: var(--task-fab-badge-bg);
  padding: 0.24rem 0.42rem;
  box-shadow: var(--task-fab-badge-shadow);
}

.task-fab-badge-label {
  font-size: 0.46rem;
  font-weight: 700;
  line-height: 1;
  color: var(--task-fab-badge-label);
}

.task-fab-badge-value {
  font-family: ui-monospace, SFMono-Regular, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.78rem;
  font-weight: 800;
  line-height: 1;
  color: var(--task-fab-badge-value);
}

.task-fab-close {
  position: absolute;
  top: -0.18rem;
  right: -0.18rem;
  z-index: 20;
  display: flex;
  height: 1.25rem;
  width: 1.25rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid var(--task-fab-close-border);
  background: var(--task-fab-close-bg);
  color: var(--task-fab-close-text);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.18);
  transition: background-color 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.task-fab-close:hover {
  background: var(--task-fab-close-hover-bg);
  border-color: var(--task-fab-close-hover-border);
  transform: scale(1.06);
}

.task-fab-popover {
  position: absolute;
  top: 50%;
  right: 4rem;
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 0.7rem;
  white-space: nowrap;
  border-radius: 0.8rem;
  border: 1px solid var(--task-fab-popover-border);
  background: var(--task-fab-popover-bg);
  padding: 0.55rem 0.7rem;
  box-shadow: var(--task-fab-popover-shadow);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  transform: translateY(-50%);
}

.task-fab-popover-text {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--task-fab-popover-text);
}

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
