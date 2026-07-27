<script setup lang="ts">
import { computed, reactive } from 'vue'
import {
  DeleteOutlined,
  LockOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  UnlockOutlined,
} from '@ant-design/icons-vue'
import message from 'ant-design-vue/es/message'
import Modal from 'ant-design-vue/es/modal'
import {
  deleteRunPodWorker,
  enableLanAioWorker,
  enableRunPodWorker,
  lockRunPodWorker,
  pauseLanAioWorker,
  pauseRunPodWorker,
  restartLanAioWorker,
  restartRunPodWorker,
  unlockRunPodWorker,
} from '../api/api'
import { isRunPodManualAgentId } from '../utils/runpodProfiles'

type WorkerInfo = {
  agent_id: string
  status?: string
  current_task_id?: string
  provider?: string
  pool_managed?: boolean | string | number
  runtime_profile?: string
  control_state?: string
  runpod_locked?: boolean | string | number
  locked?: boolean | string | number
}

const props = defineProps<{
  worker: WorkerInfo
}>()

const emit = defineEmits<{
  changed: []
}>()

const loading = reactive({
  control: false,
  restart: false,
  lock: false,
  delete: false,
})

const isRunPodWorker = computed(() =>
  isRunPodManualAgentId(props.worker.agent_id || '')
)

const isTruthyFlag = (value: unknown) =>
  value === true || value === 1 || value === '1' || value === 'true' || value === 'True'

const isLanAioWorker = computed(() => {
  const agentId = props.worker.agent_id || ''
  return (
    /^lan_aio_prod_gpu\d+_gpu\d+_[a-z0-9_]+_\d+$/.test(agentId) ||
    (agentId.startsWith('lan_aio_prod_') &&
      props.worker.provider === 'lan_ssh' &&
      isTruthyFlag(props.worker.pool_managed))
  )
})

const canRestartWorker = computed(() => isRunPodWorker.value || isLanAioWorker.value)

const canControlWorker = computed(() => isRunPodWorker.value || isLanAioWorker.value)

const isPausedForControl = computed(() => {
  const controlState = String(props.worker.control_state || '').toLowerCase()
  return controlState === 'disabled' || controlState === 'draining'
})

const controlActionLabel = computed(() => (isPausedForControl.value ? '开启' : '暂停'))

const isRunPodLocked = computed(() =>
  isRunPodWorker.value &&
  (isTruthyFlag(props.worker.runpod_locked) || isTruthyFlag(props.worker.locked))
)

const runControlAction = async () => {
  const shouldEnable = isPausedForControl.value
  loading.control = true
  try {
    if (isRunPodWorker.value) {
      if (shouldEnable) {
        await enableRunPodWorker(props.worker.agent_id)
      } else {
        await pauseRunPodWorker(props.worker.agent_id)
      }
    } else if (shouldEnable) {
      await enableLanAioWorker(props.worker.agent_id)
    } else {
      await pauseLanAioWorker(props.worker.agent_id)
    }
    message.success(shouldEnable ? '已提交开启接单操作' : '已提交暂停操作')
    emit('changed')
  } catch (err) {
    console.error(err)
    message.error(`${shouldEnable ? '开启' : '暂停'}提交失败`)
  } finally {
    loading.control = false
  }
}

const runAction = async (action: 'restart' | 'delete') => {
  if (action === 'delete' && isRunPodLocked.value) {
    message.warning('请先解锁后再删除 RunPod Worker')
    return
  }
  loading[action] = true
  try {
    if (action === 'restart') {
      if (isRunPodWorker.value) {
        await restartRunPodWorker(props.worker.agent_id)
      } else {
        await restartLanAioWorker(props.worker.agent_id)
      }
      message.success('已提交重启操作')
    } else {
      await deleteRunPodWorker(props.worker.agent_id)
      message.success('已提交删除操作')
    }
    emit('changed')
  } catch (err) {
    console.error(err)
    const actionName = action === 'restart' ? '重启' : '删除'
    message.error(`${actionName}提交失败`)
  } finally {
    loading[action] = false
  }
}

const runLockAction = async () => {
  const shouldUnlock = isRunPodLocked.value
  loading.lock = true
  try {
    if (shouldUnlock) {
      await unlockRunPodWorker(props.worker.agent_id, {
        reason: 'dashboard unlock runpod worker',
      })
    } else {
      await lockRunPodWorker(props.worker.agent_id, {
        reason: 'dashboard lock runpod worker',
      })
    }
    message.success(shouldUnlock ? '已解锁 RunPod Worker' : '已锁定 RunPod Worker')
    emit('changed')
  } catch (err) {
    console.error(err)
    message.error(shouldUnlock ? '解锁提交失败' : '锁定提交失败')
  } finally {
    loading.lock = false
  }
}

const confirmControl = () => {
  const shouldEnable = isPausedForControl.value
  const targetLabel = isRunPodWorker.value ? 'RunPod Worker' : 'LAN AIO Worker'
  Modal.confirm({
    title: shouldEnable ? '开启接单？' : `暂停 ${targetLabel}？`,
    content: shouldEnable
      ? `${props.worker.agent_id} 将恢复接单。`
      : `${props.worker.agent_id} 将停止接新单，已接任务不删除。`,
    okText: shouldEnable ? '开启' : '暂停',
    cancelText: '取消',
    onOk: () => runControlAction(),
  })
}

const confirmRestart = () => {
  const targetLabel = isRunPodWorker.value ? 'RunPod Pod' : 'LAN AIO 容器'
  const keepLabel = isRunPodWorker.value
    ? '会保留 GPU 配置和数据卷'
    : '会保留 compose、模型缓存和数据挂载'
  Modal.confirm({
    title: '重启 Worker？',
    content: `${props.worker.agent_id} 将原地重启 ${targetLabel}，${keepLabel}，恢复后自动接单。` +
      '当前任务可能被中断。',
    okText: '重启',
    cancelText: '取消',
    onOk: () => runAction('restart'),
  })
}

const confirmLock = () => {
  const shouldUnlock = isRunPodLocked.value
  Modal.confirm({
    title: shouldUnlock ? '解锁 RunPod Worker？' : '锁定 RunPod Worker？',
    content: shouldUnlock
      ? `${props.worker.agent_id} 解锁后允许手动删除，也会重新成为自动缩容候选。`
      : `${props.worker.agent_id} 锁定后不会被手动删除，也不会被自动缩容删除。`,
    okText: shouldUnlock ? '解锁' : '锁定',
    cancelText: '取消',
    onOk: () => runLockAction(),
  })
}

const confirmDelete = () => {
  if (isRunPodLocked.value) {
    message.warning('请先解锁后再删除 RunPod Worker')
    return
  }
  Modal.confirm({
    title: '删除 RunPod Worker？',
    content: `${props.worker.agent_id} 将先暂停接单，等待当前任务结束后删除 Pod。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => runAction('delete'),
  })
}
</script>

<template>
  <div v-if="isRunPodWorker || isLanAioWorker" class="flex items-center gap-1 shrink-0">
    <a-button v-if="canControlWorker" size="small" type="text" :loading="loading.control" @click.stop="confirmControl">
      <template #icon>
        <play-circle-outlined v-if="isPausedForControl" />
        <pause-circle-outlined v-else />
      </template>
      {{ controlActionLabel }}
    </a-button>
    <a-button v-if="canRestartWorker" size="small" type="text" :loading="loading.restart" @click.stop="confirmRestart">
      <template #icon><reload-outlined /></template>
      重启
    </a-button>
    <a-button v-if="isRunPodWorker" size="small" type="text" :loading="loading.lock" @click.stop="confirmLock">
      <template #icon>
        <unlock-outlined v-if="isRunPodLocked" />
        <lock-outlined v-else />
      </template>
      {{ isRunPodLocked ? '解锁' : '锁定' }}
    </a-button>
    <a-button
      v-if="isRunPodWorker"
      size="small"
      type="text"
      danger
      :disabled="isRunPodLocked"
      :loading="loading.delete"
      @click.stop="confirmDelete"
    >
      <template #icon><delete-outlined /></template>
      删除
    </a-button>
  </div>
</template>
