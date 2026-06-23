// @vitest-environment jsdom

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const queueStatsMocks = vi.hoisted(() => ({
  statusRef: null,
  workersRef: null,
  concurrencyStatsRef: null,
}))

vi.mock('../composables/useQueueStatsMonitor', async () => {
  const { computed, ref } = await vi.importActual('vue')
  queueStatsMocks.statusRef ??= ref({})
  queueStatsMocks.workersRef ??= ref([])
  queueStatsMocks.concurrencyStatsRef ??= ref([])

  return {
    useQueueStatsMonitor: () => ({
      status: queueStatsMocks.statusRef,
      workers: queueStatsMocks.workersRef,
      concurrencyStats: queueStatsMocks.concurrencyStatsRef,
      cleaning: ref(false),
      syncing: ref({}),
      runpodProfileQueueDisplay: computed(() => {
        const status = queueStatsMocks.statusRef.value || {}
        return (status.runpod_profile_queue_details || []).map(item => {
          const rawWaitSeconds = item.max_pending_wait_seconds
          const maxPendingWaitSeconds =
            rawWaitSeconds === null || rawWaitSeconds === undefined
              ? null
              : Number(rawWaitSeconds)

          return {
            profile: item.profile,
            label: item.label,
            supportedTaskTypes: item.supported_task_types || [],
            activeCount: Number(item.active_count || 0),
            pendingCount: Number(item.pending_count || 0),
            maxPendingWaitSeconds: Number.isFinite(maxPendingWaitSeconds)
              ? maxPendingWaitSeconds
              : null,
            oldestPendingTaskId: item.oldest_pending_task_id || null,
            oldestPendingCreatedAt: item.oldest_pending_created_at || null,
          }
        })
      }),
      queueByTypeDisplay: computed(() => {
        const status = queueStatsMocks.statusRef.value || {}
        const queueByType = status.queue_by_type || {}
        const details = status.queue_by_type_details || {}
        const types = Array.from(new Set([...Object.keys(queueByType), ...Object.keys(details)]))

        return types
          .map(type => {
            const detail = details[type] || {}
            const rawWaitSeconds = detail.max_pending_wait_seconds
            const maxPendingWaitSeconds =
              rawWaitSeconds === null || rawWaitSeconds === undefined
                ? null
                : Number(rawWaitSeconds)

            return {
              type,
              count: Number(detail.active_count ?? queueByType[type] ?? 0),
              activeCount: Number(detail.active_count ?? queueByType[type] ?? 0),
              pendingCount: Number(detail.pending_count ?? 0),
              maxPendingWaitSeconds: Number.isFinite(maxPendingWaitSeconds)
                ? maxPendingWaitSeconds
                : null,
            }
          })
          .sort((a, b) => {
            const waitA = a.maxPendingWaitSeconds ?? -1
            const waitB = b.maxPendingWaitSeconds ?? -1
            if (waitA !== waitB) return waitB - waitA
            if (a.activeCount !== b.activeCount) return b.activeCount - a.activeCount
            return a.type.localeCompare(b.type)
          })
      }),
      cleanZombies: vi.fn(),
      syncLock: vi.fn(),
      updateQueue: vi.fn(),
    }),
  }
})

const slotStub = (name) => defineComponent({
  name,
  template: '<div><slot name="title" /><slot name="icon" /><slot name="prefix" /><slot name="suffix" /><slot /></div>',
})

const BadgeStub = defineComponent({
  name: 'BadgeStub',
  props: ['text'],
  template: '<span class="badge-stub">{{ text }}</span>',
})

const StatisticStub = defineComponent({
  name: 'StatisticStub',
  props: ['title', 'value'],
  template: '<div><span>{{ title }}</span><span>{{ value }}</span><slot name="prefix" /><slot name="suffix" /></div>',
})

const WorkerHistoryModalStub = defineComponent({
  name: 'WorkerHistoryModal',
  props: ['open', 'workerId'],
  emits: ['update:open'],
  template: '<div class="worker-history-modal-stub" :data-open="String(open)" :data-worker-id="workerId || \'\'" />',
})

const TableColumnStub = defineComponent({
  name: 'TableColumnStub',
  template: '<div />',
})

const mountQueueStats = async () => {
  const QueueStats = (await import('./QueueStats.vue')).default
  return mount(QueueStats, {
    global: {
      stubs: {
        'a-button': slotStub('AButtonStub'),
        'a-card': slotStub('ACardStub'),
        'a-col': slotStub('AColStub'),
        'a-row': slotStub('ARowStub'),
        'a-tag': slotStub('ATagStub'),
        'a-table': slotStub('ATableStub'),
        'a-table-column': TableColumnStub,
        'a-badge': BadgeStub,
        'a-statistic': StatisticStub,
        'a-progress': slotStub('AProgressStub'),
        'a-empty': slotStub('AEmptyStub'),
        RunPodCapacityManager: slotStub('RunPodCapacityManagerStub'),
        RunPodWorkerActions: slotStub('RunPodWorkerActionsStub'),
        WorkerHistoryModal: WorkerHistoryModalStub,
      },
    },
  })
}

describe('QueueStats worker health display', () => {
  beforeEach(() => {
    queueStatsMocks.statusRef = ref({
      queue_size: 0,
      queue_by_type: {},
      active_workers: 0,
      healthy_workers: 0,
      error_workers: 0,
      quarantined_workers: 0,
      workers_by_status: {},
      comfy_online: false,
      concurrency_locks: 0,
      queue_by_type_details: {},
      runpod_profile_queue_details: [],
    })
    queueStatsMocks.workersRef = ref([])
    queueStatsMocks.concurrencyStatsRef = ref([])
    vi.resetModules()
  })

  it('shows all-fault status and does not render unhealthy workers as idle', async () => {
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      active_workers: 2,
      healthy_workers: 0,
      error_workers: 1,
      quarantined_workers: 1,
      comfy_online: false,
    }
    queueStatsMocks.workersRef.value = [
      {
        agent_id: 'agent-error',
        types: 'ltx_video',
        status: 'error',
        last_seen: Date.now() / 1000,
        health_reason: 'comfy_probe_failed',
        last_error: 'ComfyUI /system_stats probe failed',
        last_error_at: Date.now() / 1000 - 10,
        consecutive_failures: 3,
      },
      {
        agent_id: 'agent-quarantine',
        types: 'wan22_video_v2',
        status: 'quarantined',
        last_seen: Date.now() / 1000,
        health_reason: 'task_infra_failures',
        last_error: 'ComfyUI upload timeout',
        quarantined_until: Date.now() / 1000 + 120,
        consecutive_failures: 3,
      },
    ]

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('ComfyUI 全部故障')
    expect(wrapper.text()).toContain('故障')
    expect(wrapper.text()).toContain('已隔离')
    expect(wrapper.text()).toContain('ComfyUI /system_stats probe failed')
    expect(wrapper.text()).toContain('ComfyUI upload timeout')
    expect(wrapper.text()).not.toContain('等待任务分发中...')
  })

  it('shows partial fault status when at least one worker remains healthy', async () => {
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      active_workers: 3,
      healthy_workers: 2,
      error_workers: 1,
      quarantined_workers: 0,
      comfy_online: true,
    }
    queueStatsMocks.workersRef.value = [
      { agent_id: 'agent-idle', types: 'img2img', status: 'idle', last_seen: Date.now() / 1000 },
      { agent_id: 'agent-running', types: 'ltx_video', status: 'running', last_seen: Date.now() / 1000 },
      {
        agent_id: 'agent-error',
        types: 'wan22_video_v2',
        status: 'error',
        last_seen: Date.now() / 1000,
        last_error: 'ComfyUI node crashed',
        consecutive_failures: 3,
      },
    ]

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('ComfyUI 部分故障')
    expect(wrapper.text()).toContain('空闲')
    expect(wrapper.text()).toContain('忙碌')
    expect(wrapper.text()).toContain('故障')
  })

  it('splits the total task card into active and pending totals', async () => {
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      queue_size: 48,
      queue_by_type_details: {
        image_to_video: {
          active_count: 46,
          pending_count: 12,
          max_pending_wait_seconds: 742,
        },
        i2i_pro: {
          active_count: 2,
          pending_count: 0,
          max_pending_wait_seconds: null,
        },
      },
    }

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('活跃数')
    expect(wrapper.text()).toContain('排队数')
    expect(wrapper.get('.task-total-active .task-total-value').text()).toContain('48')
    expect(wrapper.get('.task-total-pending .task-total-value').text()).toContain('12')
  })

  it('renders all active task detail rows with pending wait metrics', async () => {
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      queue_size: 48,
      queue_by_type: {
        image_to_video: 46,
        i2i_pro: 2,
      },
      queue_by_type_details: {
        image_to_video: {
          active_count: 46,
          pending_count: 12,
          max_pending_wait_seconds: 742,
          oldest_pending_task_id: 'backend-task-old',
          oldest_pending_created_at: 1782050000,
        },
        i2i_pro: {
          active_count: 2,
          pending_count: 0,
          max_pending_wait_seconds: null,
          oldest_pending_task_id: null,
          oldest_pending_created_at: null,
        },
      },
    }

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('活跃任务详情')
    expect(wrapper.text()).toContain('image_to_video')
    expect(wrapper.text()).toContain('i2i_pro')
    expect(wrapper.text()).toContain('12m 22s')
    expect(wrapper.findAll('.active-task-detail-table tbody tr')).toHaveLength(2)
    expect(wrapper.findAll('.active-task-detail-table thead th').map(th => th.text())).toEqual([
      '任务类型',
      '活跃数',
      '排队数',
      '最长排队等待',
    ])
  })

  it('renders runpod profile detail rows with aggregated queue metrics', async () => {
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      runpod_profile_queue_details: [
        {
          profile: 'img2img',
          label: 'img2img / img2img_lora',
          supported_task_types: ['img2img', 'img2img_lora'],
          active_count: 0,
          pending_count: 0,
          max_pending_wait_seconds: null,
        },
        {
          profile: 'image_to_video',
          label: 'image_to_video',
          supported_task_types: ['image_to_video'],
          active_count: 0,
          pending_count: 0,
          max_pending_wait_seconds: null,
        },
        {
          profile: 'wan22_video_v2',
          label: 'wan22_video_v2',
          supported_task_types: ['wan22_video_v2'],
          active_count: 0,
          pending_count: 0,
          max_pending_wait_seconds: null,
        },
        {
          profile: 'i2i_pro',
          label: 'i2i_pro / txt2img / face_swap',
          supported_task_types: ['i2i_pro', 't2i-pornmaster-turbo', 'face_swap'],
          active_count: 15,
          pending_count: 8,
          max_pending_wait_seconds: 901,
        },
        {
          profile: 'scail2',
          label: 'scail2 / 视频生视频',
          supported_task_types: ['scail2_action_transfer', 'scail2_video_replacement'],
          active_count: 2,
          pending_count: 1,
          max_pending_wait_seconds: 620,
        },
        {
          profile: 'ltx_video',
          label: 'ltx_video / 高级图生视频',
          supported_task_types: ['ltx_video', 'ltx_video_flf2v', 'ltx_video_v2v_audio'],
          active_count: 0,
          pending_count: 0,
          max_pending_wait_seconds: null,
        },
      ],
    }

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('活跃 RunPod 详情')
    expect(wrapper.text()).toContain('i2i_pro / txt2img / face_swap')
    expect(wrapper.text()).toContain('t2i-pornmaster-turbo')
    expect(wrapper.text()).toContain('15m 1s')
    expect(wrapper.findAll('.runpod-profile-detail-table tbody tr')).toHaveLength(6)
    expect(wrapper.findAll('.runpod-profile-detail-table thead th').map(th => th.text())).toEqual([
      'RunPod 类型',
      '活跃数',
      '排队数',
      '最长等待',
    ])
  })

  it('renders long worker names without the truncation class', async () => {
    const longAgentId = 'lan_aio_prod_gpu177_gpu0_image_to_video_01'
    queueStatsMocks.workersRef.value = [
      {
        agent_id: longAgentId,
        types: 'image_to_video',
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
    ]

    const wrapper = await mountQueueStats()
    const agentName = wrapper.get('.worker-card-agent')

    expect(agentName.text()).toBe(longAgentId)
    expect(agentName.classes()).not.toContain('truncate')
  })

  it('shows paused status from worker control state', async () => {
    queueStatsMocks.workersRef.value = [
      {
        agent_id: 'lan_aio_prod_gpu177_gpu0_image_to_video_01',
        types: 'wan22_video_v2',
        status: 'idle',
        control_state: 'disabled',
        last_seen: Date.now() / 1000,
      },
    ]

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('暂停中')
    expect(wrapper.text()).toContain('暂停接单中')
  })

  it('opens worker history modal when a worker card is clicked', async () => {
    const agentId = 'worker_remote_01'
    queueStatsMocks.workersRef.value = [
      {
        agent_id: agentId,
        types: 'img2img',
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
    ]

    const wrapper = await mountQueueStats()

    expect(wrapper.get('.worker-history-modal-stub').attributes('data-open')).toBe('false')

    await wrapper.get('.worker-card').trigger('click')

    expect(wrapper.get('.worker-history-modal-stub').attributes('data-open')).toBe('true')
    expect(wrapper.get('.worker-history-modal-stub').attributes('data-worker-id')).toBe(agentId)
  })

  it('opens worker history modal from keyboard activation', async () => {
    const agentId = 'worker_remote_02'
    queueStatsMocks.workersRef.value = [
      {
        agent_id: agentId,
        types: 'img2img',
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
    ]

    const wrapper = await mountQueueStats()

    await wrapper.get('.worker-card').trigger('keydown', { key: 'Enter' })

    expect(wrapper.get('.worker-history-modal-stub').attributes('data-open')).toBe('true')
    expect(wrapper.get('.worker-history-modal-stub').attributes('data-worker-id')).toBe(agentId)
  })

  it('does not open worker history modal when clicking worker controls', async () => {
    queueStatsMocks.workersRef.value = [
      {
        agent_id: 'worker_remote_03',
        types: 'img2img',
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
    ]

    const wrapper = await mountQueueStats()

    await wrapper.get('.worker-card-controls').trigger('click')

    expect(wrapper.get('.worker-history-modal-stub').attributes('data-open')).toBe('false')
  })
})
