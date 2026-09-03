import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import MediaItem from './MediaItem.vue'

const clientMocks = vi.hoisted(() => ({
  get: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: { get: clientMocks.get },
}))

const ModalStub = defineComponent({
  name: 'AModal',
  props: {
    open: Boolean,
  },
  emits: ['update:open'],
  template: '<div v-if="open" data-testid="media-modal"><slot /></div>',
})

const ImageStub = defineComponent({
  name: 'AImage',
  inheritAttrs: false,
  props: {
    src: String,
    preview: [Boolean, Object],
  },
  template: '<img data-testid="media-image" :src="src" />',
})

interface MediaProps {
  file: string
  url: string
  previewUrl?: string
  kind?: 'image' | 'video' | 'audio'
  resolveUrl?: string
}

const mountMedia = (props: MediaProps) =>
  mount(MediaItem, {
    props,
    global: {
      components: {
        AModal: ModalStub,
        AImage: ImageStub,
      },
      stubs: {
        PlayCircleOutlined: true,
      },
    },
  })

describe('MediaItem lightweight previews', () => {
  it('does not attach the original video until the in-page modal opens', async () => {
    const openSpy = vi.spyOn(window, 'open')
    const wrapper = mountMedia({
      file: 'result.mp4',
      url: 'https://media.example/original.mp4',
      previewUrl: 'https://media.example/thumb.jpg',
    })

    expect(wrapper.find('[data-testid="media-video-thumbnail"]').attributes('src')).toBe(
      'https://media.example/thumb.jpg',
    )
    expect(wrapper.find('video').exists()).toBe(false)

    await wrapper.get('[data-testid="media-video-trigger"]').trigger('click')
    await flushPromises()

    wrapper.get('[data-testid="media-video-modal"]')
    expect(wrapper.get('video').attributes('src')).toBe(
      'https://media.example/original.mp4',
    )
    expect(openSpy).not.toHaveBeenCalled()
    openSpy.mockRestore()
  })

  it('uses a thumbnail in the table while keeping the original for image preview', () => {
    const wrapper = mountMedia({
      file: 'result.png',
      url: 'https://media.example/original.png',
      previewUrl: 'https://media.example/thumb.webp',
    })

    const image = wrapper.getComponent(ImageStub)
    expect(image.props('src')).toBe('https://media.example/thumb.webp')
    expect(image.props('preview')).toEqual({
      src: 'https://media.example/original.png',
    })
  })

  it('loads reference audio only after the administrator opens its preview', async () => {
    const wrapper = mountMedia({
      file: 'voice.m4a',
      url: 'https://media.example/voice.m4a',
      kind: 'audio',
    })

    expect(wrapper.find('audio').exists()).toBe(false)
    expect(wrapper.get('[data-testid="media-audio-trigger"]').text()).toContain('Audio')

    await wrapper.get('[data-testid="media-audio-trigger"]').trigger('click')
    await nextTick()

    expect(wrapper.get('audio').attributes('src')).toBe(
      'https://media.example/voice.m4a',
    )
  })

  it('resolves an extension input video with authenticated API only when opened', async () => {
    clientMocks.get.mockResolvedValueOnce({
      data: { url: 'https://signed.example/parent.mp4' },
    })
    const wrapper = mountMedia({
      file: 'parent.mp4',
      url: '',
      kind: 'video',
      resolveUrl: '/api/history/media/parent-task',
    })

    expect(clientMocks.get).not.toHaveBeenCalled()
    expect(wrapper.find('video').exists()).toBe(false)

    await wrapper.get('[data-testid="media-video-trigger"]').trigger('click')
    await flushPromises()

    expect(clientMocks.get).toHaveBeenCalledWith('/api/history/media/parent-task')
    expect(wrapper.get('video').attributes('src')).toBe(
      'https://signed.example/parent.mp4',
    )
  })
})
