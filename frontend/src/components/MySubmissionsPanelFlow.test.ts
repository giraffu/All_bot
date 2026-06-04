// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import MySubmissionsPanel from '@/components/MySubmissionsPanel.vue'
import TemplateApplyWorkbenchHost from '@/components/template-apply/TemplateApplyWorkbenchHost.vue'
import { mainLayoutContentRefKey } from '@/composables/useWorkbenchScrollLock'
import { useTemplateApplyStore } from '@/stores/templateApply'

const {
  apiGetMock,
  messageSuccessMock,
  messageErrorMock,
  messageWarningMock
} = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  messageSuccessMock: vi.fn(),
  messageErrorMock: vi.fn(),
  messageWarningMock: vi.fn()
}))

vi.mock('@/api', () => ({
  default: {
    get: apiGetMock
  }
}))

vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')
  return {
    ...actual,
    useRouter: () => ({
      push: vi.fn()
    })
  }
})

vi.mock('ant-design-vue', async () => {
  const actual = await vi.importActual<object>('ant-design-vue')
  return {
    ...actual,
    message: {
      success: messageSuccessMock,
      error: messageErrorMock,
      warning: messageWarningMock
    },
    Modal: {
      confirm: vi.fn()
    }
  }
})

vi.mock('@/composables/useViewport', async () => {
  const { ref } = await vi.importActual<typeof import('vue')>('vue')
  return {
    useViewport: () => ({
      isMobile: ref(false)
    })
  }
})

vi.mock('@/composables/useGalleryComments', async () => {
  const { ref } = await vi.importActual<typeof import('vue')>('vue')
  return {
    useGalleryComments: () => ({
      comments: ref([]),
      commentsLoading: ref(false),
      commentsError: ref(''),
      commentsPage: ref(1),
      commentsTotal: ref(0),
      commentsHasMore: ref(false),
      showCommentInput: ref(false),
      newComment: ref(''),
      submittingComment: ref(false),
      loadComments: vi.fn(),
      loadMoreComments: vi.fn(),
      submitComment: vi.fn()
    })
  }
})

const ModalStub = defineComponent({
  name: 'AModalStub',
  props: {
    open: {
      type: Boolean,
      default: false
    },
    title: {
      type: String,
      default: ''
    }
  },
  emits: ['update:open', 'cancel'],
  template: `
    <div class="a-modal-stub" :data-open="String(open)" :data-title="title">
      <slot />
    </div>
  `
})

const DrawerStub = defineComponent({
  name: 'ADrawerStub',
  props: {
    open: {
      type: Boolean,
      default: false
    },
    title: {
      type: String,
      default: ''
    }
  },
  emits: ['close'],
  template: `
    <div class="a-drawer-stub" :data-open="String(open)" :data-title="title">
      <slot />
    </div>
  `
})

const AppHarness = defineComponent({
  name: 'MySubmissionsWorkbenchHarness',
  components: {
    MySubmissionsPanel,
    TemplateApplyWorkbenchHost
  },
  template: `
    <div>
      <MySubmissionsPanel />
      <TemplateApplyWorkbenchHost />
    </div>
  `
})

const samplePost = {
  id: 1,
  task_id: 'task-1',
  media_type: 'image',
  width: 512,
  height: 512,
  duration: 0,
  tags: ['task.face_swap'],
  likes_count: 1,
  dislikes_count: 0,
  applied_count: 3,
  comments_count: 0,
  thumbnail_url: 'https://example.com/thumb.png',
  media_url: 'https://example.com/image.png',
  created_at: '2026-05-16T00:00:00Z',
  has_liked: false,
  has_disliked: false,
  is_active: true,
  prompt: 'demo prompt'
}

const faceSwapContext = {
  post_id: 1,
  source_post_id: 1,
  task_type: 'face_swap',
  input_file: 'history/demo/original.png',
  input_file_url: 'https://example.com/original.png',
  prompt: 'demo prompt'
}

const primeSubmissionsApi = (
  options?: { empty?: boolean, items?: Array<typeof samplePost & Record<string, unknown>> }
) => {
  apiGetMock.mockImplementation((url: string) => {
    if (url === '/gallery/my-posts') {
      const items = options?.items ?? [samplePost]
      return Promise.resolve({
        data: {
          items: options?.empty ? [] : items,
          total: options?.empty ? 0 : items.length,
          page: 1,
          pages: 1
        }
      })
    }

    if (url === `/gallery/items/${samplePost.id}/apply-context`) {
      return Promise.resolve({ data: faceSwapContext })
    }

    throw new Error(`Unexpected GET request: ${url}`)
  })
}

const mountHarness = () => {
  const pinia = createPinia()
  setActivePinia(pinia)

  return mount(AppHarness, {
    global: {
      plugins: [i18n, pinia],
      stubs: {
        'a-modal': ModalStub,
        'a-drawer': DrawerStub,
        AModal: ModalStub,
        ADrawer: DrawerStub,
        'a-textarea': true
      },
      provide: {
        [mainLayoutContentRefKey as symbol]: computed(() => document.createElement('div'))
      }
    }
  })
}

const openSubmissionsDetail = async () => {
  const wrapper = mountHarness()
  await flushPromises()
  await flushPromises()

  await wrapper.get('.group.cursor-pointer').trigger('click')
  await flushPromises()
  await flushPromises()

  return wrapper
}

const findApplyButton = (wrapper: ReturnType<typeof mountHarness>) =>
  wrapper
    .findAll('button')
    .find(button => button.text().includes('一键应用'))

const openDetailAndFindApplyButton = async () => {
  const wrapper = await openSubmissionsDetail()
  const applyButton = findApplyButton(wrapper)

  expect(applyButton).toBeTruthy()

  return {
    wrapper,
    applyButton: applyButton!
  }
}

describe('MySubmissionsPanel workbench flow', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh'
    sessionStorage.clear()
    apiGetMock.mockReset()
    messageSuccessMock.mockReset()
    messageErrorMock.mockReset()
    messageWarningMock.mockReset()
  })

  it('opens the shared template workbench host from submissions details', async () => {
    primeSubmissionsApi()

    const { wrapper, applyButton } = await openDetailAndFindApplyButton()

    expect(wrapper.text()).toContain('删除')
    expect(wrapper.text()).toContain('下架')

    await applyButton.trigger('click')
    await flushPromises()
    await flushPromises()

    const templateApplyStore = useTemplateApplyStore()
    const hostModal = wrapper
      .findAll('.a-modal-stub')
      .find(node => node.attributes('data-title') === '快速换脸')

    expect(messageSuccessMock).toHaveBeenCalledWith('已载入模板工作台')
    expect(templateApplyStore.visible).toBe(true)
    expect(templateApplyStore.panelKind).toBe('faceSwap')
    expect(hostModal?.attributes('data-open')).toBe('true')
  })

  it('hides template apply for stitched Wan22 submissions', async () => {
    primeSubmissionsApi({
      items: [{
        ...samplePost,
        media_type: 'video',
        task_type: 'wan22_video_v2',
        result_meta: {
          wan22_is_stitched: true
        },
        template_apply_supported: false,
        template_apply_disabled_reason: 'wan22_stitched'
      }]
    })

    const wrapper = await openSubmissionsDetail()

    expect(wrapper.text()).toContain('删除')
    expect(wrapper.text()).toContain('下架')
    expect(findApplyButton(wrapper)).toBeUndefined()
    expect(
      apiGetMock.mock.calls.some(([url]) => String(url).includes('apply-context'))
    ).toBe(false)
    expect(useTemplateApplyStore().visible).toBe(false)
  })

  it('renders the shared empty state block when the submissions list is empty', async () => {
    primeSubmissionsApi({ empty: true })

    const wrapper = mountHarness()
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('您还没有投稿任何作品')
    expect(wrapper.findAll('.group.cursor-pointer')).toHaveLength(0)
    expect(useTemplateApplyStore().visible).toBe(false)
  })

  it('renders the shared error state and retries loading when the submissions list request fails', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/gallery/my-posts') {
        throw new Error('submissions list failed')
      }

      throw new Error(`Unexpected GET request: ${url}`)
    })

    const wrapper = mountHarness()
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('获取内容失败')
    expect(wrapper.findAll('.group.cursor-pointer')).toHaveLength(0)
    expect(messageErrorMock).toHaveBeenCalledWith('获取内容失败')

    primeSubmissionsApi()

    const retryButton = wrapper
      .findAll('button')
      .find(button => button.text().includes('重试'))

    expect(retryButton).toBeTruthy()

    await retryButton!.trigger('click')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).not.toContain('获取内容失败')
    expect(wrapper.findAll('.group.cursor-pointer')).toHaveLength(1)
  })
})
