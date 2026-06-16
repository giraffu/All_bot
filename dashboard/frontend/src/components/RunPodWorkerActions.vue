<script setup lang="ts">
import { computed, reactive } from 'vue'
import { DeleteOutlined, PauseCircleOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { deleteRunPodWorker, pauseRunPodWorker } from '../api/api'

type WorkerInfo = {
  agent_id: string
  status?: string
  current_task_id?: string
}

const props = defineProps<{
  worker: WorkerInfo
}>()

const emit = defineEmits<{
  changed: []
}>()

const loading = reactive({
  pause: false,
  delete: false,
})

const isRunPodWorker = computed(() =>
  /^runpod_prod_(img2img|image_to_video|wan22_video_v2|i2i_pro)_manual_\d+$/.test(
    props.worker.agent_id || ''
  )
)

const runAction = async (action: 'pause' | 'delete') => {
  loading[action] = true
  try {
    if (action === 'pause') {
      await pauseRunPodWorker(props.worker.agent_id)
      message.success('已提交暂停操作')
    } else {
      await deleteRunPodWorker(props.worker.agent_id)
      message.success('已提交删除操作')
    }
    emit('changed')
  } catch (err) {
    console.error(err)
    message.error(action === 'pause' ? '暂停提交失败' : '删除提交失败')
  } finally {
    loading[action] = false
  }
}

const confirmPause = () => {
  Modal.confirm({
    title: '暂停 RunPod Worker？',
    content: `${props.worker.agent_id} 将停止接新单，已接任务不删除。`,
    okText: '暂停',
    cancelText: '取消',
    onOk: () => runAction('pause'),
  })
}

const confirmDelete = () => {
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
  <div v-if="isRunPodWorker" class="flex items-center gap-1 shrink-0">
    <a-button size="small" type="text" :loading="loading.pause" @click.stop="confirmPause">
      <template #icon><pause-circle-outlined /></template>
      暂停
    </a-button>
    <a-button size="small" type="text" danger :loading="loading.delete" @click.stop="confirmDelete">
      <template #icon><delete-outlined /></template>
      删除
    </a-button>
  </div>
</template>
