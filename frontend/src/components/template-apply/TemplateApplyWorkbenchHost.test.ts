// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import {
  mainLayoutContentRefKey
} from '@/composables/useWorkbenchScrollLock'
import TemplateApplyWorkbenchHost from '@/components/template-apply/TemplateApplyWorkbenchHost.vue'

const {
  isMobileRef,
  templateApplyStoreMock,
  confirmTemplateApplyCloseMock,
  useWorkbenchScrollLockMock
} = vi.hoisted(() => ({
  isMobileRef: { value: false },
  templateApplyStoreMock: {
    visible: true,
    panelKind: 'faceSwap',
    featureTitleKey: 'lab.cards.fast_face_swap_title',
    session: {
      sessionId: 'session-1'
    },
    context: {
      rawTaskType: 'face_swap'
    },
    requestClose: vi.fn(),
    confirmCloseAndCleanup: vi.fn()
  },
  confirmTemplateApplyCloseMock: vi.fn(),
  useWorkbenchScrollLockMock: vi.fn()
}))

vi.mock('@/composables/useViewport', () => ({
  useViewport: () => ({
    isMobile: isMobileRef.value
  })
}))

vi.mock('@/composables/useWorkbenchScrollLock', async () => {
  const actual = await vi.importActual<typeof import('@/composables/useWorkbenchScrollLock')>(
    '@/composables/useWorkbenchScrollLock'
  )
  return {
    ...actual,
    useWorkbenchScrollLock: useWorkbenchScrollLockMock
  }
})

vi.mock('@/stores/templateApply', () => ({
  useTemplateApplyStore: () => templateApplyStoreMock,
  confirmTemplateApplyClose: confirmTemplateApplyCloseMock
}))

vi.mock('@/components/template-apply/TemplateImagePromptPanel.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  const component = defineComponent({
    name: 'TemplateImagePromptPanelStub',
    props: ['sessionId', 'context'],
    template: '<div class="panel image-prompt">image-prompt</div>'
  })
  return {
    __esModule: true,
    __isTeleport: false,
    default: component
  }
})

vi.mock('@/components/template-apply/TemplateImageToVideoPanel.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  const component = defineComponent({
    name: 'TemplateImageToVideoPanelStub',
    props: ['sessionId', 'context'],
    template: '<div class="panel image-to-video">image-to-video</div>'
  })
  return {
    __esModule: true,
    __isTeleport: false,
    default: component
  }
})

vi.mock('@/components/template-apply/TemplateFaceSwapPanel.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  const component = defineComponent({
    name: 'TemplateFaceSwapPanelStub',
    props: ['sessionId', 'context'],
    template: '<div class="panel face-swap">face-swap</div>'
  })
  return {
    __esModule: true,
    __isTeleport: false,
    default: component
  }
})

vi.mock('@/components/template-apply/TemplateVideoSwapPanel.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  const component = defineComponent({
    name: 'TemplateVideoSwapPanelStub',
    props: ['sessionId', 'context'],
    template: '<div class="panel video-swap">video-swap</div>'
  })
  return {
    __esModule: true,
    __isTeleport: false,
    default: component
  }
})

vi.mock('@/components/template-apply/TemplateScail2VideoPanel.vue', () => ({
  __esModule: true,
  __isTeleport: false,
  default: {
    name: 'TemplateScail2VideoPanelStub',
    props: ['sessionId', 'context'],
    template: '<div class="panel scail2-video">scail2-video</div>'
  }
}))

const ModalStub = defineComponent({
  name: 'AModalStub',
  props: ['open', 'title'],
  emits: ['cancel'],
  template: `
    <div class="modal-stub" :data-open="String(open)" :data-title="title">
      <button class="modal-cancel" @click="$emit('cancel')">cancel</button>
      <slot />
    </div>
  `
})

const DrawerStub = defineComponent({
  name: 'ADrawerStub',
  props: ['open', 'title'],
  emits: ['close'],
  template: `
    <div class="drawer-stub" :data-open="String(open)" :data-title="title">
      <button class="drawer-close" @click="$emit('close')">close</button>
      <slot />
    </div>
  `
})

const mountHost = () => {
  const contentElement = document.createElement('div')

  return mount(TemplateApplyWorkbenchHost, {
    global: {
      plugins: [i18n],
      stubs: {
        'a-modal': ModalStub,
        'a-drawer': DrawerStub,
        AModal: ModalStub,
        ADrawer: DrawerStub
      },
      provide: {
        [mainLayoutContentRefKey as symbol]: computed(() => contentElement)
      }
    }
  })
}

describe('TemplateApplyWorkbenchHost', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh'
    isMobileRef.value = false

    templateApplyStoreMock.visible = true
    templateApplyStoreMock.panelKind = 'faceSwap'
    templateApplyStoreMock.featureTitleKey = 'lab.cards.fast_face_swap_title'
    templateApplyStoreMock.session = {
      sessionId: 'session-1'
    }
    templateApplyStoreMock.context = {
      rawTaskType: 'face_swap'
    }

    templateApplyStoreMock.requestClose.mockReset()
    templateApplyStoreMock.confirmCloseAndCleanup.mockReset()
    templateApplyStoreMock.confirmCloseAndCleanup.mockResolvedValue(undefined)
    confirmTemplateApplyCloseMock.mockReset()

    useWorkbenchScrollLockMock.mockReset()
  })

  it('uses the desktop cancel entry to request and execute cleanup', async () => {
    templateApplyStoreMock.requestClose.mockResolvedValue({
      status: 'close_now'
    })

    const wrapper = mountHost()
    wrapper.findComponent(ModalStub).vm.$emit('cancel')
    await nextTick()
    await flushPromises()

    expect(templateApplyStoreMock.requestClose).toHaveBeenCalledWith('user_close')
    expect(templateApplyStoreMock.confirmCloseAndCleanup).toHaveBeenCalledWith('user_close')
    expect(wrapper.findComponent(ModalStub).exists()).toBe(true)
  })

  it('asks confirmation from the desktop cancel entry before cleanup', async () => {
    templateApplyStoreMock.requestClose.mockResolvedValue({
      status: 'confirm_required',
      trigger: 'user_close',
      confirmReason: 'dirty'
    })
    confirmTemplateApplyCloseMock.mockResolvedValue(true)

    const wrapper = mountHost()
    wrapper.findComponent(ModalStub).vm.$emit('cancel')
    await nextTick()
    await flushPromises()

    expect(templateApplyStoreMock.requestClose).toHaveBeenCalledWith('user_close')
    expect(confirmTemplateApplyCloseMock).toHaveBeenCalledWith('dirty')
    expect(templateApplyStoreMock.confirmCloseAndCleanup).toHaveBeenCalledWith('user_close')
  })

  it('asks confirmation from the mobile drawer close entry before cleanup', async () => {
    isMobileRef.value = true
    templateApplyStoreMock.requestClose.mockResolvedValue({
      status: 'confirm_required',
      trigger: 'gesture_close',
      confirmReason: 'uploading'
    })
    confirmTemplateApplyCloseMock.mockResolvedValue(true)

    const wrapper = mountHost()
    wrapper.findComponent(DrawerStub).vm.$emit('close')
    await nextTick()
    await flushPromises()

    expect(templateApplyStoreMock.requestClose).toHaveBeenCalledWith('gesture_close')
    expect(confirmTemplateApplyCloseMock).toHaveBeenCalledWith('uploading')
    expect(templateApplyStoreMock.confirmCloseAndCleanup).toHaveBeenCalledWith('gesture_close')
  })

  it('wires the scroll lock hook with the provided content ref and visibility state', () => {
    mountHost()

    expect(useWorkbenchScrollLockMock).toHaveBeenCalledTimes(1)
    const [contentRefArg, activeRefArg] = useWorkbenchScrollLockMock.mock.calls[0]
    expect(contentRefArg.value).toBeInstanceOf(HTMLElement)
    expect(activeRefArg.value).toBe(true)
  })

  it('renders the scail2 template panel when selected', async () => {
    templateApplyStoreMock.panelKind = 'scail2Video'
    templateApplyStoreMock.context = {
      rawTaskType: 'scail2_action_transfer'
    }

    const wrapper = mountHost()
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.scail2-video').exists()).toBe(true)
  })

  it('renders the workbench title from i18n in english', () => {
    i18n.global.locale.value = 'en'
    templateApplyStoreMock.featureTitleKey = '' as any

    const wrapper = mountHost()

    expect(wrapper.findComponent(ModalStub).attributes('data-title')).toBe('Template Workbench')
  })
})
