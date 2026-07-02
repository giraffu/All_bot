// @vitest-environment jsdom

import { defineComponent, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const queueStatsMocks = vi.hoisted(() => ({
  statusRef: null,
  workersRef: null,
  concurrencyStatsRef: null,
}))

const apiMocks = vi.hoisted(() => ({
  fetchRunPodAutoscaler: vi.fn(),
  fetchRunPodOperations: vi.fn(),
  updateRunPodAutoscalerSettings: vi.fn(),
}))

vi.mock('../api/api', () => apiMocks)

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
          const rawNonLowTrustWaitSeconds =
            item.max_non_low_trust_pending_wait_seconds
          const maxNonLowTrustPendingWaitSeconds =
            rawNonLowTrustWaitSeconds === null ||
            rawNonLowTrustWaitSeconds === undefined
              ? null
              : Number(rawNonLowTrustWaitSeconds)

          return {
            profile: item.profile,
            label: item.label,
            autoscalerEnabled: item.autoscaler_enabled !== false,
            supportedTaskTypes: item.supported_task_types || [],
            activeCount: Number(item.active_count || 0),
            pendingCount: Number(item.pending_count || 0),
            activeCountByTaskType: item.active_count_by_task_type || {},
            pendingCountByTaskType: item.pending_count_by_task_type || {},
            nonLowTrustClearPendingCount: Number(
              item.non_low_trust_clear_pending_count || 0
            ),
            nonLowTrustClearPendingCountByTaskType:
              item.non_low_trust_clear_pending_count_by_task_type || {},
            lastNonLowTrustPendingQueueIndex:
              item.last_non_low_trust_pending_queue_index ?? null,
            maxPendingWaitSeconds: Number.isFinite(maxPendingWaitSeconds)
              ? maxPendingWaitSeconds
              : null,
            maxNonLowTrustPendingWaitSeconds: Number.isFinite(
              maxNonLowTrustPendingWaitSeconds
            )
              ? maxNonLowTrustPendingWaitSeconds
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
            const rawNonLowTrustWaitSeconds =
              detail.max_non_low_trust_pending_wait_seconds
            const maxNonLowTrustPendingWaitSeconds =
              rawNonLowTrustWaitSeconds === null ||
              rawNonLowTrustWaitSeconds === undefined
                ? null
                : Number(rawNonLowTrustWaitSeconds)

            return {
              type,
              count: Number(detail.active_count ?? queueByType[type] ?? 0),
              activeCount: Number(detail.active_count ?? queueByType[type] ?? 0),
              pendingCount: Number(detail.pending_count ?? 0),
              lowTrustFreeTierUserCount: Number(
                detail.low_trust_free_tier_user_count ?? 0
              ),
              lowTrustFreeTierTaskCount: Number(
                detail.low_trust_free_tier_task_count ?? 0
              ),
              maxPendingWaitSeconds: Number.isFinite(maxPendingWaitSeconds)
                ? maxPendingWaitSeconds
                : null,
              maxNonLowTrustPendingWaitSeconds: Number.isFinite(
                maxNonLowTrustPendingWaitSeconds
              )
                ? maxNonLowTrustPendingWaitSeconds
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

const ButtonStub = defineComponent({
  name: 'ButtonStub',
  props: ['disabled', 'loading'],
  emits: ['click'],
  template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
})

const InputNumberStub = defineComponent({
  name: 'InputNumberStub',
  props: ['value', 'size', 'min', 'max'],
  emits: ['update:value'],
  template: '<input type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />',
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

const ModalStub = defineComponent({
  name: 'ModalStub',
  props: ['open', 'title'],
  emits: ['update:open'],
  template: '<div v-if="open" class="modal-stub"><h2>{{ title }}</h2><slot /></div>',
})

const WorkerHistoryModalStub = defineComponent({
  name: 'WorkerHistoryModal',
  props: ['open', 'workerId'],
  emits: ['update:open'],
  template: '<div class="worker-history-modal-stub" :data-open="String(open)" :data-worker-id="workerId || \'\'" />',
})

const TableColumnStub = defineComponent({
  name: 'TableColumnStub',
  props: ['title'],
  template: '<div class="table-column-stub">{{ title }}</div>',
})

const mountedWrappers = []

const mountQueueStats = async () => {
  const QueueStats = (await import('./QueueStats.vue')).default
  const wrapper = mount(QueueStats, {
    global: {
      stubs: {
        'a-button': ButtonStub,
        'a-card': slotStub('ACardStub'),
        'a-col': slotStub('AColStub'),
        'a-row': slotStub('ARowStub'),
        'a-input-number': InputNumberStub,
        'a-modal': ModalStub,
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
  mountedWrappers.push(wrapper)
  return wrapper
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
      low_trust_free_tier_pending_user_count: 0,
      low_trust_free_tier_pending_task_count: 0,
    })
    queueStatsMocks.workersRef = ref([])
    queueStatsMocks.concurrencyStatsRef = ref([])
    vi.clearAllMocks()
    apiMocks.fetchRunPodAutoscaler.mockResolvedValue({
      config: {
        paused_profiles: [],
        profile_autoscaler_paused_by_profile: {},
        scale_up_wait_seconds_by_profile: {
          img2img: 20 * 60,
          image_to_video: 30 * 60,
          wan22_video_v2: 30 * 60,
          i2i_pro: 30 * 60,
          scail2: 40 * 60,
          ltx_video: 30 * 60,
          pornmaster_flux2_edit: 30 * 60,
        },
        task_duration_seconds_by_type: {
          img2img: 13,
          img2img_lora: 13,
          image_to_video: 60,
          wan22_video_v2: 60,
          i2i_pro: 12,
          't2i-pornmaster-turbo': 12,
          face_swap: 12,
          scail2_action_transfer: 300,
          scail2_video_replacement: 300,
          ltx_video: 120,
          ltx_video_flf2v: 120,
          ltx_video_v2v_audio: 120,
          pornmaster_flux2_single_edit: 30,
          pornmaster_flux2_multi_edit: 30,
          unknown: 100,
        },
      },
      decisions: [
        {
          profile: 'i2i_pro',
          action: 'scale_up',
          reason: 'scale_up: estimated non-low-trust clear time 1860s exceeds 1800s',
          estimated_clear_time_seconds: 1860,
          estimated_non_low_trust_clear_time_seconds: 1860,
          non_low_trust_clear_pending_count: 155,
          capacity_status: 'ok',
        },
        {
          profile: 'pornmaster_flux2_edit',
          action: 'hold',
          reason: 'hold: estimated non-low-trust clear time within threshold',
          estimated_clear_time_seconds: 60,
          estimated_non_low_trust_clear_time_seconds: 60,
          non_low_trust_clear_pending_count: 2,
          capacity_status: 'ok',
        },
      ],
    })
    apiMocks.updateRunPodAutoscalerSettings.mockResolvedValue({
      config: {
        paused_profiles: [],
        profile_autoscaler_paused_by_profile: {},
        scale_up_wait_seconds_by_profile: {
          img2img: 25 * 60,
          image_to_video: 30 * 60,
          wan22_video_v2: 30 * 60,
          i2i_pro: 30 * 60,
          scail2: 40 * 60,
          ltx_video: 30 * 60,
          pornmaster_flux2_edit: 30 * 60,
        },
        task_duration_seconds_by_type: {
          img2img: 15,
          img2img_lora: 15,
        },
      },
      decisions: [],
    })
    apiMocks.fetchRunPodOperations.mockResolvedValue({ operations: [] })
    vi.resetModules()
  })

  afterEach(() => {
    for (const wrapper of mountedWrappers.splice(0)) {
      wrapper.unmount()
    }
    vi.useRealTimers()
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
          low_trust_free_tier_user_count: 3,
          low_trust_free_tier_task_count: 4,
        },
        i2i_pro: {
          active_count: 2,
          pending_count: 0,
          max_pending_wait_seconds: null,
        },
      },
      low_trust_free_tier_pending_user_count: 3,
      low_trust_free_tier_pending_task_count: 4,
    }

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('活跃数')
    expect(wrapper.text()).toContain('排队数')
    expect(wrapper.text()).toContain('低信任免费层')
    expect(wrapper.get('.task-total-active .task-total-value').text()).toContain('48')
    expect(wrapper.get('.task-total-pending .task-total-value').text()).toContain('12')
    expect(wrapper.get('.task-total-submetric').text()).toContain('3')
    expect(wrapper.get('.task-total-submetric').text()).toContain('4 任务')
  })

  it('shows identity and max concurrency columns for user lock rows', async () => {
    queueStatsMocks.concurrencyStatsRef.value = [
      {
        user_id: 123,
        username: 'tester',
        current_identity: '核心弟子',
        effective_identity: '核心弟子',
        max_concurrent_tasks: 8,
        concurrency_locks: 3,
        active_tasks: 3,
      },
    ]

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('用户并发锁状态监控')
    expect(wrapper.text()).toContain('有效身份')
    expect(wrapper.text()).toContain('最大并发')
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
          low_trust_free_tier_user_count: 2,
          low_trust_free_tier_task_count: 3,
        },
        i2i_pro: {
          active_count: 2,
          pending_count: 0,
          max_pending_wait_seconds: null,
          oldest_pending_task_id: null,
          oldest_pending_created_at: null,
          low_trust_free_tier_user_count: 0,
          low_trust_free_tier_task_count: 0,
        },
      },
    }

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('活跃任务详情')
    expect(wrapper.text()).toContain('image_to_video')
    expect(wrapper.text()).toContain('i2i_pro')
    expect(wrapper.text()).toContain('低信任用户')
    expect(wrapper.text()).toContain('12m 22s')
    expect(wrapper.findAll('.active-task-detail-table tbody tr')).toHaveLength(2)
    expect(wrapper.findAll('.active-task-detail-table thead th').map(th => th.text())).toEqual([
      '任务类型',
      '活跃数',
      '排队数',
      '低信任用户',
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
          max_non_low_trust_pending_wait_seconds: 720,
        },
        {
          profile: 'scail2',
          label: 'scail2 / 视频生视频',
          supported_task_types: ['scail2_action_transfer', 'scail2_video_replacement'],
          active_count: 2,
          pending_count: 1,
          max_pending_wait_seconds: 620,
          max_non_low_trust_pending_wait_seconds: 500,
        },
        {
          profile: 'ltx_video',
          label: 'ltx_video / 高级图生视频',
          supported_task_types: ['ltx_video', 'ltx_video_flf2v', 'ltx_video_v2v_audio'],
          active_count: 0,
          pending_count: 0,
          max_pending_wait_seconds: null,
        },
        {
          profile: 'pornmaster_flux2_edit',
          label: 'pornmaster_flux2',
          supported_task_types: [
            'pornmaster_flux2_single_edit',
            'pornmaster_flux2_multi_edit',
          ],
          active_count: 3,
          pending_count: 4,
          max_pending_wait_seconds: 1000,
          max_non_low_trust_pending_wait_seconds: 880,
        },
      ],
      queue_by_type_details: {
        scail2_action_transfer: {
          active_count: 2,
          pending_count: 1,
          max_pending_wait_seconds: 620,
          max_non_low_trust_pending_wait_seconds: 500,
        },
        scail2_action_transfer_long: {
          active_count: 0,
          pending_count: 5,
          max_pending_wait_seconds: 5940,
          max_non_low_trust_pending_wait_seconds: 5940,
        },
        scail2_face_swap_v2: {
          active_count: 7,
          pending_count: 7,
          max_pending_wait_seconds: 6900,
          max_non_low_trust_pending_wait_seconds: 6900,
        },
      },
    }
    queueStatsMocks.workersRef.value = [
      {
        agent_id: 'runpod_prod_i2i_pro_manual_01',
        types: 'i2i_pro,t2i-pornmaster-turbo,face_swap',
        provider: 'runpod',
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
      {
        agent_id: 'runpod_prod_i2i_pro_manual_02',
        types: 'i2i_pro',
        status: 'running',
        last_seen: Date.now() / 1000,
      },
      {
        agent_id: 'lan_aio_prod_gpu999_gpu0_i2i_pro_01',
        types: 'i2i_pro,t2i-pornmaster-turbo',
        provider: 'lan_ssh',
        pool_managed: true,
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
      {
        agent_id: 'worker_remote_face_swap',
        types: 'face_swap',
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
      {
        agent_id: 'runpod_prod_scail2_manual_01',
        types: 'scail2_action_transfer',
        provider: 'runpod',
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
      {
        agent_id: 'runpod_prod_pornmaster_flux2_edit_manual_01',
        types: 'pornmaster_flux2_single_edit,pornmaster_flux2_multi_edit',
        runtime_profile: 'pornmaster_flux2_edit',
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
      {
        agent_id: 'lan_aio_prod_gpu252_gpu0_pornmaster_flux2_edit_01',
        types: 'pornmaster_flux2_single_edit,pornmaster_flux2_multi_edit',
        runtime_profile: 'pornmaster_flux2_edit',
        provider: 'lan_ssh',
        status: 'idle',
        last_seen: Date.now() / 1000,
      },
    ]

    const wrapper = await mountQueueStats()
    await flushPromises()
    const i2iRow = wrapper
      .findAll('.runpod-profile-detail-table tbody tr')
      .find(row => row.text().includes('i2i_pro / txt2img / face_swap'))
    const pornmasterRow = wrapper
      .findAll('.runpod-profile-detail-table tbody tr')
      .find(row => row.text().includes('pornmaster_flux2'))
    const scail2Row = wrapper
      .findAll('.runpod-profile-detail-table tbody tr')
      .find(row => row.text().includes('scail2 / 视频生视频'))

    expect(wrapper.text()).toContain('活跃 Worker 详情')
    expect(wrapper.text()).toContain('i2i_pro / txt2img / face_swap')
    expect(wrapper.text()).toContain('t2i-pornmaster-turbo')
    expect(wrapper.text()).toContain('15m 1s')
    expect(i2iRow?.text()).toContain('12m 0s')
    expect(wrapper.text()).toContain('31m 0s')
    expect(wrapper.text()).toContain(
      'scale_up: estimated non-low-trust clear time 1860s exceeds 1800s'
    )
    expect(pornmasterRow?.exists()).toBe(true)
    expect(pornmasterRow?.text()).toContain('pornmaster_flux2_single_edit')
    expect(pornmasterRow?.text()).toContain('16m 40s')
    expect(pornmasterRow?.text()).toContain('14m 40s')
    expect(pornmasterRow?.text()).toContain('RunPod1')
    expect(pornmasterRow?.text()).toContain('本地1')
    expect(pornmasterRow?.text()).toContain('1m 0s')
    expect(pornmasterRow?.text()).toContain('自动')
    expect(pornmasterRow?.find('.profile-autoscaler-toggle').exists()).toBe(true)
    expect(scail2Row?.exists()).toBe(true)
    expect(scail2Row?.text()).toContain('scail2_action_transfer_long')
    expect(scail2Row?.text()).toContain('scail2_face_swap_v2')
    expect(scail2Row?.findAll('td')[2]?.text()).toBe('9')
    expect(scail2Row?.findAll('td')[3]?.text()).toBe('13')
    expect(scail2Row?.findAll('td')[4]?.text()).toBe('1h 55m')
    expect(i2iRow?.exists()).toBe(true)
    expect(i2iRow?.text()).toContain('RunPod2')
    expect(i2iRow?.text()).toContain('本地2')
    expect(wrapper.findAll('.runpod-profile-detail-table tbody tr')).toHaveLength(7)
    expect(wrapper.findAll('.runpod-profile-detail-table thead th').map(th => th.text())).toEqual([
      'Worker 类型',
      '服务器',
      '活跃数',
      '排队数',
      '最长等待',
      '非低信任最长等待',
      '预计非低信任用户清空',
      '单任务耗时',
      '清空阈值',
      '自动管理',
    ])
  })

  it('renders default runpod clear-time settings and saves profile updates', async () => {
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      runpod_profile_queue_details: [
        {
          profile: 'img2img',
          label: 'img2img / img2img_lora',
          supported_task_types: ['img2img', 'img2img_lora'],
          active_count: 2,
          pending_count: 1,
          max_pending_wait_seconds: 120,
        },
        {
          profile: 'scail2',
          label: 'scail2 / 视频生视频',
          supported_task_types: ['scail2_action_transfer', 'scail2_video_replacement'],
          active_count: 0,
          pending_count: 0,
          max_pending_wait_seconds: null,
        },
      ],
    }

    const wrapper = await mountQueueStats()
    await flushPromises()
    const rows = wrapper.findAll('.runpod-profile-detail-table tbody tr')
    const img2imgRow = rows.find(row => row.text().includes('img2img / img2img_lora'))
    const scail2Row = rows.find(row => row.text().includes('scail2 / 视频生视频'))

    expect(img2imgRow?.find('.scale-threshold-input').element.value).toBe('20')
    expect(img2imgRow?.find('.task-duration-input').element.value).toBe('13')
    expect(scail2Row?.find('.scale-threshold-input').element.value).toBe('40')
    expect(scail2Row?.find('.task-duration-input').element.value).toBe('300')

    await img2imgRow?.find('.scale-threshold-input').setValue('25')
    await img2imgRow?.find('.task-duration-input').setValue('15')
    await img2imgRow?.find('.scale-threshold-save').trigger('click')
    await flushPromises()

    expect(apiMocks.updateRunPodAutoscalerSettings).toHaveBeenCalledWith({
      scale_up_wait_minutes_by_profile: {
        img2img: 25,
      },
      task_duration_seconds_by_type: {
        img2img: 15,
        img2img_lora: 15,
      },
      reason: 'dashboard clear-time settings update',
    })
  })

  it('toggles autoscaler management for a single runpod profile', async () => {
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      runpod_profile_queue_details: [
        {
          profile: 'img2img',
          label: 'img2img / img2img_lora',
          supported_task_types: ['img2img', 'img2img_lora'],
          active_count: 2,
          pending_count: 1,
          max_pending_wait_seconds: 120,
        },
        {
          profile: 'scail2',
          label: 'scail2 / 视频生视频',
          supported_task_types: ['scail2_action_transfer', 'scail2_video_replacement'],
          active_count: 0,
          pending_count: 0,
          max_pending_wait_seconds: null,
        },
      ],
    }
    apiMocks.updateRunPodAutoscalerSettings.mockResolvedValueOnce({
      config: {
        paused_profiles: ['img2img'],
        profile_autoscaler_paused_by_profile: {
          img2img: true,
          scail2: false,
        },
        scale_up_wait_seconds_by_profile: {
          img2img: 20 * 60,
          scail2: 40 * 60,
        },
        task_duration_seconds_by_type: {
          img2img: 13,
          img2img_lora: 13,
          scail2_action_transfer: 300,
          scail2_video_replacement: 300,
        },
      },
      decisions: [
        {
          profile: 'img2img',
          action: 'hold',
          reason: 'hold: profile autoscaler paused',
          estimated_clear_time_seconds: 13,
          capacity_status: 'ok',
        },
      ],
    })

    const wrapper = await mountQueueStats()
    await flushPromises()
    const img2imgRow = wrapper
      .findAll('.runpod-profile-detail-table tbody tr')
      .find(row => row.text().includes('img2img / img2img_lora'))

    expect(img2imgRow?.text()).toContain('自动')
    await img2imgRow?.find('.profile-autoscaler-toggle').trigger('click')
    await flushPromises()

    expect(apiMocks.updateRunPodAutoscalerSettings).toHaveBeenCalledWith({
      scale_up_wait_minutes_by_profile: {},
      task_duration_seconds_by_type: {},
      profile_autoscaler_paused_by_profile: {
        img2img: true,
      },
      reason: 'dashboard pause profile autoscaler',
    })

    const refreshedImg2imgRow = wrapper
      .findAll('.runpod-profile-detail-table tbody tr')
      .find(row => row.text().includes('img2img / img2img_lora'))
    const scail2Row = wrapper
      .findAll('.runpod-profile-detail-table tbody tr')
      .find(row => row.text().includes('scail2 / 视频生视频'))

    expect(refreshedImg2imgRow?.text()).toContain('暂停中')
    expect(scail2Row?.text()).toContain('自动')
  })

  it('refreshes autoscaler decisions without resetting draft settings', async () => {
    vi.useFakeTimers()
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      runpod_profile_queue_details: [
        {
          profile: 'img2img',
          label: 'img2img / img2img_lora',
          supported_task_types: ['img2img', 'img2img_lora'],
          active_count: 106,
          pending_count: 102,
          max_pending_wait_seconds: 1149,
        },
      ],
    }
    apiMocks.fetchRunPodAutoscaler
      .mockResolvedValueOnce({
        config: {
          scale_up_wait_seconds_by_profile: {
            img2img: 20 * 60,
          },
          task_duration_seconds_by_type: {
            img2img: 13,
            img2img_lora: 13,
          },
        },
        decisions: [
          {
            profile: 'img2img',
            action: 'hold',
            reason: 'hold: estimated non-low-trust clear time within threshold',
            estimated_clear_time_seconds: 37,
            estimated_non_low_trust_clear_time_seconds: 37,
            non_low_trust_clear_pending_count: 3,
            capacity_status: 'ok',
          },
        ],
      })
      .mockResolvedValueOnce({
        config: {
          scale_up_wait_seconds_by_profile: {
            img2img: 20 * 60,
          },
          task_duration_seconds_by_type: {
            img2img: 13,
            img2img_lora: 13,
          },
        },
        decisions: [
          {
            profile: 'img2img',
            action: 'hold',
            reason: 'hold: estimated non-low-trust clear time within threshold',
            estimated_clear_time_seconds: 361,
            estimated_non_low_trust_clear_time_seconds: 361,
            non_low_trust_clear_pending_count: 28,
            capacity_status: 'ok',
          },
        ],
      })

    const wrapper = await mountQueueStats()
    await flushPromises()
    let row = wrapper
      .findAll('.runpod-profile-detail-table tbody tr')
      .find(item => item.text().includes('img2img / img2img_lora'))

    expect(row?.text()).toContain('37s')
    await row?.find('.scale-threshold-input').setValue('25')

    await vi.advanceTimersByTimeAsync(10000)
    await flushPromises()
    row = wrapper
      .findAll('.runpod-profile-detail-table tbody tr')
      .find(item => item.text().includes('img2img / img2img_lora'))

    expect(apiMocks.fetchRunPodAutoscaler).toHaveBeenCalledTimes(2)
    expect(row?.text()).toContain('6m 1s')
    expect(row?.find('.scale-threshold-input').element.value).toBe('25')
  })

  it('opens runpod create and delete operation logs from the profile card', async () => {
    apiMocks.fetchRunPodOperations.mockResolvedValue({
      operations: [
        {
          id: 'op-add',
          action: 'add',
          profile: 'img2img',
          source: 'autoscaler',
          status: 'succeeded',
          requested_count: 1,
          created_at: '2026-06-24T01:00:00Z',
          trigger_reason:
            'scale_up: estimated non-low-trust clear time 1300s exceeds 1200s',
          log_tail: ['runpod_create_pod_03: ok'],
        },
        {
          id: 'op-delete',
          action: 'delete',
          profile: 'scail2',
          source: 'manual',
          status: 'running',
          slot: '02',
          created_at: '2026-06-24T01:05:00Z',
          log_tail: ['down manual_02'],
        },
        {
          id: 'op-restart',
          action: 'restart',
          profile: 'ltx_video',
          source: 'manual',
          status: 'succeeded',
          created_at: '2026-06-24T01:10:00Z',
        },
      ],
    })

    const wrapper = await mountQueueStats()
    await flushPromises()

    const logButton = wrapper
      .findAll('button')
      .find(button => button.text().includes('日志'))
    expect(logButton).toBeTruthy()
    await logButton?.trigger('click')
    await flushPromises()

    expect(apiMocks.fetchRunPodOperations).toHaveBeenCalled()
    expect(wrapper.text()).toContain('RunPod 创建/删除日志')
    expect(wrapper.text()).toContain('最近 2 条创建/删除记录')
    expect(wrapper.text()).toContain('创建')
    expect(wrapper.text()).toContain('删除')
    expect(wrapper.text()).toContain('img2img')
    expect(wrapper.text()).toContain('scail2')
    expect(wrapper.text()).toContain('自动')
    expect(wrapper.text()).not.toContain('ltx_video')
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

  it('shows locked status for locked RunPod worker cards', async () => {
    queueStatsMocks.workersRef.value = [
      {
        agent_id: 'runpod_prod_wan22_video_v2_manual_03',
        provider: 'runpod',
        types: 'wan22_video_v2',
        status: 'idle',
        runpod_locked: true,
        last_seen: Date.now() / 1000,
      },
    ]

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('已锁定')
    expect(wrapper.text()).toContain('空闲')
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
