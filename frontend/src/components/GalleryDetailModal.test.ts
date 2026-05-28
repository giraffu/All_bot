// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'

import GalleryDetailModal from '@/components/GalleryDetailModal.vue'

const AModalStub = defineComponent({
  name: 'AModalStub',
  props: {
    open: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['update:open'],
  template: `
    <div class="a-modal-stub" :data-open="String(open)">
      <slot />
    </div>
  `,
})

const DetailModalShellStub = defineComponent({
  name: 'DetailModalShellStub',
  template: `
    <div class="detail-modal-shell-stub">
      <div class="mobile-header-slot"><slot name="mobile-header" /></div>
      <div class="media-slot"><slot name="media" /></div>
      <div class="info-slot"><slot name="info" /></div>
      <div class="default-slot"><slot /></div>
    </div>
  `,
})

const DetailMediaPreviewStub = defineComponent({
  name: 'DetailMediaPreviewStub',
  template: '<div class="detail-media-preview-stub">media</div>',
})

const DetailCommentsSectionStub = defineComponent({
  name: 'DetailCommentsSectionStub',
  template: '<div class="detail-comments-section-stub">comments</div>',
})

const DetailMobileBottomBarStub = defineComponent({
  name: 'DetailMobileBottomBarStub',
  template: `
    <div class="detail-mobile-bottom-bar-stub">
      <div class="mobile-left-slot"><slot name="left" /></div>
      <div class="mobile-right-slot"><slot name="right" /></div>
    </div>
  `,
})

const DetailDesktopActionsStub = defineComponent({
  name: 'DetailDesktopActionsStub',
  template: `
    <div class="detail-desktop-actions-stub">
      <div class="desktop-top-slot"><slot name="top" /></div>
      <div class="desktop-bottom-slot"><slot name="bottom" /></div>
    </div>
  `,
})

const DetailReactionBarStub = defineComponent({
  name: 'DetailReactionBarStub',
  props: {
    likesCount: {
      type: Number,
      default: 0,
    },
    commentsCount: {
      type: Number,
      default: 0,
    },
  },
  emits: ['like', 'dislike', 'comment'],
  template: `
    <div class="detail-reaction-bar-stub">
      <span class="reaction-meta">{{ likesCount }} / {{ commentsCount }}</span>
      <button class="like-btn" @click="$emit('like')">like</button>
      <button class="dislike-btn" @click="$emit('dislike')">dislike</button>
      <button class="comment-btn" @click="$emit('comment')">comment</button>
    </div>
  `,
})

const DetailApplyActionsStub = defineComponent({
  name: 'DetailApplyActionsStub',
  props: {
    showCopy: {
      type: Boolean,
      default: false,
    },
    copyLabel: {
      type: String,
      default: '',
    },
    applyLabel: {
      type: String,
      default: '',
    },
  },
  emits: ['copy', 'apply'],
  template: `
    <div class="detail-apply-actions-stub">
      <span class="apply-label">{{ applyLabel }}</span>
      <span v-if="showCopy" class="copy-label">{{ copyLabel }}</span>
      <button v-if="showCopy" class="copy-btn" @click="$emit('copy')">copy</button>
      <button class="apply-btn" @click="$emit('apply')">apply</button>
    </div>
  `,
})

const PromptCopyButtonStub = defineComponent({
  name: 'PromptCopyButtonStub',
  props: {
    label: {
      type: String,
      default: '',
    },
  },
  emits: ['click'],
  template: `
    <button class="prompt-copy-button-stub" @click="$emit('click')">
      {{ label }}
    </button>
  `,
})

const PromptPreviewPanelStub = defineComponent({
  name: 'PromptPreviewPanelStub',
  props: {
    title: {
      type: String,
      default: '',
    },
    prompt: {
      type: String,
      default: '',
    },
    showCopy: {
      type: Boolean,
      default: false,
    },
    copyLabel: {
      type: String,
      default: '',
    },
  },
  emits: ['copy'],
  template: `
    <div class="prompt-preview-panel-stub">
      <span class="prompt-preview-title">{{ title }}</span>
      <span class="prompt-preview-text">{{ prompt }}</span>
      <button v-if="showCopy" class="prompt-preview-copy-btn" @click="$emit('copy')">{{ copyLabel }}</button>
    </div>
  `,
})

const baseProps = {
  open: true,
  currentPost: {
    id: 1,
    tags: ['foo'],
    created_at: '2026-05-20T00:00:00Z',
    width: 1024,
    height: 1024,
    duration: 8,
    likes_count: 2,
    dislikes_count: 1,
    comments_count: 3,
    has_liked: false,
    has_disliked: false,
    prompt: 'demo prompt',
  },
  currentDetailMedia: { src: 'demo.png' },
  hasPrev: false,
  hasNext: false,
  isMobile: false,
  title: '详情标题',
  noTagsText: '无标签',
  formatTag: (tag: string) => tag,
  comments: [],
  commentsLoading: false,
  commentsError: '',
  commentsPage: 1,
  commentsTotal: 0,
  commentsHasMore: false,
  commentInputOpen: false,
  newComment: '',
  submittingComment: false,
}

const mountModal = (props = {}, slots = {}) =>
  mount(GalleryDetailModal, {
    props: {
      ...baseProps,
      ...props,
    },
    slots,
    global: {
      mocks: {
        $t: (key: string) => key,
      },
      stubs: {
        'a-modal': AModalStub,
        AModal: AModalStub,
        DetailModalShell: DetailModalShellStub,
        DetailMediaPreview: DetailMediaPreviewStub,
        DetailCommentsSection: DetailCommentsSectionStub,
        DetailMobileBottomBar: DetailMobileBottomBarStub,
        DetailDesktopActions: DetailDesktopActionsStub,
        DetailReactionBar: DetailReactionBarStub,
        DetailApplyActions: DetailApplyActionsStub,
        PromptCopyButton: PromptCopyButtonStub,
        PromptPreviewPanel: PromptPreviewPanelStub,
      },
    },
  })

describe('GalleryDetailModal', () => {
  it('renders standard actions defaults and forwards callbacks', async () => {
    const onLike = vi.fn()
    const onDislike = vi.fn()
    const onComment = vi.fn()
    const onCopy = vi.fn()
    const onApply = vi.fn()

    const wrapper = mountModal({
      standardActions: {
        showDesktopReaction: true,
        showDesktopApply: true,
        showDesktopCopy: true,
        showMobileReaction: true,
        showMobileApply: true,
        showMobileCopy: true,
        showPromptPanelCopy: true,
        desktopApplyPlacement: 'after',
        desktopApplyInline: true,
        applyLabel: '一键应用',
        copyLabel: '复制提示词',
        onLike,
        onDislike,
        onComment,
        onCopy,
        onApply,
      },
    })

    expect(wrapper.findAll('.detail-reaction-bar-stub')).toHaveLength(2)
    expect(wrapper.findAll('.detail-apply-actions-stub')).toHaveLength(2)
    expect(wrapper.find('.prompt-copy-button-stub').text()).toContain('复制提示词')
    expect(wrapper.find('.prompt-preview-panel-stub').text()).toContain('demo prompt')
    expect(wrapper.text()).toContain('一键应用')

    const likeButtons = wrapper.findAll('.like-btn')
    const dislikeButtons = wrapper.findAll('.dislike-btn')
    const commentButtons = wrapper.findAll('.comment-btn')
    const copyButtons = wrapper.findAll('.copy-btn')
    const applyButtons = wrapper.findAll('.apply-btn')

    await likeButtons[0].trigger('click')
    await dislikeButtons[0].trigger('click')
    await commentButtons[0].trigger('click')
    await wrapper.get('.prompt-preview-copy-btn').trigger('click')
    await wrapper.get('.prompt-copy-button-stub').trigger('click')
    await copyButtons[0].trigger('click')
    await applyButtons[0].trigger('click')

    expect(onLike).toHaveBeenCalledTimes(1)
    expect(onDislike).toHaveBeenCalledTimes(1)
    expect(onComment).toHaveBeenCalledTimes(1)
    expect(onCopy).toHaveBeenCalledTimes(3)
    expect(onApply).toHaveBeenCalledTimes(1)
  })

  it('keeps defaults while appending extra slots', () => {
    const wrapper = mountModal(
      {
        standardActions: {
          showDesktopReaction: true,
          showDesktopApply: true,
          showDesktopCopy: true,
          showMobileReaction: true,
          showMobileApply: true,
          showMobileCopy: true,
          desktopApplyPlacement: 'after',
          applyLabel: '一键应用',
          copyLabel: '复制提示词',
        },
      },
      {
        'before-comments-extra': '<div class="before-extra">before-extra</div>',
        'after-comments-extra': '<div class="after-extra">after-extra</div>',
        'mobile-left-extra': '<div class="mobile-left-extra">mobile-left-extra</div>',
        'mobile-right-extra': '<div class="mobile-right-extra">mobile-right-extra</div>',
      },
    )

    expect(wrapper.findAll('.detail-reaction-bar-stub')).toHaveLength(2)
    expect(wrapper.findAll('.detail-apply-actions-stub')).toHaveLength(2)
    expect(wrapper.find('.before-extra').exists()).toBe(true)
    expect(wrapper.find('.after-extra').exists()).toBe(true)
    expect(wrapper.find('.mobile-left-extra').exists()).toBe(true)
    expect(wrapper.find('.mobile-right-extra').exists()).toBe(true)
  })
})
