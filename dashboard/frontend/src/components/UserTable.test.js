// @vitest-environment jsdom

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const userTableStateMocks = vi.hoisted(() => ({
  useUserTableState: vi.fn(),
}))

vi.mock('../composables/useUserTableState', () => ({
  useUserTableState: userTableStateMocks.useUserTableState,
}))

vi.mock('./UserTableToolbar.vue', () => ({
  default: {
    name: 'UserTableToolbarStub',
    template: '<div class="toolbar-stub" />',
  },
}))

vi.mock('./UserTableRowActions.vue', () => ({
  default: {
    name: 'UserTableRowActionsStub',
    template: '<div class="row-actions-stub" />',
  },
}))

vi.mock('./UserTableDialogs.vue', () => ({
  default: {
    name: 'UserTableDialogsStub',
    template: '<div class="dialogs-stub" />',
  },
}))

vi.mock('./UserTransferDialog.vue', () => ({
  default: {
    name: 'UserTransferDialogStub',
    template: '<div class="transfer-dialog-stub" />',
  },
}))

const UserTable = await import('./UserTable.vue').then(module => module.default)

const CardStub = defineComponent({
  name: 'ACardStub',
  props: ['title'],
  template: `
    <section class="card-stub">
      <h1>{{ title }}</h1>
      <div class="card-extra"><slot name="extra" /></div>
      <slot />
    </section>
  `,
})

const AlertStub = defineComponent({
  name: 'AAlertStub',
  props: ['message'],
  template: '<div class="alert-stub">{{ message }}</div>',
})

const TableStub = defineComponent({
  name: 'ATableStub',
  props: ['columns', 'dataSource', 'loading', 'pagination', 'scroll'],
  emits: ['change'],
  template: `
    <div class="table-stub" :data-scroll-x="scroll && scroll.x">
      <div v-for="column in columns" :key="column.key" class="table-column">{{ column.title }}</div>
      <div v-for="(record, rowIndex) in dataSource" :key="record.id" class="table-row">
        <div v-for="column in columns" :key="column.key" class="table-cell">
          <slot name="bodyCell" :column="column" :record="record" :index="rowIndex">
            {{ column.dataIndex ? record[column.dataIndex] : '' }}
          </slot>
        </div>
      </div>
    </div>
  `,
})

const TagStub = defineComponent({
  name: 'ATagStub',
  props: ['color'],
  template: '<span class="tag-stub"><slot /></span>',
})

const buildTableState = (overrides = {}) => ({
  users: ref([
    {
      id: 1001,
      full_name: 'Inviter One',
      username: 'inviter1',
      user_group: '凡人',
      current_identity: '外门弟子',
      credits: 6,
      checkin_count: 0,
      referral_count: 3,
      invited_total_usdt: 14.85,
      is_channel_member: false,
      generation_count: 0,
      created_at: null,
      last_activity: null,
    },
    {
      id: 1002,
      full_name: 'Inviter Two',
      username: 'inviter2',
      user_group: '凡人',
      current_identity: '外门弟子',
      credits: 6,
      checkin_count: 0,
      referral_count: 0,
      invited_total_usdt: 0,
      is_channel_member: false,
      generation_count: 0,
      created_at: null,
      last_activity: null,
    },
  ]),
  loading: ref(false),
  error: ref(null),
  currentPage: ref(1),
  pageSize: ref(20),
  totalUsers: ref(2),
  searchUserId: ref(''),
  searchQuery: ref(''),
  isQueryPartial: ref(true),
  filterIdentity: ref(null),
  filterUserGroup: ref(null),
  filterSubmissionBanned: ref(false),
  searchUsername: ref(''),
  isUsernamePartial: ref(true),
  sortBy: ref('created_at'),
  sortOrder: ref('desc'),
  statsModalVisible: ref(false),
  statsLoading: ref(false),
  currentUserStats: ref(null),
  currentUser: ref(null),
  editCreditsVisible: ref(false),
  currentEditingUser: ref(null),
  newCreditsValue: ref(0),
  newCheckinCountValue: ref(0),
  updatingCredits: ref(false),
  giftModalVisible: ref(false),
  currentGiftUser: ref(null),
  availablePlans: ref([]),
  giftForm: ref({ plan_id: null, note: '后台手动赠送' }),
  giftingPlan: ref(false),
  editIdentityVisible: ref(false),
  currentIdentityUser: ref(null),
  newIdentityValue: ref('外门弟子'),
  newExpireAtValue: ref(null),
  autoConvertIdentity: ref(true),
  updatingIdentity: ref(false),
  editGroupVisible: ref(false),
  updatingGroup: ref(false),
  currentGroupUser: ref(null),
  newGroupValue: ref('凡人'),
  editChannelMemberVisible: ref(false),
  updatingChannelMember: ref(false),
  currentChannelMemberUser: ref(null),
  newChannelMemberValue: ref(false),
  transferModalVisible: ref(false),
  transferringData: ref(false),
  transferSearchLoading: ref(false),
  currentTransferSourceUser: ref(null),
  transferTargetUserId: ref(null),
  transferTargetKeyword: ref(''),
  transferTargetOptions: ref([]),
  transferConfirmText: ref(''),
  transferNote: ref('后台用户数据转移'),
  allIdentities: ['外门弟子', '内门弟子', '核心弟子', '真传弟子'],
  handleTableChange: vi.fn(),
  onSearchInput: vi.fn(),
  handleViewStats: vi.fn(),
  handleEditCredits: vi.fn(),
  saveCredits: vi.fn(),
  handleClearHistory: vi.fn(),
  handleDeleteUser: vi.fn(),
  handleEditIdentity: vi.fn(),
  handleEditGroup: vi.fn(),
  handleEditChannelMember: vi.fn(),
  handleToggleSubmissionBan: vi.fn(),
  saveIdentity: vi.fn(),
  saveGroup: vi.fn(),
  saveChannelMember: vi.fn(),
  searchTransferTargets: vi.fn(),
  handleTransferData: vi.fn(),
  submitTransfer: vi.fn(),
  handleGiftPlan: vi.fn(),
  submitGift: vi.fn(),
  ...overrides,
})

const mountUserTable = (state = buildTableState()) => {
  userTableStateMocks.useUserTableState.mockReturnValue(state)
  return mount(UserTable, {
    global: {
      stubs: {
        'a-card': CardStub,
        'a-alert': AlertStub,
        'a-table': TableStub,
        'a-tag': TagStub,
      },
    },
  })
}

describe('UserTable', () => {
  beforeEach(() => {
    userTableStateMocks.useUserTableState.mockReset()
  })

  it('shows invited recharge USDT totals after referral count', () => {
    const wrapper = mountUserTable()

    expect(wrapper.text()).toContain('邀请人数')
    expect(wrapper.text()).toContain('邀请折合(USDT)')
    expect(wrapper.text()).toContain('$ 14.85')
    expect(wrapper.text()).toContain('$ 0.00')
    expect(wrapper.find('.table-stub').attributes('data-scroll-x')).toBe('1540')
  })
})
