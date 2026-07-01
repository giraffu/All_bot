// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchLanAioProfiles: vi.fn(),
  fetchLanAioSlots: vi.fn(),
  fetchRunPodOperations: vi.fn(),
  startLanAioSlotAction: vi.fn(),
}))

const antMocks = vi.hoisted(() => ({
  confirm: vi.fn(options => options.onOk()),
  error: vi.fn(),
  success: vi.fn(),
}))

vi.mock('../api/api', () => apiMocks)

vi.mock('ant-design-vue', () => ({
  message: {
    error: antMocks.error,
    success: antMocks.success,
  },
  Modal: {
    confirm: antMocks.confirm,
  },
}))

import LanAioFleetManager from './LanAioFleetManager.vue'

const profilesPayload = {
  profiles: [
    {
      profile: 'image_to_video',
      runtime_profile: 'image_to_video',
      task_types: ['video_insert', 'video_edit', 'image_to_video'],
      all_in_one_image_ref: '192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:image',
      model_manifest_key: 'lan-aio/image_to_video.json',
      min_vram_gb: 24,
    },
    {
      profile: 'wan22_video_v2',
      runtime_profile: 'wan22_video_v2',
      task_types: ['wan22_video_v2'],
      all_in_one_image_ref: '192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:wan22',
      model_manifest_key: 'lan-aio/wan22_video_v2.json',
      min_vram_gb: 24,
    },
    {
      profile: 'pornmaster_flux2_edit',
      runtime_profile: 'pornmaster_flux2_edit',
      task_types: ['i2i_pro', 't2i-pornmaster-turbo'],
      all_in_one_image_ref: '192.168.1.115:5000/allbot/pornmaster-flux2-edit:aio',
      model_manifest_key: 'lan-aio/pornmaster_flux2_edit.json',
      min_vram_gb: 24,
    },
    {
      profile: 'img2img_lora',
      runtime_profile: 'img2img_lora',
      task_types: ['img2img_lora'],
      all_in_one_image_ref: '192.168.1.115:5000/allbot/img2img-lora:aio',
      model_manifest_key: 'lan-aio/img2img_lora.json',
      min_vram_gb: 24,
    },
  ],
}

const slotsPayload = {
  ok: true,
  groups: [
    {
      physical_slot_key: 'gpu-252:gpu0',
      node_id: 'gpu-252',
      gpu_index: 0,
      slots: [
        {
          slot: {
            id: 'gpu-252-gpu0-pornmaster_flux2_edit',
            enabled: true,
            runtime_current: true,
            phase: 'aio_enabled',
            target_profile_id: 'pornmaster_flux2_edit',
            configured_profile_id: 'pornmaster_flux2_edit',
            configured_task_types: ['i2i_pro', 't2i-pornmaster-turbo'],
            live_runtime_profile: 'pornmaster_flux2_edit',
            live_task_types: ['i2i_pro', 't2i-pornmaster-turbo'],
            live_image_ref: '192.168.1.115:5000/allbot/pornmaster-flux2-edit:aio',
            runtime_drift: false,
            runtime_drift_reasons: [],
            live_state: 'running',
            switch_readiness: 'blocked',
            switch_blockers: ['current_slot'],
            recover_readiness: 'blocked',
            recover_blockers: ['current_slot'],
            recover_prefer: 'old',
            target_container_state: { state: 'running' },
            recovery_status: null,
            retargetable: false,
            replacement_targets: [],
            host_port: 8188,
            agent_id: 'lan_aio_prod_gpu252_gpu0_pornmaster_flux2_edit_01',
            node_id: 'gpu-252',
            gpu_index: 0,
            physical_slot_key: 'gpu-252:gpu0',
            all_in_one_image_ref: '192.168.1.115:5000/allbot/pornmaster-flux2-edit:aio',
            model_manifest_key: 'lan-aio/pornmaster_flux2_edit.json',
            target_task_types: ['i2i_pro', 't2i-pornmaster-turbo'],
          },
          workers: [
            {
              agent_id: 'lan_aio_prod_gpu252_gpu0_pornmaster_flux2_edit_01',
              status: 'idle',
              runtime_profile: 'pornmaster_flux2_edit',
            },
          ],
          control: {
            legacy: 'disabled',
            aio: 'enabled',
          },
          remote_containers: [
            'allbot-lan-aio-gpu252-gpu0-pornmaster-flux2-edit-prod Up 2 minutes',
          ],
          model_cache: {
            status: 'ready',
            synced_at: '2026-06-29T01:02:03Z',
            model_manifest_key: 'lan-aio/pornmaster_flux2_edit.json',
          },
        },
        {
          slot: {
            id: 'gpu-252-gpu0-img2img_lora',
            enabled: false,
            runtime_current: false,
            phase: 'candidate',
            target_profile_id: 'img2img_lora',
            configured_profile_id: 'img2img_lora',
            configured_task_types: ['img2img_lora'],
            live_runtime_profile: null,
            live_task_types: [],
            live_image_ref: null,
            runtime_drift: false,
            runtime_drift_reasons: [],
            live_state: 'missing',
            switch_readiness: 'warning',
            switch_blockers: ['model_cache_missing'],
            recover_readiness: 'blocked',
            recover_blockers: ['physical_slot_has_active_runtime'],
            recover_prefer: 'candidate',
            target_container_state: { state: 'missing' },
            recovery_status: null,
            retargetable: true,
            replacement_targets: [
              {
                slot_id: 'gpu-252-gpu0-pornmaster_flux2_edit',
                physical_slot_key: 'gpu-252:gpu0',
                node_id: 'gpu-252',
                gpu_index: 0,
                host_port: 8188,
                live_runtime_profile: 'pornmaster_flux2_edit',
                configured_profile_id: 'pornmaster_flux2_edit',
                selectable: true,
                disabled_reason: null,
              },
            ],
            host_port: 8190,
            agent_id: 'lan_aio_prod_gpu252_gpu0_img2img_lora_01',
            node_id: 'gpu-252',
            gpu_index: 0,
            physical_slot_key: 'gpu-252:gpu0',
            all_in_one_image_ref: '192.168.1.115:5000/allbot/img2img-lora:aio',
            model_manifest_key: 'lan-aio/img2img_lora.json',
            target_task_types: ['img2img_lora'],
          },
          workers: [],
          control: {
            legacy: 'unknown',
            aio: 'unknown',
          },
          remote_containers: [],
          model_cache: {
            status: 'missing',
          },
        },
      ],
    },
  ],
}

const operationsPayload = {
  operations: [
    {
      id: 'lan-op-1',
      action: 'lan-aio-warm-cache',
      profile: 'pornmaster_flux2_edit',
      slot: 'gpu-252-gpu0-pornmaster_flux2_edit',
      active_lan_aio_slot: 'gpu-252:gpu0',
      status: 'succeeded',
      trigger_reason: 'dashboard lan aio warm-cache',
      created_at: '2026-06-29T01:03:00Z',
    },
    {
      id: 'runpod-op-1',
      action: 'add',
      profile: 'img2img',
      status: 'succeeded',
      trigger_reason: 'filtered runpod add',
    },
  ],
}

const ButtonStub = defineComponent({
  name: 'ButtonStub',
  props: ['danger', 'disabled', 'loading', 'type', 'size'],
  emits: ['click'],
  template: `
    <button
      type="button"
      :disabled="disabled"
      :data-danger="String(!!danger)"
      @click="$emit('click', $event)"
    >
      <slot name="icon" />
      <slot />
    </button>
  `,
})

const ModalStub = defineComponent({
  name: 'ModalStub',
  props: ['open'],
  template: '<div v-if="open"><slot /></div>',
})

const TooltipStub = defineComponent({
  name: 'TooltipStub',
  props: ['title'],
  template: '<span :title="title"><slot /></span>',
})

const slotStub = (name: string) => defineComponent({
  name,
  props: ['color'],
  template: '<span><slot name="icon" /><slot /></span>',
})

const mountLanAioFleetManager = () =>
  mount(LanAioFleetManager, {
    global: {
      stubs: {
        'a-button': ButtonStub,
        'a-modal': ModalStub,
        'a-tag': slotStub('TagStub'),
        'a-tooltip': TooltipStub,
        DownOutlined: slotStub('DownOutlinedStub'),
        ReloadOutlined: slotStub('ReloadOutlinedStub'),
        RightOutlined: slotStub('RightOutlinedStub'),
        RocketOutlined: slotStub('RocketOutlinedStub'),
        SafetyCertificateOutlined: slotStub('SafetyCertificateOutlinedStub'),
        SyncOutlined: slotStub('SyncOutlinedStub'),
      },
    },
  })

describe('LanAioFleetManager', () => {
  beforeEach(() => {
    Object.values(apiMocks).forEach(mock => mock.mockClear())
    Object.values(antMocks).forEach(mock => mock.mockClear())
    apiMocks.fetchLanAioProfiles.mockResolvedValue(profilesPayload)
    apiMocks.fetchLanAioSlots.mockResolvedValue(slotsPayload)
    apiMocks.fetchRunPodOperations.mockResolvedValue(operationsPayload)
    apiMocks.startLanAioSlotAction.mockResolvedValue({ status: 'accepted' })
  })

  it('renders configured current and disabled candidate LAN AIO slots', async () => {
    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(apiMocks.fetchLanAioSlots).toHaveBeenCalledWith(true)
    expect(wrapper.text()).toContain('LAN AIO 管理')
    expect(wrapper.text()).toContain('gpu-252:gpu0')
    expect(wrapper.text()).toContain('gpu-252-gpu0-pornmaster_flux2_edit')
    expect(wrapper.text()).toContain('gpu-252-gpu0-img2img_lora')
    expect(wrapper.text()).toContain('当前')
    expect(wrapper.text()).toContain('候选')
    expect(wrapper.text()).toContain('ready')
    expect(wrapper.text()).toContain('missing')
    expect(wrapper.text()).toContain('一键切换')
    expect(wrapper.text()).not.toContain('预检')
    expect(wrapper.text()).not.toContain('预热模型')
    expect(wrapper.text()).not.toContain('启用接单')
  })

  it('groups physical GPUs under collapsible GPU node panels', async () => {
    const multiNodePayload = JSON.parse(JSON.stringify(slotsPayload))
    const secondNodeGroup = JSON.parse(JSON.stringify(slotsPayload.groups[0]))
    secondNodeGroup.physical_slot_key = 'gpu-177:gpu1'
    secondNodeGroup.node_id = 'gpu-177'
    secondNodeGroup.gpu_index = 1
    secondNodeGroup.slots[0].slot.id = 'gpu-177-gpu1-ltx_video'
    secondNodeGroup.slots[0].slot.node_id = 'gpu-177'
    secondNodeGroup.slots[0].slot.gpu_index = 1
    secondNodeGroup.slots[0].slot.physical_slot_key = 'gpu-177:gpu1'
    secondNodeGroup.slots[0].slot.target_profile_id = 'ltx_video'
    secondNodeGroup.slots[1].slot.id = 'gpu-177-gpu1-wan22_video_v2'
    secondNodeGroup.slots[1].slot.node_id = 'gpu-177'
    secondNodeGroup.slots[1].slot.gpu_index = 1
    secondNodeGroup.slots[1].slot.physical_slot_key = 'gpu-177:gpu1'
    secondNodeGroup.slots[1].slot.target_profile_id = 'wan22_video_v2'
    multiNodePayload.groups.push(secondNodeGroup)
    apiMocks.fetchLanAioSlots.mockResolvedValue(multiNodePayload)

    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('GPU 节点 2')
    expect(wrapper.text()).toContain('物理 GPU 2')

    const headers = wrapper.findAll('.node-panel-header')
    expect(headers).toHaveLength(2)
    expect(headers[0].text()).toContain('gpu-252')
    expect(headers[0].text()).toContain('gpu0')
    expect(headers[1].text()).toContain('gpu-177')
    expect(headers[1].text()).toContain('gpu1')

    const bodies = wrapper.findAll('.node-panel-body')
    expect(bodies[0].attributes('style') || '').not.toContain('display: none')
    expect(bodies[1].attributes('style') || '').toContain('display: none')

    await headers[1].trigger('click')
    await flushPromises()

    expect(bodies[1].attributes('style') || '').not.toContain('display: none')
  })

  it('prefers runtime current over the static enabled flag', async () => {
    const runtimePayload = JSON.parse(JSON.stringify(slotsPayload))
    runtimePayload.groups[0].active_slot_id = 'gpu-252-gpu0-img2img_lora'
    runtimePayload.groups[0].active_slot_source = 'runtime'
    runtimePayload.groups[0].slots[0].slot.runtime_current = false
    runtimePayload.groups[0].slots[1].slot.runtime_current = true
    apiMocks.fetchLanAioSlots.mockResolvedValue(runtimePayload)

    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    const configuredRow = rows.find(row =>
      row.text().includes('gpu-252-gpu0-pornmaster_flux2_edit')
    )
    const runtimeRow = rows.find(row =>
      row.text().includes('gpu-252-gpu0-img2img_lora')
    )

    expect(configuredRow?.text()).toContain('候选')
    expect(runtimeRow?.text()).toContain('当前')
  })

  it('shows maintenance disabled slots without live runtime as stopped', async () => {
    const maintenancePayload = JSON.parse(JSON.stringify(slotsPayload))
    maintenancePayload.groups.push({
      physical_slot_key: 'gpu-252:gpu1',
      active_slot_id: null,
      active_slot_source: 'none',
      node_id: 'gpu-252',
      gpu_index: 1,
      slots: [
        {
          slot: {
            id: 'gpu-252-gpu1-wan22_video_v2',
            enabled: true,
            runtime_current: false,
            phase: 'maintenance_disabled',
            target_profile_id: 'wan22_video_v2',
            configured_profile_id: 'wan22_video_v2',
            configured_task_types: ['wan22_video_v2'],
            live_runtime_profile: null,
            live_task_types: [],
            live_image_ref: null,
            runtime_drift: false,
            runtime_drift_reasons: [],
            live_state: 'missing',
            switch_readiness: 'blocked',
            switch_blockers: ['maintenance_disabled', 'missing_live_runtime'],
            target_container_state: { state: 'missing' },
            recovery_status: null,
            retargetable: false,
            replacement_targets: [],
            host_port: 8191,
            agent_id: 'lan_aio_prod_gpu252_gpu1_wan22_video_v2_01',
            node_id: 'gpu-252',
            gpu_index: 1,
            physical_slot_key: 'gpu-252:gpu1',
            all_in_one_image_ref: '192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:wan22',
            model_manifest_key: 'lan-aio/wan22_video_v2.json',
            target_task_types: ['wan22_video_v2'],
          },
          workers: [],
          control: {
            legacy: 'disabled',
            aio: 'enabled',
          },
          remote_containers: [],
          model_cache: {
            status: 'unavailable',
          },
        },
      ],
    })
    apiMocks.fetchLanAioSlots.mockResolvedValue(maintenancePayload)

    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const maintenanceRow = wrapper.findAll('tbody tr').find(row =>
      row.text().includes('gpu-252-gpu1-wan22_video_v2')
    )
    const headers = wrapper.findAll('.node-panel-header')
    const gpu252Header = headers.find(header => header.text().includes('gpu-252'))
    const takeoverButtons = wrapper
      .findAll('button')
      .filter(button => button.text().includes('一键切换'))

    expect(maintenanceRow?.text()).toContain('停用')
    expect(maintenanceRow?.text()).not.toContain('当前')
    expect(gpu252Header?.text()).toContain('当前 1')
    expect(gpu252Header?.text()).toContain('候选 2')
    expect(takeoverButtons[2].attributes('disabled')).toBeDefined()
    expect(
      maintenanceRow?.find(
        'span[title*="maintenance disabled"]'
      ).exists()
    ).toBe(true)
  })

  it('exposes guarded takeover and recover actions for slots', async () => {
    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const slotRows = wrapper.findAll('tbody tr').filter(row =>
      row.text().includes('gpu-252-gpu0-')
    )
    expect(slotRows).toHaveLength(2)
    slotRows.forEach(row => {
      expect(row.text()).toContain('一键切换')
      expect(row.text()).toContain('恢复此 AIO')
      expect(row.text()).not.toContain('预热模型')
      expect(row.text()).not.toContain('启用接单')
    })

    const warmCacheButton = wrapper
      .findAll('button')
      .find(button => button.text().includes('预热模型'))
    expect(warmCacheButton).toBeUndefined()
  })

  it('submits a guarded takeover action for one slot', async () => {
    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const takeoverButtons = wrapper
      .findAll('button')
      .filter(button => button.text().includes('一键切换'))
    expect(takeoverButtons).toHaveLength(2)
    expect(takeoverButtons[0].attributes('disabled')).toBeDefined()
    expect(takeoverButtons[1].attributes('disabled')).toBeUndefined()

    await takeoverButtons[1].trigger('click')
    await flushPromises()

    expect(antMocks.confirm).toHaveBeenCalled()
    expect(antMocks.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        zIndex: 1800,
        centered: true,
        width: 480,
        getContainer: expect.any(Function),
      })
    )
    expect(apiMocks.startLanAioSlotAction).toHaveBeenCalledWith(
      'gpu-252-gpu0-img2img_lora',
      'takeover',
      {
        failure_policy: 'auto_rollback',
        reason: 'dashboard lan aio takeover',
        replacement_target_slot_id: 'gpu-252-gpu0-pornmaster_flux2_edit',
      }
    )
  })

  it('defaults retarget takeover to the current slot on the same physical GPU', async () => {
    const gpu177Payload = JSON.parse(JSON.stringify(slotsPayload))
    gpu177Payload.groups = [
      {
        physical_slot_key: 'gpu-177:gpu1',
        node_id: 'gpu-177',
        gpu_index: 1,
        active_slot_id: 'gpu-177-gpu1-ltx_video',
        active_slot_source: 'runtime',
        slots: [
          {
            slot: {
              ...gpu177Payload.groups[0].slots[0].slot,
              id: 'gpu-177-gpu1-ltx_video',
              target_profile_id: 'ltx_video',
              configured_profile_id: 'ltx_video',
              configured_task_types: ['ltx_video'],
              live_runtime_profile: 'ltx_video',
              live_task_types: ['ltx_video'],
              runtime_current: true,
              live_state: 'running',
              switch_readiness: 'blocked',
              switch_blockers: ['current_slot'],
              retargetable: false,
              replacement_targets: [],
              host_port: 8191,
              node_id: 'gpu-177',
              gpu_index: 1,
              physical_slot_key: 'gpu-177:gpu1',
            },
            workers: [
              {
                agent_id: 'lan_aio_prod_gpu177_gpu1_ltx_video_01',
                status: 'idle',
                runtime_profile: 'ltx_video',
              },
            ],
            control: { legacy: 'disabled', aio: 'enabled' },
            remote_containers: [
              'allbot-lan-aio-gpu-177-gpu1-ltx_video-prod Up 8 days',
            ],
            model_cache: { status: 'ready' },
          },
          {
            slot: {
              ...gpu177Payload.groups[0].slots[1].slot,
              id: 'gpu-177-gpu1-wan22_video_v2',
              target_profile_id: 'wan22_video_v2',
              configured_profile_id: 'wan22_video_v2',
              configured_task_types: ['wan22_video_v2'],
              live_runtime_profile: null,
              live_task_types: [],
              runtime_current: false,
              live_state: 'missing',
              switch_readiness: 'warning',
              switch_blockers: ['model_cache_missing'],
              retargetable: true,
              replacement_targets: [
                {
                  slot_id: 'gpu-177-gpu0-image_to_video',
                  physical_slot_key: 'gpu-177:gpu0',
                  node_id: 'gpu-177',
                  gpu_index: 0,
                  host_port: 8190,
                  live_runtime_profile: 'image_to_video',
                  configured_profile_id: 'image_to_video',
                  selectable: true,
                  disabled_reason: null,
                },
                {
                  slot_id: 'gpu-177-gpu1-ltx_video',
                  physical_slot_key: 'gpu-177:gpu1',
                  node_id: 'gpu-177',
                  gpu_index: 1,
                  host_port: 8191,
                  live_runtime_profile: 'ltx_video',
                  configured_profile_id: 'ltx_video',
                  selectable: true,
                  disabled_reason: null,
                },
              ],
              host_port: 8191,
              node_id: 'gpu-177',
              gpu_index: 1,
              physical_slot_key: 'gpu-177:gpu1',
            },
            workers: [],
            control: { legacy: 'enabled', aio: 'enabled' },
            remote_containers: [],
            model_cache: { status: 'missing' },
          },
        ],
      },
    ]
    apiMocks.fetchLanAioSlots.mockResolvedValue(gpu177Payload)

    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const candidateRow = wrapper.findAll('tbody tr').find(row =>
      row.text().includes('gpu-177-gpu1-wan22_video_v2')
    )
    const takeoverButton = candidateRow
      ?.findAll('button')
      .find(button => button.text().includes('一键切换'))

    await takeoverButton?.trigger('click')
    await flushPromises()

    expect(apiMocks.startLanAioSlotAction).toHaveBeenCalledWith(
      'gpu-177-gpu1-wan22_video_v2',
      'takeover',
      {
        failure_policy: 'auto_rollback',
        reason: 'dashboard lan aio takeover',
        replacement_target_slot_id: 'gpu-177-gpu1-ltx_video',
      }
    )
  })

  it('enables recovery for an idle physical GPU after local inspection', async () => {
    const recoverPayload = JSON.parse(JSON.stringify(slotsPayload))
    recoverPayload.groups[0].active_slot_id = null
    recoverPayload.groups[0].active_slot_source = 'none'
    recoverPayload.groups[0].recoverable_slot_ids = [
      'gpu-252-gpu0-pornmaster_flux2_edit',
      'gpu-252-gpu0-img2img_lora',
    ]
    recoverPayload.groups[0].recoverable_count = 2
    recoverPayload.groups[0].slots[0].slot.runtime_current = false
    recoverPayload.groups[0].slots[0].slot.live_runtime_profile = null
    recoverPayload.groups[0].slots[0].slot.live_state = 'stopped'
    recoverPayload.groups[0].slots[0].slot.switch_readiness = 'blocked'
    recoverPayload.groups[0].slots[0].slot.switch_blockers = ['missing_live_runtime']
    recoverPayload.groups[0].slots[0].slot.recover_readiness = 'warning'
    recoverPayload.groups[0].slots[0].slot.recover_blockers = [
      'stale_target_container',
      'control_enabled_without_live_runtime',
    ]
    recoverPayload.groups[0].slots[0].slot.recover_prefer = 'old'
    recoverPayload.groups[0].slots[1].slot.recover_readiness = 'warning'
    recoverPayload.groups[0].slots[1].slot.recover_blockers = ['target_container_missing']
    recoverPayload.groups[0].slots[1].slot.recover_prefer = 'candidate'
    apiMocks.fetchLanAioSlots.mockResolvedValue(recoverPayload)

    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('可恢复 2')

    const candidateRow = wrapper.findAll('tbody tr').find(row =>
      row.text().includes('gpu-252-gpu0-img2img_lora')
    )
    const recoverButton = candidateRow
      ?.findAll('button')
      .find(button => button.text().includes('恢复此 AIO'))
    expect(recoverButton?.attributes('disabled')).toBeUndefined()

    await recoverButton?.trigger('click')
    await flushPromises()

    expect(apiMocks.startLanAioSlotAction).toHaveBeenCalledWith(
      'gpu-252-gpu0-img2img_lora',
      'recover',
      {
        failure_policy: 'auto_rollback',
        reason: 'dashboard lan aio recover',
      }
    )
  })

  it('shows switch readiness warnings and auto rollback policy before takeover', async () => {
    const warningPayload = JSON.parse(JSON.stringify(slotsPayload))
    const candidate = warningPayload.groups[0].slots[1].slot
    candidate.switch_readiness = 'warning'
    candidate.switch_blockers = ['stale_target_container', 'model_cache_missing']
    candidate.target_container_state = {
      state: 'exited',
      summary: 'allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod Exited (1)',
    }
    apiMocks.fetchLanAioSlots.mockResolvedValue(warningPayload)

    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const candidateRow = wrapper.findAll('tbody tr').find(row =>
      row.text().includes('gpu-252-gpu0-img2img_lora')
    )
    expect(candidateRow?.text()).toContain('需确认')
    expect(candidateRow?.text()).toContain('stale target container')
    expect(candidateRow?.text()).toContain('model cache missing')

    const takeoverButtons = wrapper
      .findAll('button')
      .filter(button => button.text().includes('一键切换'))
    expect(takeoverButtons[1].attributes('disabled')).toBeUndefined()

    await takeoverButtons[1].trigger('click')
    await flushPromises()

    expect(antMocks.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        content: expect.any(Object),
      })
    )
    expect(apiMocks.startLanAioSlotAction).toHaveBeenCalledWith(
      'gpu-252-gpu0-img2img_lora',
      'takeover',
      expect.objectContaining({
        failure_policy: 'auto_rollback',
      })
    )
  })

  it('shows live runtime before configured target when a slot drifts', async () => {
    const driftPayload = JSON.parse(JSON.stringify(slotsPayload))
    const currentSlot = driftPayload.groups[0].slots[0].slot
    currentSlot.id = 'gpu-177-gpu0-image_to_video'
    currentSlot.target_profile_id = 'wan22_video_v2'
    currentSlot.configured_profile_id = 'wan22_video_v2'
    currentSlot.configured_task_types = ['wan22_video_v2']
    currentSlot.live_runtime_profile = 'image_to_video'
    currentSlot.live_task_types = ['image_to_video']
    currentSlot.live_image_ref = '192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:image'
    currentSlot.runtime_drift = true
    currentSlot.runtime_drift_reasons = ['profile', 'task_types']
    apiMocks.fetchLanAioSlots.mockResolvedValue(driftPayload)

    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const driftRow = wrapper.findAll('tbody tr').find(row =>
      row.text().includes('gpu-177-gpu0-image_to_video')
    )

    expect(driftRow?.text()).toContain('image_to_video')
    expect(driftRow?.text()).toContain('配置 wan22_video_v2')
    expect(driftRow?.text()).toContain('类型漂移')
    expect(driftRow?.text()).toContain('192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:image')
  })

  it('disables retarget takeover when same-node targets are the same live profile', async () => {
    const sameProfilePayload = JSON.parse(JSON.stringify(slotsPayload))
    const candidate = sameProfilePayload.groups[0].slots[1].slot
    candidate.target_profile_id = 'pornmaster_flux2_edit'
    candidate.configured_profile_id = 'pornmaster_flux2_edit'
    candidate.replacement_targets = [
      {
        slot_id: 'gpu-252-gpu0-pornmaster_flux2_edit',
        physical_slot_key: 'gpu-252:gpu0',
        node_id: 'gpu-252',
        gpu_index: 0,
        host_port: 8188,
        live_runtime_profile: 'pornmaster_flux2_edit',
        configured_profile_id: 'pornmaster_flux2_edit',
        selectable: false,
        disabled_reason: 'same_profile',
      },
    ]
    apiMocks.fetchLanAioSlots.mockResolvedValue(sameProfilePayload)

    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const takeoverButtons = wrapper
      .findAll('button')
      .filter(button => button.text().includes('一键切换'))

    expect(takeoverButtons[1].attributes('disabled')).toBeDefined()
    expect(apiMocks.startLanAioSlotAction).not.toHaveBeenCalled()
  })

  it('allows takeover for an inactive configured slot when its sibling is live', async () => {
    const driftedPayload = JSON.parse(JSON.stringify(slotsPayload))
    const pornmaster = driftedPayload.groups[0].slots[0]
    const img2img = driftedPayload.groups[0].slots[1]

    driftedPayload.groups[0].active_slot_id = 'gpu-252-gpu0-img2img_lora'
    pornmaster.slot.runtime_current = false
    pornmaster.slot.live_runtime_profile = null
    pornmaster.slot.live_task_types = []
    pornmaster.slot.live_state = 'stopped'
    pornmaster.slot.switch_readiness = 'warning'
    pornmaster.slot.switch_blockers = [
      'missing_live_runtime',
      'control_enabled_without_live_runtime',
      'stale_target_container',
      'model_cache_missing',
    ]
    pornmaster.slot.target_container_state = { state: 'exited' }
    pornmaster.workers = []
    pornmaster.remote_containers = [
      'allbot-lan-aio-gpu-252-gpu0-pornmaster-flux2-edit-prod Exited (143)',
    ]
    pornmaster.model_cache = { status: 'missing' }

    img2img.slot.runtime_current = true
    img2img.slot.enabled = false
    img2img.slot.phase = 'superseded_by_pornmaster_flux2_edit'
    img2img.slot.live_runtime_profile = 'img2img_lora'
    img2img.slot.live_state = 'running'
    img2img.slot.switch_readiness = 'blocked'
    img2img.slot.switch_blockers = ['current_slot']
    img2img.workers = [
      {
        agent_id: 'lan_aio_prod_gpu252_gpu0_img2img_lora_01',
        status: 'idle',
        runtime_profile: 'img2img_lora',
      },
    ]
    apiMocks.fetchLanAioSlots.mockResolvedValue(driftedPayload)

    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const pornmasterRow = wrapper.findAll('tbody tr').find(row =>
      row.text().includes('gpu-252-gpu0-pornmaster_flux2_edit')
    )
    expect(pornmasterRow?.text()).toContain('需确认')
    expect(pornmasterRow?.text()).toContain('missing live runtime')

    const takeoverButton = pornmasterRow
      ?.findAll('button')
      .find(button => button.text().includes('一键切换'))
    expect(takeoverButton?.attributes('disabled')).toBeUndefined()

    await takeoverButton?.trigger('click')
    await flushPromises()

    expect(apiMocks.startLanAioSlotAction).toHaveBeenCalledWith(
      'gpu-252-gpu0-pornmaster_flux2_edit',
      'takeover',
      {
        failure_policy: 'auto_rollback',
        reason: 'dashboard lan aio takeover',
      }
    )
  })

  it('shows recent LAN AIO operations and filters regular RunPod operations', async () => {
    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('lan-aio-warm-cache')
    expect(wrapper.text()).toContain('dashboard lan aio warm-cache')
    expect(wrapper.text()).not.toContain('filtered runpod add')
  })
})
