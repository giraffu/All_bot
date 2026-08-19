import { onMounted, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import Modal from 'ant-design-vue/es/modal'
import {
  adminGiftPlan,
  clearUserHistory,
  deleteUser,
  fetchPlans,
  fetchUserStats,
  fetchUsers,
  transferUserData,
  updateUserChannelMember,
  updateUserCredits,
  updateUserGroup,
  updateUserIdentity,
  updateUserSubmissionBan,
  updateUserAlipayDirect,
} from '../api/api'

export interface DashboardUserRecord {
  id: number
  full_name?: string | null
  username?: string | null
  credits?: number
  checkin_count?: number | null
  current_identity?: string | null
  identity_expire_at?: string | null
  user_group?: string | null
  is_channel_member?: boolean | null
  is_submission_banned?: boolean | null
  alipay_direct_enabled?: boolean | null
  submission_ban_reason?: string | null
  submission_banned_at?: string | null
  [key: string]: unknown
}

interface DashboardPlan {
  id: number
  is_active?: boolean
  [key: string]: unknown
}

interface TransferTargetOption {
  value: number
  label: string
  raw: DashboardUserRecord
}

interface GiftForm {
  plan_id: number | null
  note: string
}

interface PaginationState {
  current?: number
  pageSize?: number
}

interface SorterItem {
  field?: string
  columnKey?: string
  column?: {
    key?: string
  }
  order?: string | null
}

type SorterState = SorterItem | SorterItem[] | null | undefined
type SortOrder = 'asc' | 'desc'
type FormatDateFn = (value: string | null | undefined) => string

interface ApiErrorLike {
  response?: {
    data?: {
      detail?: string
    }
  }
  message?: string
}

const errorMessage = (err: unknown) => {
  const apiError = err as ApiErrorLike
  return apiError.response?.data?.detail || apiError.message || String(err)
}

export function useUserTableState(formatDate: FormatDateFn) {
  const DEFAULT_SORT_BY = 'created_at'
  const DEFAULT_SORT_ORDER: SortOrder = 'desc'
  const users = ref<DashboardUserRecord[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const currentPage = ref(1)
  const pageSize = ref(20)
  const totalUsers = ref(0)
  const searchUserId = ref('')
  const searchQuery = ref('')
  const isQueryPartial = ref(true)
  const filterIdentity = ref<string | null>(null)
  const filterUserGroup = ref<string | null>(null)
  const filterSubmissionBanned = ref(false)
  const filterAlipayDirect = ref<string | null>(null)
  const searchUsername = ref('')
  const isUsernamePartial = ref(true)
  const sortBy = ref(DEFAULT_SORT_BY)
  const sortOrder = ref<SortOrder>(DEFAULT_SORT_ORDER)
  const searchTimeout = ref<ReturnType<typeof window.setTimeout> | null>(null)
  let latestUsersRequestId = 0

  const statsModalVisible = ref(false)
  const statsLoading = ref(false)
  const currentUserStats = ref<Record<string, unknown> | null>(null)
  const currentUser = ref<DashboardUserRecord | null>(null)

  const editCreditsVisible = ref(false)
  const currentEditingUser = ref<DashboardUserRecord | null>(null)
  const newCreditsValue = ref(0)
  const newCheckinCountValue = ref(0)
  const updatingCredits = ref(false)

  const giftModalVisible = ref(false)
  const currentGiftUser = ref<DashboardUserRecord | null>(null)
  const availablePlans = ref<DashboardPlan[]>([])
  const giftForm = ref<GiftForm>({
    plan_id: null,
    note: '后台手动赠送',
  })
  const giftingPlan = ref(false)

  const editIdentityVisible = ref(false)
  const currentIdentityUser = ref<DashboardUserRecord | null>(null)
  const newIdentityValue = ref('外门弟子')
  const newExpireAtValue = ref<string | null>(null)
  const autoConvertIdentity = ref(true)
  const updatingIdentity = ref(false)

  const editGroupVisible = ref(false)
  const updatingGroup = ref(false)
  const currentGroupUser = ref<DashboardUserRecord | null>(null)
  const newGroupValue = ref('凡人')

  const editChannelMemberVisible = ref(false)
  const updatingChannelMember = ref(false)
  const currentChannelMemberUser = ref<DashboardUserRecord | null>(null)
  const newChannelMemberValue = ref(false)
  const transferModalVisible = ref(false)
  const transferringData = ref(false)
  const transferSearchLoading = ref(false)
  const currentTransferSourceUser = ref<DashboardUserRecord | null>(null)
  const transferTargetUserId = ref<number | null>(null)
  const transferTargetKeyword = ref('')
  const transferTargetOptions = ref<TransferTargetOption[]>([])
  const transferConfirmText = ref('')
  const transferNote = ref('后台用户数据转移')
  let latestTransferSearchId = 0

  const allIdentities = [
    '外门弟子',
    '内门弟子',
    '核心弟子',
    '真传弟子',
  ]

  const normalizeSorterOrder = (order: string | null | undefined): SortOrder => {
    if (order === 'ascend') return 'asc'
    if (order === 'descend') return 'desc'
    return DEFAULT_SORT_ORDER
  }

  const resolveSorterField = (sorter: SorterState): string => {
    if (Array.isArray(sorter)) {
      return resolveSorterField(sorter[0])
    }
    return String(sorter?.field || sorter?.columnKey || sorter?.column?.key || DEFAULT_SORT_BY)
  }

  const loadUsersData = async () => {
    const requestId = ++latestUsersRequestId
    loading.value = true
    error.value = null

    try {
      const paramsObj = {
        user_id: searchUserId.value || null,
        query: searchQuery.value,
        query_partial: isQueryPartial.value,
        identity: filterIdentity.value,
        user_group: filterUserGroup.value,
        submission_banned: filterSubmissionBanned.value ? true : null,
        alipay_direct_enabled:
          filterAlipayDirect.value === 'enabled'
            ? true
            : filterAlipayDirect.value === 'disabled'
              ? false
              : null,
        username: searchUsername.value,
        username_partial: isUsernamePartial.value,
        sort_by: sortBy.value,
        sort_order: sortOrder.value,
      }
      const res = await fetchUsers(currentPage.value, pageSize.value, paramsObj)
      if (requestId !== latestUsersRequestId) {
        return
      }
      users.value = res.items || []
      totalUsers.value = res.total || 0
    } catch (err) {
      if (requestId !== latestUsersRequestId) {
        return
      }
      console.error('Failed to load users:', err)
      error.value = '加载用户列表失败'
    } finally {
      if (requestId === latestUsersRequestId) {
        loading.value = false
      }
    }
  }

  const handleTableChange = (
    pagination: PaginationState,
    _filters: unknown,
    sorter: SorterState,
  ) => {
    const nextSortBy = resolveSorterField(sorter)
    const nextSortOrder = normalizeSorterOrder(
      Array.isArray(sorter) ? sorter[0]?.order : sorter?.order
    )
    const sortChanged = nextSortBy !== sortBy.value || nextSortOrder !== sortOrder.value

    currentPage.value = sortChanged ? 1 : pagination.current || 1
    pageSize.value = pagination.pageSize || pageSize.value
    sortBy.value = nextSortBy
    sortOrder.value = nextSortOrder
    void loadUsersData()
  }

  const onSearchInput = () => {
    if (searchTimeout.value) window.clearTimeout(searchTimeout.value)
    searchTimeout.value = window.setTimeout(() => {
      currentPage.value = 1
      void loadUsersData()
    }, 500)
  }

  const handleViewStats = async (record: DashboardUserRecord) => {
    currentUser.value = record
    statsModalVisible.value = true
    statsLoading.value = true
    currentUserStats.value = null
    try {
      currentUserStats.value = await fetchUserStats(record.id)
    } catch (err) {
      message.error('获取统计数据失败: ' + errorMessage(err))
    } finally {
      statsLoading.value = false
    }
  }

  const handleEditCredits = (record: DashboardUserRecord) => {
    currentEditingUser.value = record
    newCreditsValue.value = Number(record.credits || 0)
    newCheckinCountValue.value = record.checkin_count || 0
    editCreditsVisible.value = true
  }

  const saveCredits = async () => {
    if (!currentEditingUser.value) return

    updatingCredits.value = true
    try {
      await updateUserCredits(
        currentEditingUser.value.id,
        newCreditsValue.value,
        newCheckinCountValue.value
      )
      message.success(`用户 ${currentEditingUser.value.id} 数据已更新`)
      editCreditsVisible.value = false
      await loadUsersData()
    } catch (err) {
      message.error('更新失败: ' + errorMessage(err))
    } finally {
      updatingCredits.value = false
    }
  }

  const handleClearHistory = (record: DashboardUserRecord) => {
    Modal.confirm({
      title: '确认清除数据？',
      content: `这将永久删除用户 ${record.full_name || record.id} 的所有历史记录（包括图片和Prompt），但会保留灵石和邀请信息。此操作不可撤销。`,
      okText: '确认清除',
      okType: 'danger',
      cancelText: '取消',
      async onOk() {
        try {
          await clearUserHistory(record.id)
          message.success('用户历史数据已成功清除')
          await loadUsersData()
        } catch (err) {
          message.error('清除数据失败: ' + errorMessage(err))
        }
      },
    })
  }

  const handleDeleteUser = (record: DashboardUserRecord) => {
    Modal.confirm({
      title: '确认彻底删除用户？',
      content: `这将从数据库中永久移除用户 ${record.full_name || record.id} 的所有信息（包括身份组、灵石、签到记录、生成历史等）。用户重新启动机器人后将作为全新的“凡人”身份加入。此操作不可撤销！`,
      okText: '确认彻底删除',
      okType: 'danger',
      cancelText: '取消',
      async onOk() {
        try {
          await deleteUser(record.id)
          message.success('用户及其所有关联数据已成功从数据库移除')
          await loadUsersData()
        } catch (err) {
          message.error('删除用户失败: ' + errorMessage(err))
        }
      },
    })
  }

  const handleEditIdentity = (record: DashboardUserRecord) => {
    currentIdentityUser.value = record
    newIdentityValue.value = record.current_identity || '外门弟子'
    newExpireAtValue.value = null
    autoConvertIdentity.value = true
    editIdentityVisible.value = true
  }

  const handleEditGroup = (record: DashboardUserRecord) => {
    currentGroupUser.value = record
    newGroupValue.value = record.user_group || '凡人'
    editGroupVisible.value = true
  }

  const handleEditChannelMember = (record: DashboardUserRecord) => {
    currentChannelMemberUser.value = record
    newChannelMemberValue.value = !!record.is_channel_member
    editChannelMemberVisible.value = true
  }

  const handleToggleSubmissionBan = (record: DashboardUserRecord) => {
    const nextStatus = !record.is_submission_banned
    const targetName = record.full_name || record.username || record.id
    Modal.confirm({
      title: nextStatus ? '确认禁止该用户投稿？' : '确认解除该用户投稿封禁？',
      content: nextStatus
        ? `封禁后，用户在 Bot 端和 Web 端点击投稿相关功能时，都会提示“违禁被封，请联系管理员解封”。目标用户：${targetName}`
        : `解除后，用户将恢复 Bot 端和 Web 端的投稿能力。目标用户：${targetName}`,
      okText: nextStatus ? '确认封禁' : '确认解封',
      okType: nextStatus ? 'danger' : 'primary',
      cancelText: '取消',
      async onOk() {
        try {
          const res = await updateUserSubmissionBan(record.id, nextStatus)
          message.success(
            nextStatus
              ? `用户 ${record.id} 已禁止投稿`
              : `用户 ${record.id} 已解除投稿封禁`
          )
          record.is_submission_banned = !!res.is_submission_banned
          record.submission_ban_reason = res.submission_ban_reason || null
          record.submission_banned_at = res.submission_banned_at || null
          await loadUsersData()
        } catch (err) {
          message.error('更新失败: ' + errorMessage(err))
        }
      },
    })
  }

  const handleToggleAlipayDirect = (record: DashboardUserRecord) => {
    const nextStatus = !record.alipay_direct_enabled
    const targetName = record.full_name || record.username || record.id
    Modal.confirm({
      title: nextStatus ? '确认开启支付宝直连？' : '确认关闭支付宝直连？',
      content: nextStatus
        ? `开启后，该用户新建的支付宝订单将在全局开关开启时走支付宝官方直连。微信订单不受影响。目标用户：${targetName}`
        : `关闭后，该用户的新支付宝订单将恢复走环宇；已有订单仍按创建时的提供方处理。目标用户：${targetName}`,
      okText: nextStatus ? '确认开启' : '确认关闭',
      okType: nextStatus ? 'primary' : 'danger',
      cancelText: '取消',
      async onOk() {
        try {
          const result = await updateUserAlipayDirect(record.id, nextStatus)
          record.alipay_direct_enabled = !!result.alipay_direct_enabled
          message.success(
            nextStatus
              ? `用户 ${record.id} 已开启支付宝直连`
              : `用户 ${record.id} 已关闭支付宝直连`
          )
          await loadUsersData()
        } catch (err) {
          message.error('更新支付宝直连失败: ' + errorMessage(err))
        }
      },
    })
  }

  const searchTransferTargets = async (keyword = '') => {
    const sourceUserId = currentTransferSourceUser.value?.id
    if (!sourceUserId) {
      transferTargetOptions.value = []
      return
    }

    const requestId = ++latestTransferSearchId
    transferSearchLoading.value = true
    transferTargetKeyword.value = keyword
    try {
      const res = await fetchUsers(1, 12, {
        query: keyword || null,
        query_partial: true,
      })
      if (requestId !== latestTransferSearchId) {
        return
      }
      transferTargetOptions.value = (res.items || [])
        .filter((user: DashboardUserRecord) => user.id !== sourceUserId)
        .map((user: DashboardUserRecord) => ({
          value: user.id,
          label: `${user.full_name || '未知用户'} (@${user.username || 'n/a'}) [ID:${user.id}]`,
          raw: user,
        }))
    } catch (err) {
      if (requestId !== latestTransferSearchId) {
        return
      }
      console.error('Failed to search transfer targets:', err)
      message.error('加载目标用户失败')
    } finally {
      if (requestId === latestTransferSearchId) {
        transferSearchLoading.value = false
      }
    }
  }

  const handleTransferData = async (record: DashboardUserRecord) => {
    currentTransferSourceUser.value = record
    transferTargetUserId.value = null
    transferTargetKeyword.value = ''
    transferTargetOptions.value = []
    transferConfirmText.value = ''
    transferNote.value = '后台用户数据转移'
    transferModalVisible.value = true
    await searchTransferTargets('')
  }

  const submitTransfer = async () => {
    if (!currentTransferSourceUser.value) return
    if (!transferTargetUserId.value) {
      message.warning('请先选择目标用户')
      return
    }
    if (String(transferConfirmText.value).trim() !== String(currentTransferSourceUser.value.id)) {
      message.warning(`请输入源用户 ID ${currentTransferSourceUser.value.id} 以确认转移`)
      return
    }

    transferringData.value = true
    try {
      const result = await transferUserData(
        currentTransferSourceUser.value.id,
        transferTargetUserId.value,
        transferNote.value || '后台用户数据转移'
      )
      message.success(result.message || '用户数据转移成功')
      transferModalVisible.value = false
      await loadUsersData()
    } catch (err) {
      message.error('转移数据失败: ' + errorMessage(err))
    } finally {
      transferringData.value = false
    }
  }

  const saveIdentity = async () => {
    if (!currentIdentityUser.value) return

    updatingIdentity.value = true
    try {
      const res = await updateUserIdentity(
        currentIdentityUser.value.id,
        newIdentityValue.value,
        newExpireAtValue.value,
        autoConvertIdentity.value
      )
      const newExpireStr = res.identity_expire_at ? formatDate(res.identity_expire_at) : '永不过期'
      message.success(`用户 ${currentIdentityUser.value.id} 身份已更新为 ${res.current_identity}，到期时间：${newExpireStr}`)
      editIdentityVisible.value = false
      await loadUsersData()
    } catch (err) {
      message.error('更新失败: ' + errorMessage(err))
    } finally {
      updatingIdentity.value = false
    }
  }

  const saveGroup = async () => {
    if (!currentGroupUser.value) return

    updatingGroup.value = true
    try {
      const res = await updateUserGroup(
        currentGroupUser.value.id,
        newGroupValue.value
      )
      message.success(`用户 ${currentGroupUser.value.id} 修为已更新为 ${res.user_group}`)
      editGroupVisible.value = false
      await loadUsersData()
    } catch (err) {
      message.error('更新失败: ' + errorMessage(err))
    } finally {
      updatingGroup.value = false
    }
  }

  const saveChannelMember = async () => {
    if (!currentChannelMemberUser.value) return

    updatingChannelMember.value = true
    try {
      await updateUserChannelMember(
        currentChannelMemberUser.value.id,
        newChannelMemberValue.value
      )
      message.success(`用户 ${currentChannelMemberUser.value.id} 宗门状态已更新`)
      editChannelMemberVisible.value = false
      await loadUsersData()
    } catch (err) {
      message.error('更新失败: ' + errorMessage(err))
    } finally {
      updatingChannelMember.value = false
    }
  }

  const loadPlans = async () => {
    try {
      const res = await fetchPlans()
      availablePlans.value = res.filter((plan: DashboardPlan) => plan.is_active)
    } catch (err) {
      console.error('Failed to load plans:', err)
    }
  }

  const handleGiftPlan = (record: DashboardUserRecord) => {
    currentGiftUser.value = record
    giftForm.value = {
      plan_id: availablePlans.value.length > 0 ? availablePlans.value[0].id : null,
      note: '后台手动赠送',
    }
    giftModalVisible.value = true
  }

  const submitGift = async () => {
    if (!giftForm.value.plan_id) {
      message.warning('请选择一个套餐')
      return
    }

    giftingPlan.value = true
    try {
      if (!currentGiftUser.value) return
      await adminGiftPlan(currentGiftUser.value.id, giftForm.value.plan_id, giftForm.value.note)
      message.success(`成功为用户 ${currentGiftUser.value.id} 赠送套餐`)
      giftModalVisible.value = false
      await loadUsersData()
    } catch (err) {
      message.error('赠送套餐失败: ' + errorMessage(err))
    } finally {
      giftingPlan.value = false
    }
  }

  onMounted(() => {
    void loadPlans()
    void loadUsersData()
  })

  return {
    users,
    loading,
    error,
    currentPage,
    pageSize,
    totalUsers,
    searchUserId,
    searchQuery,
    isQueryPartial,
    filterIdentity,
    filterUserGroup,
    filterSubmissionBanned,
    filterAlipayDirect,
    searchUsername,
    isUsernamePartial,
    sortBy,
    sortOrder,
    statsModalVisible,
    statsLoading,
    currentUserStats,
    currentUser,
    editCreditsVisible,
    currentEditingUser,
    newCreditsValue,
    newCheckinCountValue,
    updatingCredits,
    giftModalVisible,
    currentGiftUser,
    availablePlans,
    giftForm,
    giftingPlan,
    editIdentityVisible,
    currentIdentityUser,
    newIdentityValue,
    newExpireAtValue,
    autoConvertIdentity,
    updatingIdentity,
    editGroupVisible,
    updatingGroup,
    currentGroupUser,
    newGroupValue,
    editChannelMemberVisible,
    updatingChannelMember,
    currentChannelMemberUser,
    newChannelMemberValue,
    transferModalVisible,
    transferringData,
    transferSearchLoading,
    currentTransferSourceUser,
    transferTargetUserId,
    transferTargetKeyword,
    transferTargetOptions,
    transferConfirmText,
    transferNote,
    allIdentities,
    handleTableChange,
    onSearchInput,
    handleViewStats,
    handleEditCredits,
    saveCredits,
    handleClearHistory,
    handleDeleteUser,
    handleEditIdentity,
    handleEditGroup,
    handleEditChannelMember,
    handleToggleSubmissionBan,
    handleToggleAlipayDirect,
    saveIdentity,
    saveGroup,
    saveChannelMember,
    searchTransferTargets,
    handleTransferData,
    submitTransfer,
    handleGiftPlan,
    submitGift,
  }
}
