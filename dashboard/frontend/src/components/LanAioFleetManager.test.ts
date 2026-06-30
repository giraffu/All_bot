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
        ReloadOutlined: slotStub('ReloadOutlinedStub'),
        RocketOutlined: slotStub('RocketOutlinedStub'),
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

  it('only exposes the guarded takeover action for slots', async () => {
    const wrapper = mountLanAioFleetManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const slotRows = wrapper.findAll('tbody tr').filter(row =>
      row.text().includes('gpu-252-gpu0-')
    )
    expect(slotRows).toHaveLength(2)
    slotRows.forEach(row => {
      expect(row.text()).toContain('一键切换')
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
      { reason: 'dashboard lan aio takeover' }
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
