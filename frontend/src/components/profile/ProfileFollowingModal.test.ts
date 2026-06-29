// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import i18n from '@/i18n'
import ProfileFollowingModal from '@/components/profile/ProfileFollowingModal.vue'
import type { PublicUserSummary } from '@/types/social'

const {
  getMyFollowersMock,
  getMyFollowingMock,
  followUserMock,
  unfollowUserMock,
} = vi.hoisted(() => ({
  getMyFollowersMock: vi.fn(),
  getMyFollowingMock: vi.fn(),
  followUserMock: vi.fn(),
  unfollowUserMock: vi.fn(),
}))

vi.mock('@/api/social', () => ({
  getMyFollowers: getMyFollowersMock,
  getMyFollowing: getMyFollowingMock,
  followUser: followUserMock,
  unfollowUser: unfollowUserMock,
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

const userProfileModalStub = defineComponent({
  name: 'UserProfileModal',
  template: '<div data-testid="user-profile-modal" />',
})

function buildUser(overrides: Partial<PublicUserSummary>): PublicUserSummary {
  return {
    id: 2,
    author_name: 'Fan One',
    username: 'fan-one',
    user_group: '凡人',
    current_identity: '外门弟子',
    checkin_count: 1,
    total_public_posts: 0,
    followers_count: 0,
    following_count: 0,
    is_following: false,
    is_self: false,
    ...overrides,
  }
}

function mountModal(mode: 'following' | 'followers') {
  return mount(ProfileFollowingModal, {
    props: {
      open: true,
      mode,
    },
    global: {
      plugins: [i18n],
      stubs: {
        'a-modal': modalStub,
        'a-spin': slotStub('ASpinStub'),
        'a-button': buttonStub,
        UserProfileModal: userProfileModalStub,
      },
      renderStubDefaultSlot: true,
    },
  })
}

describe('ProfileFollowingModal', () => {
  beforeEach(() => {
    getMyFollowersMock.mockReset()
    getMyFollowingMock.mockReset()
    followUserMock.mockReset()
    unfollowUserMock.mockReset()
  })

  it('closes from the top-left profile back button', async () => {
    getMyFollowersMock.mockResolvedValue({
      items: [],
      total: 0,
    })

    const wrapper = mountModal('followers')
    await flushPromises()

    const backButton = wrapper.find('[data-testid="profile-back-button"]')
    expect(backButton.exists()).toBe(true)

    await backButton.trigger('click')

    expect(wrapper.emitted('update:open')?.at(-1)).toEqual([false])
  })

  it('loads followers and lets the user follow back', async () => {
    getMyFollowersMock.mockResolvedValue({
      items: [
        buildUser({ id: 2, author_name: 'Fan One', is_following: false }),
        buildUser({ id: 3, author_name: 'Fan Two', is_following: true }),
      ],
      total: 2,
    })
    followUserMock.mockResolvedValue({ success: true, is_following: true })

    const wrapper = mountModal('followers')
    await flushPromises()

    expect(getMyFollowersMock).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('我的粉丝')
    expect(wrapper.text()).toContain('回关')
    expect(wrapper.text()).toContain('取消关注')

    const followBackButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('回关'))
    expect(followBackButton).toBeTruthy()

    await followBackButton!.trigger('click')
    await flushPromises()

    expect(followUserMock).toHaveBeenCalledWith(2)
    expect(wrapper.emitted('followUpdated')?.at(-1)).toEqual([
      { userId: 2, isFollowing: true },
    ])
  })

  it('keeps existing following list behavior when unfollowing', async () => {
    getMyFollowingMock.mockResolvedValue({
      items: [
        buildUser({ id: 4, author_name: 'Followed User', is_following: true }),
      ],
      total: 1,
    })
    unfollowUserMock.mockResolvedValue({ success: true, is_following: false })

    const wrapper = mountModal('following')
    await flushPromises()

    expect(getMyFollowingMock).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Followed User')

    const unfollowButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('取消关注'))
    expect(unfollowButton).toBeTruthy()

    await unfollowButton!.trigger('click')
    await flushPromises()

    expect(unfollowUserMock).toHaveBeenCalledWith(4)
    expect(wrapper.text()).not.toContain('Followed User')
  })
})
