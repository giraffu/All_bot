// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import i18n from '@/i18n'
import UserProfileModal from '@/components/UserProfileModal.vue'
import type { GalleryPost, PaginatedGalleryResponse } from '@/types/gallery'
import type { PublicUserProfileResponse } from '@/types/social'

const {
  getPublicUserProfileMock,
  followUserMock,
  unfollowUserMock,
  unlockGalleryPromptMock,
  updateBalanceMock,
  templateApplyStoreMock,
} = vi.hoisted(() => ({
  getPublicUserProfileMock: vi.fn(),
  followUserMock: vi.fn(),
  unfollowUserMock: vi.fn(),
  unlockGalleryPromptMock: vi.fn(),
  updateBalanceMock: vi.fn(),
  templateApplyStoreMock: {
    requestClose: vi.fn(),
    openFromRawContext: vi.fn(),
    confirmCloseAndCleanup: vi.fn(),
  },
}))

vi.mock('@/api/social', () => ({
  getPublicUserProfile: getPublicUserProfileMock,
  followUser: followUserMock,
  unfollowUser: unfollowUserMock,
}))

vi.mock('@/api/gallery', () => ({
  unlockGalleryPrompt: unlockGalleryPromptMock,
  getGalleryCommentsPage: vi.fn().mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    size: 20,
    pages: 0,
  }),
  getUnifiedApplyContext: vi.fn(),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    updateBalance: updateBalanceMock,
  }),
}))

vi.mock('@/stores/templateApply', () => ({
  useTemplateApplyStore: () => templateApplyStoreMock,
}))

vi.mock('@/composables/useViewport', async () => {
  const { ref } = await vi.importActual<typeof import('vue')>('vue')
  return {
    useViewport: () => ({
      isMobile: ref(false),
    }),
  }
})

vi.mock('ant-design-vue', async () => {
  const actual = await vi.importActual<object>('ant-design-vue')
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  }
})

const slotStub = (name: string) =>
  defineComponent({
    name,
    template: '<div><slot /></div>',
  })

const modalStub = defineComponent({
  name: 'AModalStub',
  props: {
    open: Boolean,
  },
  template: '<div v-if="open"><slot /></div>',
})

const buttonStub = defineComponent({
  name: 'AButtonStub',
  emits: ['click'],
  template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
})

const mediaCardStub = defineComponent({
  name: 'GalleryMediaCard',
  props: {
    item: {
      type: Object,
      required: true,
    },
  },
  emits: ['card-click'],
  template: `
    <button type="button" data-testid="media-card" @click="$emit('card-click')">
      {{ item.task_id }}
      <span data-testid="media-src">{{ item.src }}</span>
    </button>
  `,
})

const detailModalStub = defineComponent({
  name: 'GalleryDetailModal',
  props: {
    open: Boolean,
    currentPost: Object,
    standardActions: Object,
  },
  template: `
    <div v-if="open" data-testid="detail-modal">
      <span data-testid="detail-prompt">{{ currentPost?.prompt }}</span>
      <button
        v-if="standardActions?.showPromptPanelUnlock"
        type="button"
        data-testid="unlock-prompt"
        @click="standardActions.onUnlockPrompt()"
      >
        {{ standardActions.unlockLabel }}
      </button>
    </div>
  `,
})

const pagedNavigationStub = defineComponent({
  name: 'PagedNavigation',
  emits: ['change'],
  template: '<button type="button" data-testid="next-page" @click="$emit(\'change\', 2)">next</button>',
})

function buildPost(overrides: Partial<GalleryPost>): GalleryPost {
  return {
    id: 1,
    task_id: 'task-1',
    media_type: 'image',
    width: null,
    height: null,
    duration: null,
    tags: [],
    likes_count: 0,
    dislikes_count: 0,
    applied_count: 0,
    comments_count: 0,
    thumbnail_url: 'thumb.jpg',
    media_url: 'media.jpg',
    created_at: '2026-06-29T00:00:00',
    has_liked: false,
    has_disliked: false,
    author_id: 9,
    is_active: true,
    prompt: null,
    ...overrides,
  }
}

function buildProfileResponse(posts: PaginatedGalleryResponse<GalleryPost>): PublicUserProfileResponse {
  return {
    user: {
      id: 9,
      author_name: 'Author',
      username: 'author',
      user_group: '凡人',
      current_identity: '外门弟子',
      checkin_count: 3,
      total_public_posts: posts.total,
      followers_count: 2,
      following_count: 1,
      is_following: false,
      is_self: false,
    },
    posts,
    recent_posts: posts.items,
  }
}

function mountModal() {
  return mount(UserProfileModal, {
    props: {
      open: true,
      userId: 9,
    },
    global: {
      plugins: [i18n],
      stubs: {
        'a-modal': modalStub,
        'a-spin': slotStub('ASpinStub'),
        'a-button': buttonStub,
        GalleryMediaCard: mediaCardStub,
        GalleryDetailModal: detailModalStub,
        OriginalInputBadge: true,
        PagedNavigation: pagedNavigationStub,
      },
      renderStubDefaultSlot: true,
    },
  })
}

describe('UserProfileModal', () => {
  beforeEach(() => {
    getPublicUserProfileMock.mockReset()
    followUserMock.mockReset()
    unfollowUserMock.mockReset()
    unlockGalleryPromptMock.mockReset()
    updateBalanceMock.mockReset()

    getPublicUserProfileMock.mockImplementation((_userId: number, params: { page?: number }) => {
      const page = params?.page ?? 1
      if (page === 2) {
        return Promise.resolve(buildProfileResponse({
          items: [buildPost({ id: 2, task_id: 'task-page-2' })],
          total: 13,
          page: 2,
          size: 12,
          pages: 2,
        }))
      }
      return Promise.resolve(buildProfileResponse({
        items: [
          buildPost({
            id: 1,
            task_id: 'task-page-1',
            thumbnail_url: '',
            media_url: 'https://r2.example/media-page-1.jpg',
            prompt: 'masked ****',
            prompt_unlocked: false,
            prompt_unlockable: true,
            prompt_is_masked: true,
            prompt_unlock_price: 1,
          }),
        ],
        total: 13,
        page: 1,
        size: 12,
        pages: 2,
      }))
    })

    unlockGalleryPromptMock.mockResolvedValue({
      post_id: 1,
      prompt: 'full prompt',
      prompt_unlocked: true,
      prompt_unlockable: false,
      prompt_is_masked: false,
      prompt_unlock_price: 1,
      current_credits: 8,
      already_unlocked: false,
    })
  })

  it('loads public posts with pagination and switches pages', async () => {
    const wrapper = mountModal()
    await flushPromises()

    expect(getPublicUserProfileMock).toHaveBeenCalledWith(9, { page: 1, size: 12 })
    expect(wrapper.text()).toContain('task-page-1')
    expect(wrapper.get('[data-testid="media-src"]').text()).toContain('media-page-1.jpg')

    await wrapper.get('[data-testid="next-page"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('task-page-2')
  })

  it('shows prompt unlock in profile post detail and updates the prompt', async () => {
    const wrapper = mountModal()
    await flushPromises()

    await wrapper.get('[data-testid="media-card"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="unlock-prompt"]').text()).toContain('1')

    await wrapper.get('[data-testid="unlock-prompt"]').trigger('click')
    await flushPromises()

    expect(unlockGalleryPromptMock).toHaveBeenCalledWith(1)
    expect(updateBalanceMock).toHaveBeenCalledWith(8)
    expect(wrapper.get('[data-testid="detail-prompt"]').text()).toContain('full prompt')
  })
})
