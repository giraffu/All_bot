// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import Gallery from '@/views/Gallery.vue'
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

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn()
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

vi.mock('@/components/LazyVideo.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  return {
    default: defineComponent({
      name: 'LazyVideoStub',
      template: '<div class="lazy-video-stub" />'
    })
  }
})

vi.mock('vue-waterfall-plugin-next', async () => {
  const { defineComponent, nextTick, onMounted, onUpdated } = await vi.importActual<typeof import('vue')>('vue')
  return {
    Waterfall: defineComponent({
      name: 'WaterfallStub',
      emits: ['afterRender'],
      props: {
        list: {
          type: Array,
          default: () => []
        }
      },
      setup(_, { emit }) {
        const triggerAfterRender = () => {
          void nextTick(() => emit('afterRender'))
        }

        onMounted(triggerAfterRender)
        onUpdated(triggerAfterRender)
        return {}
      },
      template: `
        <div class="waterfall-stub">
          <template v-for="item in list" :key="item.id">
            <slot :item="item" />
          </template>
        </div>
      `
    })
  }
})

vi.mock('@/components/template-apply/TemplateFaceSwapPanel.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  return {
    __esModule: true,
    __isTeleport: false,
    default: defineComponent({
      name: 'TemplateFaceSwapPanelStub',
      props: ['sessionId', 'context'],
      template: '<div class="panel face-swap-panel">face-swap-workbench</div>'
    })
  }
})

vi.mock('@/components/template-apply/TemplateImagePromptPanel.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  return {
    __esModule: true,
    __isTeleport: false,
    default: defineComponent({
      name: 'TemplateImagePromptPanelStub',
      template: '<div class="panel image-prompt-panel" />'
    })
  }
})

vi.mock('@/components/template-apply/TemplateImageToVideoPanel.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  return {
    __esModule: true,
    __isTeleport: false,
    default: defineComponent({
      name: 'TemplateImageToVideoPanelStub',
      template: '<div class="panel image-to-video-panel" />'
    })
  }
})

vi.mock('@/components/template-apply/TemplateVideoSwapPanel.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  return {
    __esModule: true,
    __isTeleport: false,
    default: defineComponent({
      name: 'TemplateVideoSwapPanelStub',
      template: '<div class="panel video-swap-panel" />'
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
      <button class="modal-close" @click="$emit('cancel')">close</button>
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
      <button class="drawer-close" @click="$emit('close')">close</button>
      <slot />
    </div>
  `
})

const AppHarness = defineComponent({
  name: 'GalleryWorkbenchHarness',
  components: {
    Gallery,
    TemplateApplyWorkbenchHost
  },
  template: `
    <div>
      <Gallery />
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
  author_name: 'tester'
}

const faceSwapContext = {
  post_id: 1,
  source_post_id: 1,
  task_type: 'face_swap',
  input_file: 'history/demo/original.png',
  input_file_url: 'https://example.com/original.png',
  prompt: 'demo prompt'
}

const primeGalleryApi = (options?: { empty?: boolean }) => {
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

    if (url === '/gallery/posts') {
      return Promise.resolve({
        data: {
          items: options?.empty ? [] : [samplePost],
          total: options?.empty ? 0 : 1,
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

describe('Gallery workbench flow', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh'
    sessionStorage.clear()
    apiGetMock.mockReset()
    messageSuccessMock.mockReset()
    messageErrorMock.mockReset()
    messageWarningMock.mockReset()
  })

  it('opens the template workbench host from the gallery detail apply action', async () => {
    primeGalleryApi()

    const wrapper = mountHarness()
    await flushPromises()
    await flushPromises()

    await wrapper.find('.group.cursor-pointer').trigger('click')
    await flushPromises()

    const applyButton = wrapper
      .findAll('button')
      .find(button => button.text().includes('一键应用'))

    expect(applyButton).toBeTruthy()

    await applyButton!.trigger('click')
    await flushPromises()
    await flushPromises()

    const templateApplyStore = useTemplateApplyStore()
    const workbenchModal = wrapper
      .findAll('.a-modal-stub')
      .find(node => node.attributes('data-title') === '快速换脸')

    expect(messageSuccessMock).toHaveBeenCalledWith('已载入模板工作台')
    expect(templateApplyStore.visible).toBe(true)
    expect(templateApplyStore.panelKind).toBe('faceSwap')
    expect(workbenchModal?.attributes('data-open')).toBe('true')
  })

  it('renders the shared empty state block when the gallery list is empty', async () => {
    primeGalleryApi({ empty: true })

    const wrapper = mountHarness()
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('暂无道友分享作品')
    expect(wrapper.find('.waterfall-stub').text()).toBe('')
    expect(useTemplateApplyStore().visible).toBe(false)
  })

  it('renders the shared error state and retries loading when the gallery list request fails', async () => {
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

      if (url === '/gallery/posts') {
        throw new Error('gallery list failed')
      }

      throw new Error(`Unexpected GET request: ${url}`)
    })

    const wrapper = mountHarness()
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('获取内容失败')
    expect(wrapper.find('.waterfall-stub').text()).toBe('')
    expect(messageErrorMock).toHaveBeenCalledWith('获取广场数据失败')

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

      if (url === '/gallery/posts') {
        return Promise.resolve({
          data: {
            items: [samplePost],
            total: 1,
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
