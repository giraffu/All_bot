// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchGalleryReports: vi.fn(),
  resolveGalleryReport: vi.fn(),
  takedownGalleryReport: vi.fn(),
}))

const messageMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}))

vi.mock('../api/api', () => ({
  apiBaseUrl: '',
  fetchGalleryReports: apiMocks.fetchGalleryReports,
  resolveGalleryReport: apiMocks.resolveGalleryReport,
  takedownGalleryReport: apiMocks.takedownGalleryReport,
}))

vi.mock('ant-design-vue/es/message', () => ({
  default: {
    error: messageMocks.error,
    success: messageMocks.success,
  },
}))

import GalleryReportsTable from './GalleryReportsTable.vue'

const ButtonStub = defineComponent({
  name: 'ButtonStub',
  props: ['disabled', 'loading', 'danger', 'type'],
  emits: ['click'],
  template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
})

const TableStub = defineComponent({
  name: 'TableStub',
  props: ['columns', 'dataSource', 'pagination', 'loading', 'rowKey', 'scroll', 'size'],
  emits: ['change'],
  template: `
    <div class="table-stub">
      <div class="row-count">{{ dataSource.length }}</div>
      <div v-for="record in dataSource" :key="record.id" class="table-row">
        <template v-for="column in columns" :key="column.key || column.dataIndex">
          <slot name="bodyCell" :column="column" :record="record" />
        </template>
      </div>
    </div>
  `,
})

const PopconfirmStub = defineComponent({
  name: 'PopconfirmStub',
  emits: ['confirm'],
  template: '<div class="popconfirm-stub" @click="$emit(\'confirm\')"><slot /></div>',
})

const SelectStub = defineComponent({
  name: 'SelectStub',
  props: ['value', 'options'],
  emits: ['update:value', 'change'],
  template:
    '<select :value="value" @change="$emit(\'update:value\', $event.target.value); $emit(\'change\', $event.target.value)" />',
})

const InputNumberStub = defineComponent({
  name: 'InputNumberStub',
  props: ['value'],
  emits: ['update:value'],
  template:
    '<input type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />',
})

const passthroughStub = (name: string) =>
  defineComponent({
    name,
    template: '<span><slot /></span>',
  })

const sampleReport = {
  id: 10,
  post_id: 7,
  post_task_id: 'task-7',
  post_is_active: true,
  post_author_user_id: 456,
  post_author_name: 'author',
  reporter_user_id: 123,
  reporter_name: 'reporter',
  reason: 'gore',
  status: 'pending',
  created_at: '2026-07-04T12:00:00',
  resolved_at: null,
  resolution_action: null,
  media_type: 'image',
  media_url: '/demo.png',
  prompt: 'demo prompt',
}

const mountReportsTable = () =>
  mount(GalleryReportsTable, {
    global: {
      stubs: {
        'a-button': ButtonStub,
        'a-table': TableStub,
        'a-popconfirm': PopconfirmStub,
        'a-select': SelectStub,
        'a-input-number': InputNumberStub,
        'a-divider': passthroughStub('DividerStub'),
        'a-tag': passthroughStub('TagStub'),
        EyeOutlined: passthroughStub('EyeOutlinedStub'),
        ReloadOutlined: passthroughStub('ReloadOutlinedStub'),
        SearchOutlined: passthroughStub('SearchOutlinedStub'),
        StopOutlined: passthroughStub('StopOutlinedStub'),
        WarningOutlined: passthroughStub('WarningOutlinedStub'),
      },
    },
  })

describe('GalleryReportsTable', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchGalleryReports.mockResolvedValue({
      items: [sampleReport],
      total: 1,
      page: 1,
      page_size: 20,
    })
    apiMocks.resolveGalleryReport.mockResolvedValue({ status: 'ok' })
    apiMocks.takedownGalleryReport.mockResolvedValue({
      status: 'ok',
      affected_posts: 1,
      resolved_reports: 1,
    })
  })

  it('loads pending reports by default', async () => {
    const wrapper = mountReportsTable()
    await flushPromises()

    expect(wrapper.find('.row-count').text()).toBe('1')
    expect(apiMocks.fetchGalleryReports).toHaveBeenCalledWith({
      page: 1,
      page_size: 20,
      status: 'pending',
      reason: undefined,
      post_id: undefined,
    })
  })

  it('calls moderation actions from report rows', async () => {
    const wrapper = mountReportsTable()
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const resolveButton = buttons.find(button => button.text().includes('标记处理'))
    const takedownButton = buttons.find(button => button.text().includes('下架'))

    await resolveButton?.trigger('click')
    await flushPromises()
    expect(apiMocks.resolveGalleryReport).toHaveBeenCalledWith(10)

    await takedownButton?.trigger('click')
    await flushPromises()
    expect(apiMocks.takedownGalleryReport).toHaveBeenCalledWith(10)
  })
})
