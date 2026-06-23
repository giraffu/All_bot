// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WorkerHistoryModal from './WorkerHistoryModal.vue'

const fetchWorkerHistoryMock = vi.hoisted(() => vi.fn())
const messageErrorMock = vi.hoisted(() => vi.fn())

vi.mock('../api/api', () => ({
  fetchWorkerHistory: fetchWorkerHistoryMock,
}))

vi.mock('ant-design-vue', () => ({
  message: {
    error: messageErrorMock,
  },
}))

const ModalStub = defineComponent({
  name: 'AModalStub',
  props: ['open'],
  emits: ['cancel'],
  template: `
    <section v-if="open" class="modal-stub">
      <div class="modal-title"><slot name="title" /></div>
      <slot />
      <button class="modal-close" @click="$emit('cancel')">close</button>
    </section>
  `,
})

const ButtonStub = defineComponent({
  name: 'AButtonStub',
  emits: ['click'],
  template: '<button class="button-stub" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
})

const TableStub = defineComponent({
  name: 'ATableStub',
  props: ['columns', 'dataSource', 'loading', 'pagination'],
  emits: ['change'],
  template: `
    <div class="table-stub">
      <div class="table-loading">{{ loading ? 'loading' : 'idle' }}</div>
      <div class="table-page-size">{{ pagination && pagination.pageSize }}</div>
      <div v-for="column in columns" :key="column.key" class="table-column">{{ column.title }}</div>
      <div v-for="record in dataSource" :key="record.id" class="history-row">
        <span>{{ record.worker_id }}</span>
        <span>{{ record.task_id }}</span>
        <span>{{ record.task_type }}</span>
        <span>{{ record.status }}</span>
        <span>{{ record.error_message || '-' }}</span>
      </div>
      <button class="table-page-2" @click="$emit('change', { current: 2, pageSize: 20 })">page 2</button>
    </div>
  `,
})

const TagStub = defineComponent({
  name: 'ATagStub',
  template: '<span class="tag-stub"><slot /></span>',
})

const mountModal = (props = {}) =>
  mount(WorkerHistoryModal, {
    props: {
      open: false,
      workerId: 'worker-1',
      ...props,
    },
    global: {
      stubs: {
        'a-modal': ModalStub,
        'a-button': ButtonStub,
        'a-table': TableStub,
        'a-tag': TagStub,
        SyncOutlined: defineComponent({ template: '<span />' }),
      },
    },
  })

describe('WorkerHistoryModal', () => {
  beforeEach(() => {
    fetchWorkerHistoryMock.mockReset()
    messageErrorMock.mockReset()
  })

  it('does not fetch worker history while closed', async () => {
    mountModal({ open: false, workerId: 'worker-1' })

    await flushPromises()

    expect(fetchWorkerHistoryMock).not.toHaveBeenCalled()
  })

  it('fetches the selected worker history when opened', async () => {
    fetchWorkerHistoryMock.mockResolvedValueOnce({
      total: 1,
      data: [
        {
          id: 1,
          worker_id: 'worker-1',
          task_id: 'task-1',
          task_type: 'img2img',
          status: 'success',
          start_time: '2026-06-22T02:27:57',
          end_time: '2026-06-22T02:28:12',
          duration: 15,
          error_message: null,
        },
      ],
    })

    const wrapper = mountModal({ open: true, workerId: 'worker-1' })

    await flushPromises()

    expect(fetchWorkerHistoryMock).toHaveBeenCalledTimes(1)
    expect(fetchWorkerHistoryMock).toHaveBeenCalledWith({
      workerId: 'worker-1',
      page: 1,
      size: 10,
    })
    expect(wrapper.text()).toContain('worker-1')
    expect(wrapper.text()).toContain('task-1')
    expect(wrapper.text()).toContain('img2img')
    expect(wrapper.text()).toContain('完成时间')
    expect(wrapper.text()).toContain('链路耗时')
  })

  it('refetches with the current worker when pagination changes', async () => {
    fetchWorkerHistoryMock.mockResolvedValue({
      total: 30,
      data: [],
    })

    const wrapper = mountModal({ open: true, workerId: 'worker-2' })

    await flushPromises()
    await wrapper.get('.table-page-2').trigger('click')
    await flushPromises()

    expect(fetchWorkerHistoryMock).toHaveBeenLastCalledWith({
      workerId: 'worker-2',
      page: 2,
      size: 20,
    })
  })

  it('keeps the modal open and shows an error when the request fails', async () => {
    fetchWorkerHistoryMock.mockRejectedValueOnce(new Error('network failed'))

    const wrapper = mountModal({ open: true, workerId: 'worker-3' })

    await flushPromises()

    expect(messageErrorMock).toHaveBeenCalledWith('获取 Worker 历史记录失败')
    expect(wrapper.find('.modal-stub').exists()).toBe(true)
  })

  it('ignores stale responses after switching workers', async () => {
    let resolveFirst
    fetchWorkerHistoryMock
      .mockImplementationOnce(() => new Promise(resolve => {
        resolveFirst = resolve
      }))
      .mockResolvedValueOnce({
        total: 1,
        data: [
          {
            id: 2,
            worker_id: 'worker-new',
            task_id: 'new-task',
            task_type: 'i2i_pro',
            status: 'success',
          },
        ],
      })

    const wrapper = mountModal({ open: true, workerId: 'worker-old' })

    await wrapper.setProps({ workerId: 'worker-new' })
    await flushPromises()

    expect(wrapper.text()).toContain('new-task')

    resolveFirst({
      total: 1,
      data: [
        {
          id: 1,
          worker_id: 'worker-old',
          task_id: 'old-task',
          task_type: 'img2img',
          status: 'success',
        },
      ],
    })
    await flushPromises()

    expect(wrapper.text()).toContain('new-task')
    expect(wrapper.text()).not.toContain('old-task')
  })
})
