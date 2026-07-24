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
    )
  })
})
