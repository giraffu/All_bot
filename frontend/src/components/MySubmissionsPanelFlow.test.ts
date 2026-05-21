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
import { GALLERY_APPLY_CONTEXT_STORAGE_KEY } from '@/utils/galleryApplyContext'

const {
  apiGetMock,
  routerPushMock,
  messageSuccessMock,
  messageErrorMock,
  messageWarningMock
} = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  routerPushMock: vi.fn(),
  messageSuccessMock: vi.fn(),
  messageErrorMock: vi.fn(),
  messageWarningMock: vi.fn()
}))

vi.mock('@/api', () => ({
  default: {
    get: apiGetMock
  }
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPushMock
  })
}))

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

const primeSubmissionsApi = (options?: { empty?: boolean }) => {
  apiGetMock.mockImplementation((url: string) => {
    if (url === '/gallery/my-posts') {
      return Promise.resolve({
        data: {
          items: options?.empty ? [] : [samplePost],
          total: options?.empty ? 0 : 1,
          page: 1,
          pages: 1
        }
      })
    }

    if (url === `/gallery/posts/${samplePost.id}/apply-context`) {
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

const openDetailAndFindApplyButton = async () => {
  const wrapper = mountHarness()
  await flushPromises()
  await flushPromises()

  await wrapper.get('.group.cursor-pointer').trigger('click')
  await flushPromises()
  await flushPromises()

  const applyButton = wrapper
    .findAll('button')
    .find(button => button.text().includes('一键应用'))

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
    routerPushMock.mockReset()
    messageSuccessMock.mockReset()
    messageErrorMock.mockReset()
    messageWarningMock.mockReset()
  })

  it('keeps legacy template apply for submissions without opening the shared workbench host', async () => {
    primeSubmissionsApi()

    const { wrapper, applyButton } = await openDetailAndFindApplyButton()
    await applyButton.trigger('click')
    await flushPromises()
    await flushPromises()

    const templateApplyStore = useTemplateApplyStore()
    const hostModal = wrapper
      .findAll('.a-modal-stub')
      .find(node => node.attributes('data-title') === '模板工作台')

    expect(sessionStorage.getItem(GALLERY_APPLY_CONTEXT_STORAGE_KEY)).toBe(
      JSON.stringify(faceSwapContext)
    )
    expect(routerPushMock).toHaveBeenCalledWith({
      name: 'FaceSwap',
      query: {
        apply: 'true',
        type: 'face_swap',
        title: '快速换脸',
        cost: '1'
      }
    })
    expect(messageSuccessMock).toHaveBeenCalledWith('已载入模板，请上传您的参考图')
    expect(templateApplyStore.visible).toBe(false)
    expect(hostModal?.attributes('data-open')).toBe('false')
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
})
