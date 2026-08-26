import { flushPromises, shallowMount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import HistoryTable from './HistoryTable.vue'

const apiMocks = vi.hoisted(() => ({
  fetchHistoryAll: vi.fn(),
  fetchWorkerList: vi.fn(),
}))

vi.mock('../api/api', () => apiMocks)

describe('HistoryTable source filters', () => {
  beforeEach(() => {
    apiMocks.fetchHistoryAll.mockReset()
    apiMocks.fetchHistoryAll.mockResolvedValue({ items: [], total: 0 })
    apiMocks.fetchWorkerList.mockReset()
    apiMocks.fetchWorkerList.mockResolvedValue({ workers: [] })
  })

  it('widens the worker filter and sends the selected QQCC source', async () => {
    const SelectStub = defineComponent({
      name: 'ASelect',
      inheritAttrs: false,
      emits: ['update:value', 'change'],
      template: '<select v-bind="$attrs" />',
    })
    const wrapper = shallowMount(HistoryTable, {
      global: {
        components: {
          ASelect: SelectStub,
        },
      },
    })
    await flushPromises()

    const workerFilter = wrapper.get('[data-testid="history-worker-filter"]')
    const sourceFilter = wrapper.get('[data-testid="history-source-filter"]')
    const typeFilter = wrapper.get('[data-testid="history-type-filter"]')

    expect(typeFilter.attributes('style')).toContain('min-width: 240px')
    expect(workerFilter.attributes('style')).toContain('width: 190px')
    expect(sourceFilter.attributes('style')).toContain('width: 180px')

    const sourceSelect = wrapper.findAllComponents(SelectStub)[4]!
    expect(sourceSelect).toBeDefined()
    sourceSelect.vm.$emit('update:value', 'bot:qqcc')
    sourceSelect.vm.$emit('change')
    await flushPromises()

    expect(apiMocks.fetchHistoryAll).toHaveBeenLastCalledWith(
      1,
      20,
      null,
      null,
      null,
      null,
      'bot:qqcc',
      { signal: expect.any(AbortSignal) },
    )
  })

  it('keeps responsive server pagination in the constrained table region', async () => {
    const TableStub = defineComponent({
      name: 'ATable',
      inheritAttrs: false,
      props: {
        pagination: { type: Object, required: true },
        scroll: { type: Object, required: true },
      },
      emits: ['change'],
      template: '<div data-testid="history-table-stub" v-bind="$attrs" />',
    })
    const wrapper = shallowMount(HistoryTable, {
      global: {
        components: {
          ATable: TableStub,
        },
      },
    })
    await flushPromises()

    const table = wrapper.getComponent(TableStub)
    expect(wrapper.get('[data-testid="history-table-shell"]').classes()).toContain(
      'min-h-0',
    )
    expect(wrapper.get('[data-testid="history-filter-strip"]').classes()).toContain(
      'overflow-x-auto',
    )
    expect(table.classes()).toContain('min-h-0')
    expect(table.props('scroll')).toMatchObject({ x: 1350 })
    expect(table.props('pagination')).toMatchObject({
      current: 1,
      pageSize: 20,
      total: 0,
      responsive: true,
      showLessItems: true,
    })

    table.vm.$emit('change', { current: 2, pageSize: 20 })
    await flushPromises()

    expect(apiMocks.fetchHistoryAll).toHaveBeenLastCalledWith(
      2,
      20,
      null,
      null,
      null,
      null,
      null,
      { signal: expect.any(AbortSignal) },
    )
  })

  it('aborts the previous history request when a filter changes', async () => {
    const pendingRequests: Array<{
      resolve: (value: { items: never[]; total: number }) => void
      signal: AbortSignal
    }> = []
    apiMocks.fetchHistoryAll.mockImplementation((...args) => new Promise((resolve) => {
      pendingRequests.push({
        resolve,
        signal: args[7].signal,
      })
    }))
    const SelectStub = defineComponent({
      name: 'ASelect',
      inheritAttrs: false,
      emits: ['update:value', 'change'],
      template: '<select v-bind="$attrs" />',
    })
    const wrapper = shallowMount(HistoryTable, {
      global: { components: { ASelect: SelectStub } },
    })
    await flushPromises()

    const sourceSelect = wrapper.findAllComponents(SelectStub)[4]!
    sourceSelect.vm.$emit('change')
    await flushPromises()

    expect(pendingRequests).toHaveLength(2)
    expect(pendingRequests[0].signal.aborted).toBe(true)
    expect(pendingRequests[1].signal.aborted).toBe(false)
    pendingRequests[1].resolve({ items: [], total: 0 })
    await flushPromises()
  })
})
