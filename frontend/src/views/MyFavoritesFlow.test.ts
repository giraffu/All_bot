// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import MyFavorites from '@/views/MyFavorites.vue'
import TemplateApplyWorkbenchHost from '@/components/template-apply/TemplateApplyWorkbenchHost.vue'
import { mainLayoutContentRefKey } from '@/composables/useWorkbenchScrollLock'
import { useTemplateApplyStore } from '@/stores/templateApply'
import { GALLERY_APPLY_CONTEXT_STORAGE_KEY } from '@/utils/galleryApplyContext'

const {
  apiGetMock,
  routerPushMock,
  routerReplaceMock,
  messageSuccessMock,
  messageErrorMock,
  messageWarningMock,
  routeMock
} = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  routerPushMock: vi.fn(),
  routerReplaceMock: vi.fn(),
  messageSuccessMock: vi.fn(),
  messageErrorMock: vi.fn(),
  messageWarningMock: vi.fn(),
  routeMock: {
    query: {
      tab: 'favorite'
    }
  }
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
    useRoute: () => routeMock,
    useRouter: () => ({
      push: routerPushMock,
      replace: routerReplaceMock
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
  name: 'MyFavoritesWorkbenchHarness',
  components: {
    MyFavorites,
    TemplateApplyWorkbenchHost
  },
  template: `
    <div>
      <MyFavorites />
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

const primeFavoritesApi = (options?: { empty?: boolean; submissionsEmpty?: boolean }) => {
  apiGetMock.mockImplementation((url: string) => {
    if (url === '/gallery/config') {
      return Promise.resolve({
        data: {
          allowed_types: [],
          lora_models: [],
          img2img_lora_models: []
        }
      })
    }

    if (url === '/users/my-favorites') {
      return Promise.resolve({
        data: {
          items: options?.empty ? [] : [samplePost],
          total: options?.empty ? 0 : 1,
          page: 1,
          pages: 1
        }
      })
    }

    if (url === '/gallery/my-posts') {
      return Promise.resolve({
        data: {
          items: options?.submissionsEmpty ? [] : [samplePost],
          total: options?.submissionsEmpty ? 0 : 1,
          page: 1,
          pages: 1
        }
      })
    }

    if (url === `/users/history/${samplePost.task_id}/apply-context`) {
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
        'a-textarea': true,
        LazyVideo: true
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

describe('MyFavorites workbench flow', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh'
    routeMock.query.tab = 'favorite'
    sessionStorage.clear()
    apiGetMock.mockReset()
    routerPushMock.mockReset()
    routerReplaceMock.mockReset()
    messageSuccessMock.mockReset()
    messageErrorMock.mockReset()
    messageWarningMock.mockReset()
  })

  it('opens the shared template workbench host from favorite details', async () => {
    primeFavoritesApi()

    const { wrapper, applyButton } = await openDetailAndFindApplyButton()
    await applyButton.trigger('click')
    await flushPromises()
    await flushPromises()

    const templateApplyStore = useTemplateApplyStore()
    const hostModal = wrapper
      .findAll('.a-modal-stub')
      .find(node => node.attributes('data-title') === '快速换脸')

    expect(sessionStorage.getItem(GALLERY_APPLY_CONTEXT_STORAGE_KEY)).toBeNull()
    expect(routerPushMock).not.toHaveBeenCalled()
    expect(messageSuccessMock).toHaveBeenCalledWith('已载入模板工作台')
    expect(templateApplyStore.visible).toBe(true)
    expect(templateApplyStore.panelKind).toBe('faceSwap')
    expect(hostModal?.attributes('data-open')).toBe('true')
  })

  it('renders the shared empty state block when the favorites list is empty', async () => {
    primeFavoritesApi({ empty: true })

    const wrapper = mountHarness()
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('您还没有收藏过任何作品')
    expect(wrapper.findAll('.group.cursor-pointer')).toHaveLength(0)
    expect(useTemplateApplyStore().visible).toBe(false)
  })

  it('switches from favorites to submissions and mounts the submissions branch', async () => {
    primeFavoritesApi({ empty: true })

    const wrapper = mountHarness()
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('您还没有收藏过任何作品')
    expect(wrapper.findAll('.group.cursor-pointer')).toHaveLength(0)

    const submissionsTab = wrapper
      .findAll('button')
      .find(button => button.text().trim() === '我的投稿')

    expect(submissionsTab).toBeTruthy()

    await submissionsTab!.trigger('click')
    await flushPromises()
    await flushPromises()

    expect(routerReplaceMock).toHaveBeenCalledWith({
      name: 'MyFavorites',
      query: {
        tab: 'submissions'
      }
    })
    expect(apiGetMock).toHaveBeenCalledWith('/gallery/my-posts', expect.objectContaining({
      params: expect.objectContaining({
        page: 1,
        task_type: undefined
      })
    }))
    expect(wrapper.text()).not.toContain('您还没有收藏过任何作品')
    expect(wrapper.text()).toContain('已上架')
    expect(wrapper.findAll('.group.cursor-pointer')).toHaveLength(1)
  })

  it('renders the shared error state and retries loading when the favorites list request fails', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/gallery/config') {
        return Promise.resolve({
          data: {
            allowed_types: [],
            lora_models: [],
            img2img_lora_models: []
          }
        })
      }

      if (url === '/users/my-favorites') {
        throw new Error('favorites list failed')
      }

      throw new Error(`Unexpected GET request: ${url}`)
    })

    const wrapper = mountHarness()
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('获取内容失败')
    expect(wrapper.findAll('.group.cursor-pointer')).toHaveLength(0)
    expect(messageErrorMock).toHaveBeenCalledWith('获取内容失败')

    primeFavoritesApi()

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
