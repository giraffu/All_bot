import { onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  adminGiftPlan,
  clearUserHistory,
  deleteUser,
  fetchPlans,
  fetchUserStats,
  fetchUsers,
  updateUserChannelMember,
  updateUserCredits,
  updateUserGroup,
  updateUserIdentity,
} from '../api/api'

export function useUserTableState(formatDate) {
  const users = ref([])
  const loading = ref(false)
  const error = ref(null)

  const currentPage = ref(1)
  const pageSize = ref(20)
  const totalUsers = ref(0)
  const searchQuery = ref('')
  const isQueryPartial = ref(true)
  const filterIdentity = ref(null)
  const filterUserGroup = ref(null)
  const searchUsername = ref('')
  const isUsernamePartial = ref(true)
  const searchTimeout = ref(null)
  let latestUsersRequestId = 0

  const statsModalVisible = ref(false)
  const statsLoading = ref(false)
  const currentUserStats = ref(null)
  const currentUser = ref(null)

  const editCreditsVisible = ref(false)
  const currentEditingUser = ref(null)
  const newCreditsValue = ref(0)
  const newCheckinCountValue = ref(0)
  const updatingCredits = ref(false)

  const giftModalVisible = ref(false)
  const currentGiftUser = ref(null)
  const availablePlans = ref([])
  const giftForm = ref({
    plan_id: null,
    note: '后台手动赠送',
  })
  const giftingPlan = ref(false)

  const editIdentityVisible = ref(false)
  const currentIdentityUser = ref(null)
  const newIdentityValue = ref('外门弟子')
  const newExpireAtValue = ref(null)
  const autoConvertIdentity = ref(true)
  const updatingIdentity = ref(false)

  const editGroupVisible = ref(false)
  const updatingGroup = ref(false)
  const currentGroupUser = ref(null)
  const newGroupValue = ref('凡人')

  const editChannelMemberVisible = ref(false)
  const updatingChannelMember = ref(false)
  const currentChannelMemberUser = ref(null)
  const newChannelMemberValue = ref(false)

  const allIdentities = [
    '外门弟子',
    '内门弟子',
    '核心弟子',
    '真传弟子',
  ]

  const loadUsersData = async () => {
    const requestId = ++latestUsersRequestId
    loading.value = true
    error.value = null

    try {
      const paramsObj = {
        query: searchQuery.value,
        query_partial: isQueryPartial.value,
        identity: filterIdentity.value,
        user_group: filterUserGroup.value,
        username: searchUsername.value,
        username_partial: isUsernamePartial.value,
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

  const handleTableChange = (pagination) => {
    currentPage.value = pagination.current
    pageSize.value = pagination.pageSize
    void loadUsersData()
  }

  const onSearchInput = () => {
    if (searchTimeout.value) clearTimeout(searchTimeout.value)
    searchTimeout.value = setTimeout(() => {
      currentPage.value = 1
      void loadUsersData()
    }, 500)
  }

  const handleViewStats = async (record) => {
    currentUser.value = record
    statsModalVisible.value = true
    statsLoading.value = true
    currentUserStats.value = null
    try {
      currentUserStats.value = await fetchUserStats(record.id)
    } catch (err) {
      message.error('获取统计数据失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      statsLoading.value = false
    }
  }

  const handleEditCredits = (record) => {
    currentEditingUser.value = record
    newCreditsValue.value = record.credits
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
      message.error('更新失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      updatingCredits.value = false
    }
  }

  const handleClearHistory = (record) => {
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
          message.error('清除数据失败: ' + (err.response?.data?.detail || err.message))
        }
      },
    })
  }

  const handleDeleteUser = (record) => {
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
          message.error('删除用户失败: ' + (err.response?.data?.detail || err.message))
        }
      },
    })
  }

  const handleEditIdentity = (record) => {
    currentIdentityUser.value = record
    newIdentityValue.value = record.current_identity || '外门弟子'
    newExpireAtValue.value = null
    autoConvertIdentity.value = true
    editIdentityVisible.value = true
  }

  const handleEditGroup = (record) => {
    currentGroupUser.value = record
    newGroupValue.value = record.user_group || '凡人'
    editGroupVisible.value = true
  }

  const handleEditChannelMember = (record) => {
    currentChannelMemberUser.value = record
    newChannelMemberValue.value = !!record.is_channel_member
    editChannelMemberVisible.value = true
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
      message.error('更新失败: ' + (err.response?.data?.detail || err.message))
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
      message.error('更新失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      updatingGroup.value = false
    }
  }

  const saveChannelMember = async () => {
    if (!currentChannelMemberUser.value) return

    updatingChannelMember.value = true
    try {
      const res = await updateUserChannelMember(
        currentChannelMemberUser.value.id,
        newChannelMemberValue.value
      )
      message.success(`用户 ${currentChannelMemberUser.value.id} 宗门状态已更新`)
      editChannelMemberVisible.value = false
      await loadUsersData()
    } catch (err) {
      message.error('更新失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      updatingChannelMember.value = false
    }
  }

  const loadPlans = async () => {
    try {
      const res = await fetchPlans()
      availablePlans.value = res.filter(plan => plan.is_active)
    } catch (err) {
      console.error('Failed to load plans:', err)
    }
  }

  const handleGiftPlan = (record) => {
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
      await adminGiftPlan(currentGiftUser.value.id, giftForm.value.plan_id, giftForm.value.note)
      message.success(`成功为用户 ${currentGiftUser.value.id} 赠送套餐`)
      giftModalVisible.value = false
      await loadUsersData()
    } catch (err) {
      message.error('赠送套餐失败: ' + (err.response?.data?.detail || err.message))
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
    searchQuery,
    isQueryPartial,
    filterIdentity,
    filterUserGroup,
    searchUsername,
    isUsernamePartial,
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
    saveIdentity,
    saveGroup,
    saveChannelMember,
    handleGiftPlan,
    submitGift,
  }
}
