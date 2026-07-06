// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import Gallery from '@/views/Gallery.vue'

const {
  apiGetMock,
  apiPostMock,
  messageSuccessMock,
  messageErrorMock,
  messageWarningMock,
  templateApplyStoreMock,
  confirmTemplateApplyCloseMock
} = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  apiPostMock: vi.fn(),
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
    get: apiGetMock,
    post: apiPostMock
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
  author_name: 'tester',
  prompt: 'demo prompt',
  task_type: 'i2i_pro',
  input_file: 'history/demo/reference.png',
  input_file_url: 'https://example.com/reference.png',
  input_files: ['history/demo/reference.png'],
  input_file_urls: ['https://example.com/reference.png'],
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
    window.history.replaceState(null, '', '/gallery')

    apiGetMock.mockReset()
    apiPostMock.mockReset()
    messageSuccessMock.mockReset()
    messageErrorMock.mockReset()
    messageWarningMock.mockReset()

    templateApplyStoreMock.visible = false
    templateApplyStoreMock.openFromRawContext.mockReset()
    templateApplyStoreMock.confirmCloseAndCleanup.mockReset()
    templateApplyStoreMock.confirmCloseAndCleanup.mockResolvedValue(undefined)

    confirmTemplateApplyCloseMock.mockReset()

    primeGalleryApi()
    apiPostMock.mockResolvedValue({ data: { status: 'ok', report_id: 99 } })
  })

  it('hides copy actions and masks prompt in gallery detail', async () => {
    const wrapper = mountGallery()
    await flushPromises()
    await flushPromises()

    await wrapper.get('.group.cursor-pointer').trigger('click')
    await flushPromises()

    expect(wrapper.find('.original-input-badge').exists()).toBe(true)
    expect(wrapper.text()).toContain('原始输入')
    expect(wrapper.text()).not.toContain('复制提示词')
    expect(wrapper.text()).toContain('demo ')
    expect(/[•·◦*]/.test(wrapper.text())).toBe(true)
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

  it('submits a gallery report from the detail modal', async () => {
    const wrapper = mountGallery()
    await flushPromises()
    await flushPromises()

    await wrapper.get('.group.cursor-pointer').trigger('click')
    await flushPromises()

    const reportButton = wrapper.find('.detail-report-action')
    expect(reportButton.exists()).toBe(true)

    await reportButton.trigger('click')
    await flushPromises()

    const submitButton = wrapper
      .findAll('button')
      .find(button => button.text().includes('提交举报'))

    expect(submitButton).toBeTruthy()

    await submitButton!.trigger('click')
    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith('/gallery/posts/1/reports', {
      reason: 'children'
    })
    expect(messageSuccessMock).toHaveBeenCalledWith('举报已提交')
  })

  it('opens a gallery apply deep link from query params', async () => {
    window.history.replaceState(null, '', `/gallery?apply_source=gallery&apply_id=${samplePost.id}`)
    templateApplyStoreMock.openFromRawContext.mockResolvedValue({
      status: 'opened',
      sessionId: 'session-deeplink'
    })

    mountGallery()
    await flushPromises()
    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith(`/gallery/items/${samplePost.id}/apply-context`)
    expect(templateApplyStoreMock.openFromRawContext).toHaveBeenCalledWith({
      source: 'gallery',
      entryEntityId: samplePost.id,
      rawContext: faceSwapContext
    })
    expect(messageSuccessMock).toHaveBeenCalledWith('已载入模板工作台')
    expect(window.location.search).toBe('')
  })

  it('disables template apply for stitched Wan22 gallery posts', async () => {
    const stitchedPost = {
      ...samplePost,
      id: 3,
      task_id: 'task-stitched',
      media_type: 'video',
      task_type: 'wan22_video_v2',
      result_meta: {
        wan22_is_stitched: true
      },
      template_apply_supported: false,
      template_apply_disabled_reason: 'wan22_stitched'
    }
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
            items: [stitchedPost],
            total: 1,
            page: 1,
            pages: 1
          }
        })
      }
      throw new Error(`Unexpected GET request: ${url}`)
    })

    const { applyButton } = await openDetailAndFindApplyButton()

    expect(applyButton.attributes('disabled')).toBeDefined()
    expect(applyButton.text()).toContain('一键应用')
    expect(applyButton.text()).not.toContain('拼接视频')

    await applyButton.trigger('click')
    await flushPromises()

    expect(
      apiGetMock.mock.calls.some(([url]) => String(url).includes('apply-context'))
    ).toBe(false)
    expect(templateApplyStoreMock.openFromRawContext).not.toHaveBeenCalled()
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
          { id: 'txt2img', name: '文生图' },
          { id: 'i2i_pro', name: '幻想换脸' },
          { id: 'edit', name: '自由P图' },
          { id: 'img2img_lora', name: '图生图(附加模型)' },
          { id: 'pornmaster_flux2_single_edit', name: '自由P图 v2' },
          { id: 'pornmaster_flux2_multi_edit', name: '自由P图 v2' },
          { id: 'custom_video', name: '图生视频' },
          { id: 'video_lora', name: '图生视频(附加模型)' },
          { id: 'ltx_video', name: '高级图生视频' },
          { id: 'wan22_video_v2', name: '图生视频 v2' },
          { id: 'scail2_action_transfer', name: '动作迁移' },
          { id: 'scail2_action_transfer_long', name: '动作迁移' },
          { id: 'scail2_video_replacement', name: '视频换人' },
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
    expect(findButtonsByText('自由P图 v2')).toHaveLength(1)
    expect(findButtonsByText('图生视频')).toHaveLength(1)
    expect(findButtonsByText('图生视频 v2')).toHaveLength(1)
    expect(findButtonsByText('动作迁移')).toHaveLength(1)
    expect(findButtonsByText('动作迁移（长时间）')).toHaveLength(0)
    expect(findButtonsByText('视频换人')).toHaveLength(1)
    expect(findButtonsByText('文生图')).toHaveLength(0)
    expect(findButtonsByText('gallery.tabs.txt2img')).toHaveLength(0)
    expect(findButtonsByText('gallery.tabs.scail2_action_transfer')).toHaveLength(0)
    expect(findButtonsByText('gallery.tabs.scail2_action_transfer_long')).toHaveLength(0)
    expect(findButtonsByText('gallery.tabs.scail2_video_replacement')).toHaveLength(0)
    expect(findButtonsByText('scail2_action_transfer')).toHaveLength(0)
    expect(findButtonsByText('scail2_action_transfer_long')).toHaveLength(0)
    expect(findButtonsByText('scail2_video_replacement')).toHaveLength(0)
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

    await findButtonsByText('自由P图 v2')[0]!.trigger('click')
    await flushPromises()
    await flushPromises()
    expect(getLastGalleryPostsParams()).toEqual(expect.objectContaining({
      task_type: 'free_edit_v2_group',
      lora_model: undefined,
    }))

    await findButtonsByText('图生视频')[0]!.trigger('click')
    await flushPromises()
    await flushPromises()
    expect(getLastGalleryPostsParams()).toEqual(expect.objectContaining({
      task_type: 'img2video_group',
      lora_model: undefined,
    }))
  })

  it('keeps detail apply on the shared path when an unsupported task is returned', async () => {
    templateApplyStoreMock.openFromRawContext.mockResolvedValue({
      status: 'unsupported',
      rawTaskType: 'face_swap',
      context: {} as any
    })

    const { applyButton } = await openDetailAndFindApplyButton()
    await applyButton.trigger('click')
    await flushPromises()

    expect(messageWarningMock).toHaveBeenCalledWith('当前模板暂不支持打开')
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
