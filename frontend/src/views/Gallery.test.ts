// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import Gallery from '@/views/Gallery.vue'

const {
  apiGetMock,
  messageSuccessMock,
  messageErrorMock,
  messageWarningMock,
  templateApplyStoreMock,
  confirmTemplateApplyCloseMock
} = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  messageSuccessMock: vi.fn(),
  messageErrorMock: vi.fn(),
  messageWarningMock: vi.fn(),
  templateApplyStoreMock: {
    visible: false,
    openFromRawContext: vi.fn(),
    confirmCloseAndCleanup: vi.fn()
  },
  confirmTemplateApplyCloseMock: vi.fn()
}))

vi.mock('@/api', () => ({
  default: {
    get: apiGetMock
  }
}))

vi.mock('ant-design-vue', async () => {
  const actual = await vi.importActual<object>('ant-design-vue')
  return {
    ...actual,
    message: {
      success: messageSuccessMock,
      error: messageErrorMock,
      warning: messageWarningMock
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

vi.mock('@/stores/templateApply', () => ({
  useTemplateApplyStore: () => templateApplyStoreMock,
  confirmTemplateApplyClose: confirmTemplateApplyCloseMock
}))

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

const ModalStub = defineComponent({
  name: 'AModalStub',
  props: {
    open: {
      type: Boolean,
      default: false
    }
  },
  emits: ['update:open'],
  template: '<div class="a-modal-stub" :data-open="String(open)"><slot /></div>'
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

const samplePostTwo = {
  ...samplePost,
  id: 2,
  task_id: 'task-2',
  thumbnail_url: 'https://example.com/thumb-2.png',
  media_url: 'https://example.com/image-2.png'
}

const faceSwapContext = {
  post_id: 1,
  source_post_id: 1,
  task_type: 'face_swap',
  input_file: 'history/demo/original.png',
  input_file_url: 'https://example.com/original.png',
  prompt: 'demo prompt'
}

const primeGalleryApi = (options?: {
  paged?: boolean
  config?: {
    allowed_types?: Array<{ id: string, name: string }>
    lora_models?: Array<{ id: string, name: string }>
    img2img_lora_models?: Array<{ id: string, name: string }>
  }
}) => {
  apiGetMock.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
    if (url === '/gallery/config') {
      return Promise.resolve({
        data: {
          allowed_types: options?.config?.allowed_types || [],
          lora_models: options?.config?.lora_models || [],
          img2img_lora_models: options?.config?.img2img_lora_models || []
        }
      })
    }

    if (url === '/gallery/posts') {
      const page = Number(config?.params?.page ?? 1)
      if (options?.paged) {
        return Promise.resolve({
          data: {
            items: page === 2 ? [samplePostTwo] : [samplePost],
            total: 2,
            page,
            pages: 2
          }
        })
      }

      return Promise.resolve({
        data: {
          items: [samplePost, samplePostTwo],
          total: 2,
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

const mountGallery = () =>
  mount(Gallery, {
    global: {
      plugins: [i18n],
      stubs: {
        'a-modal': ModalStub,
        'a-textarea': true,
        LazyVideo: true
      }
    }
  })

const openDetailAndFindApplyButton = async () => {
  const wrapper = mountGallery()
  await flushPromises()
  await flushPromises()

  const card = wrapper.find('.group.cursor-pointer')
  await card.trigger('click')
  await flushPromises()

  const applyButton = wrapper
    .findAll('button')
    .find(button => button.text().includes('一键应用'))

  if (!applyButton) {
    throw new Error('Expected apply button to exist in detail modal')
  }

  return { wrapper, applyButton }
}

describe('Gallery template apply integration', () => {
  beforeEach(() => {
    sessionStorage.clear()

    apiGetMock.mockReset()
    messageSuccessMock.mockReset()
    messageErrorMock.mockReset()
    messageWarningMock.mockReset()

    templateApplyStoreMock.visible = false
    templateApplyStoreMock.openFromRawContext.mockReset()
    templateApplyStoreMock.confirmCloseAndCleanup.mockReset()
    templateApplyStoreMock.confirmCloseAndCleanup.mockResolvedValue(undefined)

    confirmTemplateApplyCloseMock.mockReset()

    primeGalleryApi()
  })

  it('opens the template workbench in place without legacy navigation', async () => {
    templateApplyStoreMock.openFromRawContext.mockResolvedValue({
      status: 'opened',
      sessionId: 'session-1'
    })

    const { applyButton } = await openDetailAndFindApplyButton()
    await applyButton.trigger('click')
    await flushPromises()

    expect(templateApplyStoreMock.openFromRawContext).toHaveBeenCalledWith({
      source: 'gallery',
      entryEntityId: samplePost.id,
      rawContext: faceSwapContext
    })
    expect(messageSuccessMock).toHaveBeenCalledWith('已载入模板工作台')
  })

  it('switches page with paged navigation and requests the target page', async () => {
    primeGalleryApi({ paged: true })

    const wrapper = mountGallery()
    await flushPromises()
    await flushPromises()

    const pageTwoButton = wrapper
      .findAll('button')
      .find(button => button.text().trim() === '2')

    expect(pageTwoButton).toBeTruthy()

    await pageTwoButton!.trigger('click')
    await flushPromises()
    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/gallery/posts', expect.objectContaining({
      params: expect.objectContaining({
        page: 2
      })
    }))

    expect(wrapper.html()).toContain(samplePostTwo.media_url)
    expect(wrapper.html()).not.toContain(samplePost.media_url)
  })

  it('merges duplicate gallery task tabs and maps grouped addon filters to request params', async () => {
    primeGalleryApi({
      config: {
        allowed_types: [
          { id: 'i2i_pro', name: '幻想换脸' },
          { id: 'edit', name: '自由P图' },
          { id: 'img2img_lora', name: '图生图(附加模型)' },
          { id: 'custom_video', name: '图生视频' },
          { id: 'video_lora', name: '图生视频(附加模型)' },
          { id: 'ltx_video', name: '高级图生视频' },
        ],
        lora_models: [
          { id: '', name: '无' },
          { id: 'motion-a', name: '动作A' },
        ],
        img2img_lora_models: [
          { id: 'style-a', name: '写真A' },
        ],
      },
    })

    const wrapper = mountGallery()
    await flushPromises()
    await flushPromises()

    const findButtonsByText = (text: string) =>
      wrapper.findAll('button').filter(button => button.text().trim() === text)
    const getLastGalleryPostsParams = () => {
      const galleryCalls = apiGetMock.mock.calls.filter(([url]) => url === '/gallery/posts')
      const lastCall = galleryCalls.at(-1)
      return lastCall?.[1]?.params as Record<string, unknown> | undefined
    }

    expect(findButtonsByText('自由P图')).toHaveLength(1)
    expect(findButtonsByText('图生视频')).toHaveLength(1)
    expect(findButtonsByText('图生图(附加模型)')).toHaveLength(0)
    expect(findButtonsByText('图生视频(附加模型)')).toHaveLength(0)

    await findButtonsByText('自由P图')[0]!.trigger('click')
    await flushPromises()
    await flushPromises()
    expect(findButtonsByText('无')).toHaveLength(1)
    expect(getLastGalleryPostsParams()).toEqual(expect.objectContaining({
      task_type: 'edit_group',
      lora_model: undefined,
    }))

    await findButtonsByText('无')[0]!.trigger('click')
    await flushPromises()
    await flushPromises()
    expect(getLastGalleryPostsParams()).toEqual(expect.objectContaining({
      task_type: 'edit_group',
      lora_model: '__none__',
    }))

    await findButtonsByText('写真A')[0]!.trigger('click')
    await flushPromises()
    await flushPromises()
    expect(getLastGalleryPostsParams()).toEqual(expect.objectContaining({
      task_type: 'edit_group',
      lora_model: 'style-a',
    }))

    await findButtonsByText('图生视频')[0]!.trigger('click')
    await flushPromises()
    await flushPromises()
    expect(getLastGalleryPostsParams()).toEqual(expect.objectContaining({
      task_type: 'img2video_group',
      lora_model: undefined,
    }))
  })

  it('keeps detail apply on the shared path when workbench fallback is returned', async () => {
    templateApplyStoreMock.openFromRawContext.mockResolvedValue({
      status: 'legacy_fallback',
      fallbackKind: 'legacy_supported',
      rawTaskType: 'face_swap',
      meta: null
    })

    const { applyButton } = await openDetailAndFindApplyButton()
    await applyButton.trigger('click')
    await flushPromises()

    expect(messageErrorMock).toHaveBeenCalledWith('模板工作台打开失败，请稍后重试。')
    expect(messageSuccessMock).not.toHaveBeenCalled()
  })

  it('runs replace-close confirmation and retries opening when the current session must be replaced', async () => {
    templateApplyStoreMock.openFromRawContext
      .mockResolvedValueOnce({
        status: 'confirm_required',
        trigger: 'open_replace',
        confirmReason: 'dirty'
      })
      .mockResolvedValueOnce({
        status: 'opened',
        sessionId: 'session-2'
      })
    confirmTemplateApplyCloseMock.mockResolvedValue(true)

    const { applyButton } = await openDetailAndFindApplyButton()
    await applyButton.trigger('click')
    await flushPromises()

    expect(confirmTemplateApplyCloseMock).toHaveBeenCalledWith('dirty')
    expect(templateApplyStoreMock.confirmCloseAndCleanup).toHaveBeenCalledWith('open_replace')
    expect(templateApplyStoreMock.openFromRawContext).toHaveBeenCalledTimes(2)
    expect(messageSuccessMock).toHaveBeenCalledWith('已载入模板工作台')
  })

  it('ignores a stale apply-context response after the user switches to another post', async () => {
    let settleApplyContext: ((value: { data: typeof faceSwapContext }) => void) | undefined

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
            items: [samplePost, samplePostTwo],
            total: 2
          }
        })
      }

      if (url === `/gallery/items/${samplePost.id}/apply-context`) {
        return new Promise<{ data: typeof faceSwapContext }>(resolve => {
          settleApplyContext = resolve
        })
      }

      throw new Error(`Unexpected GET request: ${url}`)
    })

    const { wrapper, applyButton } = await openDetailAndFindApplyButton()
    await applyButton.trigger('click')

    const cards = wrapper.findAll('.group.cursor-pointer')
    await cards[1]?.trigger('click')
    await flushPromises()

    if (!settleApplyContext) {
      throw new Error('Expected apply-context request to be pending')
    }
    settleApplyContext({ data: faceSwapContext })
    await flushPromises()

    expect(templateApplyStoreMock.openFromRawContext).not.toHaveBeenCalled()
    expect(messageSuccessMock).not.toHaveBeenCalledWith('已载入模板工作台')
  })

  it('ignores a stale apply-context response after the detail modal closes', async () => {
    let settleApplyContext: ((value: { data: typeof faceSwapContext }) => void) | undefined

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
            items: [samplePost, samplePostTwo],
            total: 2
          }
        })
      }

      if (url === `/gallery/items/${samplePost.id}/apply-context`) {
        return new Promise<{ data: typeof faceSwapContext }>(resolve => {
          settleApplyContext = resolve
        })
      }

      throw new Error(`Unexpected GET request: ${url}`)
    })

    const { wrapper, applyButton } = await openDetailAndFindApplyButton()
    await applyButton.trigger('click')
    await flushPromises()

    const detailModal = wrapper.findAllComponents(ModalStub)[0]
    detailModal?.vm.$emit('update:open', false)
    await flushPromises()

    if (!settleApplyContext) {
      throw new Error('Expected apply-context request to be pending')
    }

    settleApplyContext({ data: faceSwapContext })
    await flushPromises()

    expect(templateApplyStoreMock.openFromRawContext).not.toHaveBeenCalled()
    expect(messageSuccessMock).not.toHaveBeenCalledWith('已载入模板工作台')
  })

  it('ignores a stale apply-context response after the gallery unmounts', async () => {
    let settleApplyContext: ((value: { data: typeof faceSwapContext }) => void) | undefined

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
            items: [samplePost, samplePostTwo],
            total: 2
          }
        })
      }

      if (url === `/gallery/items/${samplePost.id}/apply-context`) {
        return new Promise<{ data: typeof faceSwapContext }>(resolve => {
          settleApplyContext = resolve
        })
      }

      throw new Error(`Unexpected GET request: ${url}`)
    })

    const { wrapper, applyButton } = await openDetailAndFindApplyButton()
    await applyButton.trigger('click')
    await flushPromises()

    wrapper.unmount()

    if (!settleApplyContext) {
      throw new Error('Expected apply-context request to be pending')
    }

    settleApplyContext({ data: faceSwapContext })
    await flushPromises()

    expect(templateApplyStoreMock.openFromRawContext).not.toHaveBeenCalled()
    expect(messageSuccessMock).not.toHaveBeenCalledWith('已载入模板工作台')
  })
})
