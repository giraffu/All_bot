// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  deleteRunPodWorker: vi.fn().mockResolvedValue({ status: 'accepted' }),
  enableLanAioWorker: vi.fn().mockResolvedValue({ status: 'accepted' }),
  enableRunPodWorker: vi.fn().mockResolvedValue({ status: 'accepted' }),
  lockRunPodWorker: vi.fn().mockResolvedValue({ status: 'locked' }),
  pauseLanAioWorker: vi.fn().mockResolvedValue({ status: 'accepted' }),
  pauseRunPodWorker: vi.fn().mockResolvedValue({ status: 'accepted' }),
  restartLanAioWorker: vi.fn().mockResolvedValue({ status: 'accepted' }),
  restartRunPodWorker: vi.fn().mockResolvedValue({ status: 'accepted' }),
  unlockRunPodWorker: vi.fn().mockResolvedValue({ status: 'unlocked' }),
}))

const antMocks = vi.hoisted(() => ({
  confirm: vi.fn(options => options.onOk()),
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('../api/api', () => apiMocks)

vi.mock('ant-design-vue', () => ({
  message: {
    error: antMocks.error,
    success: antMocks.success,
    warning: antMocks.warning,
  },
  Modal: {
    confirm: antMocks.confirm,
  },
}))

vi.mock('ant-design-vue/es/message', () => ({
  default: {
    error: antMocks.error,
    success: antMocks.success,
    warning: antMocks.warning,
  },
}))

vi.mock('ant-design-vue/es/modal', () => ({
  default: {
    confirm: antMocks.confirm,
  },
}))

import RunPodWorkerActions from './RunPodWorkerActions.vue'

const ButtonStub = defineComponent({
  name: 'ButtonStub',
  props: ['danger', 'disabled', 'loading', 'type', 'size'],
  emits: ['click'],
  template: `
    <button type="button" :disabled="disabled" :data-danger="String(!!danger)" @click="$emit('click', $event)">
      <slot name="icon" />
      <slot />
    </button>
  `,
})

const iconStub = name => defineComponent({
  name,
  template: '<span />',
})

const mountActions = worker =>
  mount(RunPodWorkerActions, {
    props: { worker },
    global: {
      stubs: {
        'a-button': ButtonStub,
        DeleteOutlined: iconStub('DeleteOutlinedStub'),
        LockOutlined: iconStub('LockOutlinedStub'),
        PauseCircleOutlined: iconStub('PauseCircleOutlinedStub'),
        PlayCircleOutlined: iconStub('PlayCircleOutlinedStub'),
        ReloadOutlined: iconStub('ReloadOutlinedStub'),
        UnlockOutlined: iconStub('UnlockOutlinedStub'),
      },
    },
  })

describe('RunPodWorkerActions', () => {
  beforeEach(() => {
    Object.values(apiMocks).forEach(mock => mock.mockClear())
    Object.values(antMocks).forEach(mock => mock.mockClear())
  })

  it('shows pause and restart for LAN AIO workers without RunPod delete', async () => {
    const agentId = 'lan_aio_prod_gpu177_gpu0_image_to_video_01'
    const wrapper = mountActions({
      agent_id: agentId,
      provider: 'lan_ssh',
      pool_managed: true,
      status: 'idle',
    })

    expect(wrapper.text()).toContain('暂停')
    expect(wrapper.text()).toContain('重启')
    expect(wrapper.text()).not.toContain('删除')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(apiMocks.pauseLanAioWorker).toHaveBeenCalledWith(agentId)
  })

  it('turns the control button into enable for paused RunPod workers', async () => {
    const agentId = 'runpod_prod_wan22_video_v2_manual_03'
    const wrapper = mountActions({
      agent_id: agentId,
      control_state: 'disabled',
      status: 'idle',
    })

    expect(wrapper.text()).toContain('开启')
    expect(wrapper.text()).toContain('删除')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(apiMocks.enableRunPodWorker).toHaveBeenCalledWith(agentId)
  })

  it('shows RunPod lifecycle actions for PornMaster Flux2 workers', async () => {
    const agentId = 'runpod_prod_pornmaster_flux2_edit_manual_01'
    const wrapper = mountActions({
      agent_id: agentId,
      status: 'idle',
    })

    expect(wrapper.text()).toContain('暂停')
    expect(wrapper.text()).toContain('重启')
    expect(wrapper.text()).toContain('锁定')
    expect(wrapper.text()).toContain('删除')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(apiMocks.pauseRunPodWorker).toHaveBeenCalledWith(agentId)
    expect(apiMocks.pauseLanAioWorker).not.toHaveBeenCalled()
  })

  it('shows RunPod lifecycle actions for PornMaster Flux2 BF16 workers', async () => {
    const agentId = 'runpod_prod_pornmaster_flux2_edit_bf16_manual_01'
    const wrapper = mountActions({
      agent_id: agentId,
      status: 'idle',
    })

    expect(wrapper.text()).toContain('暂停')
    expect(wrapper.text()).toContain('重启')
    expect(wrapper.text()).toContain('锁定')
    expect(wrapper.text()).toContain('删除')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(apiMocks.pauseRunPodWorker).toHaveBeenCalledWith(agentId)
    expect(apiMocks.pauseLanAioWorker).not.toHaveBeenCalled()
  })

  it('locks RunPod workers from the card action', async () => {
    const agentId = 'runpod_prod_wan22_video_v2_manual_03'
    const wrapper = mountActions({
      agent_id: agentId,
      status: 'idle',
    })

    const lockButton = wrapper.findAll('button').find(button => button.text().includes('锁定'))
    expect(lockButton).toBeTruthy()
    expect(wrapper.text()).toContain('删除')

    await lockButton.trigger('click')
    await flushPromises()

    expect(apiMocks.lockRunPodWorker).toHaveBeenCalledWith(agentId, {
      reason: 'dashboard lock runpod worker',
    })
    expect(antMocks.success).toHaveBeenCalledWith('已锁定 RunPod Worker')
  })

  it('shows unlock and disables delete for locked RunPod workers', async () => {
    const agentId = 'runpod_prod_wan22_video_v2_manual_03'
    const wrapper = mountActions({
      agent_id: agentId,
      runpod_locked: true,
      status: 'idle',
    })

    expect(wrapper.text()).toContain('解锁')
    const deleteButton = wrapper.findAll('button').find(button => button.text().includes('删除'))
    expect(deleteButton.attributes('disabled')).toBeDefined()

    const unlockButton = wrapper.findAll('button').find(button => button.text().includes('解锁'))
    await unlockButton.trigger('click')
    await flushPromises()

    expect(apiMocks.unlockRunPodWorker).toHaveBeenCalledWith(agentId, {
      reason: 'dashboard unlock runpod worker',
    })
    expect(apiMocks.deleteRunPodWorker).not.toHaveBeenCalled()
  })

  it('treats draining LAN AIO workers as paused and enables them on click', async () => {
    const agentId = 'lan_aio_prod_gpu177_gpu0_image_to_video_01'
    const wrapper = mountActions({
      agent_id: agentId,
      control_state: 'draining',
      provider: 'lan_ssh',
      pool_managed: true,
      status: 'running',
    })

    expect(wrapper.text()).toContain('开启')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(apiMocks.enableLanAioWorker).toHaveBeenCalledWith(agentId)
  })
})
