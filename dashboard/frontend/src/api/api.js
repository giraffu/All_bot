import {
  api,
  apiBaseUrl,
  appendQueryParam,
  unwrapData,
  withQuery
} from './client'

const get = (url, config) => api.get(url, config).then(unwrapData)
const post = (url, data, config) => api.post(url, data, config).then(unwrapData)
const put = (url, data, config) => api.put(url, data, config).then(unwrapData)
const del = (url, config) => api.delete(url, config).then(unwrapData)

export const login = async (username, password) => {
  const formData = new FormData()
  formData.append('username', username)
  formData.append('password', password)
  return post('/api/auth/login', formData)
}

export const fetchStats = async () => get('/api/stats')

export const fetchStatsHistory = async (days = 7) =>
  get(withQuery('/api/stats/history', params => {
    appendQueryParam(params, 'days', days)
  }))

/**
 * @param {string | null} [dateStr]
 */
export const fetchHourlyStats = async (dateStr = null) => {
  return get(withQuery('/api/stats/hourly', params => {
    appendQueryParam(params, 'date_str', dateStr)
  }))
}

/**
 * @param {string | null} [dateStr]
 */
export const fetchFinanceHourlyStats = async (dateStr = null) => {
  return get(withQuery('/api/stats/finance_hourly', params => {
    appendQueryParam(params, 'date_str', dateStr)
  }))
}

/**
 * @param {number} [days]
 */
export const fetchCumulativeFinanceHourlyStats = async (days = 7) =>
  get(withQuery('/api/stats/finance_hourly/cumulative', params => {
    appendQueryParam(params, 'days', days)
  }))

/**
 * @param {string | null} [dateStr]
 */
export const fetchTypeDistribution = async (dateStr = null) => {
  return get(withQuery('/api/stats/type_distribution', params => {
    appendQueryParam(params, 'date_str', dateStr)
  }))
}

export const fetchCumulativeTypeDistribution = async (days = 7) =>
  get(withQuery('/api/stats/type_distribution/cumulative', params => {
    appendQueryParam(params, 'days', days)
  }))

export const fetchCumulativeHourlyStats = async (days = 7) =>
  get(withQuery('/api/stats/hourly/cumulative', params => {
    appendQueryParam(params, 'days', days)
  }))

export const fetchUsers = async (page = 1, pageSize = 20, params_obj = {}) => {
  return get(withQuery('/api/users', params => {
    appendQueryParam(params, 'skip', (page - 1) * pageSize)
    appendQueryParam(params, 'limit', pageSize)
    appendQueryParam(params, 'user_id', params_obj.user_id)
    appendQueryParam(params, 'query', params_obj.query)
    appendQueryParam(params, 'query_partial', params_obj.query_partial)
    appendQueryParam(params, 'username', params_obj.username)
    appendQueryParam(params, 'username_partial', params_obj.username_partial)
    appendQueryParam(params, 'identity', params_obj.identity)
    appendQueryParam(params, 'user_group', params_obj.user_group)
    appendQueryParam(params, 'submission_banned', params_obj.submission_banned)
    appendQueryParam(params, 'alipay_direct_enabled', params_obj.alipay_direct_enabled)
    appendQueryParam(params, 'sort_by', params_obj.sort_by)
    appendQueryParam(params, 'sort_order', params_obj.sort_order)
  }))
}

export const fetchUserStats = async (userId) => get(`/api/users/${userId}/stats`)

export const fetchUserHistory = async (userId, page = 1, pageSize = 20) =>
  get(withQuery(`/api/history/${userId}`, params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
  }))

export const fetchUserFavorites = async (
  userId,
  {
    page = 1,
    size = 12,
    taskType = null,
  } = {}
) =>
  get(withQuery(`/api/users/${userId}/favorites`, params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'size', size)
    appendQueryParam(params, 'task_type', taskType)
  }))

export const fetchHistoryAll = async (
  page = 1,
  pageSize = 20,
  type = null,
  rating = null,
  isPublic = null,
  workerId = null,
  source = null,
  requestConfig = {},
) => {
  return get(withQuery('/api/history/all', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    if (type && type !== 'all') appendQueryParam(params, 'type', type)
    if (rating !== null) appendQueryParam(params, 'rating', rating)
    if (isPublic !== null) appendQueryParam(params, 'is_public', isPublic)
    if (workerId && workerId !== 'all') appendQueryParam(params, 'worker_id', workerId)
    if (source && source !== 'all') appendQueryParam(params, 'source', source)
  }), requestConfig)
}

export const deleteUser = async (userId) => del(`/api/users/${userId}`)

/** @param {{page?: number, pageSize?: number, status?: string | null, category?: string | null}} options */
export const fetchSupportTickets = async ({ page = 1, pageSize = 30, status = null, category = null } = {}) =>
  get(withQuery('/api/support-tickets', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    appendQueryParam(params, 'status', status)
    appendQueryParam(params, 'category', category)
  }))
export const fetchSupportTicket = async (ticketId) => get(`/api/support-tickets/${ticketId}`)
export const updateSupportTicket = async (ticketId, payload) => api.patch(`/api/support-tickets/${ticketId}`, payload).then(unwrapData)
export const replySupportTicket = async (ticketId, payload) => post(`/api/support-tickets/${ticketId}/reply`, payload)

/**
 * @param {number} userId
 * @param {number} credits
 * @param {number | null} [checkin_count]
 */
export const updateUserCredits = async (userId, credits, checkin_count = null) => {
  const payload = { credits }
  if (checkin_count !== null) payload.checkin_count = checkin_count
  return post(`/api/users/${userId}/credits`, payload)
}

/**
 * @param {number} userId
 * @param {string} identity
 * @param {string | null} [expire_at]
 * @param {boolean} [convert]
 */
export const updateUserIdentity = async (userId, identity, expire_at = null, convert = true) => {
  const payload = { identity, convert }
  if (expire_at) payload.expire_at = expire_at
  return post(`/api/users/${userId}/identity`, payload)
}

export const updateUserGroup = async (userId, userGroup) =>
  post(`/api/users/${userId}/group`, { user_group: userGroup })

export const updateUserChannelMember = async (userId, isChannelMember) =>
  post(`/api/users/${userId}/channel_member`, { is_channel_member: isChannelMember })

export const updateUserSubmissionBan = async (userId, isSubmissionBanned, reason = null) => {
  const payload = { is_submission_banned: isSubmissionBanned }
  if (reason) payload.reason = reason
  return post(`/api/users/${userId}/submission_ban`, payload)
}

export const updateUserAlipayDirect = async (userId, enabled) =>
  post(`/api/users/${userId}/alipay-direct`, { enabled })

export const clearUserHistory = async (userId) => del(`/api/users/${userId}/history`)

export const fetchTemplateContributions = async () => get('/api/templates/contributions')

export const approveTemplateContribution = async (id) =>
  post(`/api/templates/contributions/${id}/approve`)

export const deleteTemplateContribution = async (id) =>
  del(`/api/templates/contributions/${id}`)



export const fetchWorkerList = async () => get('/api/workers/list')

/**
 * @param {{ page?: number, size?: number, workerId?: string | null }} [options]
 */
export const fetchWorkerHistory = async ({ page = 1, size = 20, workerId = null } = {}) =>
  get(withQuery('/api/workers/history', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'size', size)
    appendQueryParam(params, 'worker_id', workerId)
  }))

export const fetchSystemStatus = async () => get('/api/system/status')

export const fetchSystemWorkers = async () => get('/api/system/workers')

export const fetchConcurrencyStats = async () => get('/api/system/concurrency_stats')

export const fetchRunPodProfiles = async () => get('/api/runpod/profiles')

export const fetchRunPodOperations = async () => get('/api/runpod/operations')

export const fetchRunPodAutoscaler = async () => get('/api/runpod/autoscaler')

export const controlRunPodAutoscaler = async (payload) =>
  post('/api/runpod/autoscaler/control', payload)

export const updateRunPodAutoscalerSettings = async (payload) =>
  post('/api/runpod/autoscaler/settings', payload)

export const scaleRunPodCapacity = async (payload) => post('/api/runpod/scale', payload)

export const terminateRunPodOperation = async (operationId) =>
  post(`/api/runpod/operations/${operationId}/terminate`)

export const pauseRunPodWorker = async (agentId, payload = {}) =>
  post(`/api/runpod/workers/${agentId}/pause`, payload)

export const enableRunPodWorker = async (agentId, payload = {}) =>
  post(`/api/runpod/workers/${agentId}/enable`, payload)

export const restartRunPodWorker = async (agentId, payload = {}) =>
  post(`/api/runpod/workers/${agentId}/restart`, payload)

export const lockRunPodWorker = async (agentId, payload = {}) =>
  post(`/api/runpod/workers/${agentId}/lock`, payload)

export const unlockRunPodWorker = async (agentId, payload = {}) =>
  post(`/api/runpod/workers/${agentId}/unlock`, payload)

export const deleteRunPodWorker = async (agentId, payload = {}) =>
  del(`/api/runpod/workers/${agentId}`, { data: payload })

export const restartLanAioWorker = async (agentId, payload = {}) =>
  post(`/api/runpod/lan-aio/workers/${agentId}/restart`, payload)

export const pauseLanAioWorker = async (agentId, payload = {}) =>
  post(`/api/runpod/lan-aio/workers/${agentId}/pause`, payload)

export const enableLanAioWorker = async (agentId, payload = {}) =>
  post(`/api/runpod/lan-aio/workers/${agentId}/enable`, payload)

export const fetchActiveBotTasks = async () => get('/api/system/active_bot_tasks')

export const refundBotTask = async (taskId) =>
  post('/api/system/refund_bot_task', { task_id: taskId })

export const cleanZombieTasks = async () => post('/api/system/clean_zombie_tasks')

export const syncUserConcurrency = async (userId) =>
  post('/api/system/sync_user_concurrency', { user_id: userId })

export const fetchTaskStatus = async (taskId) => get(`/api/status/${taskId}`)

export const fetchTaskImage = (taskId) => {
  return `${api.defaults.baseURL}/api/image/${taskId}`
}

export const fetchTaskVideo = (taskId) => {
  return `${api.defaults.baseURL}/api/video/${taskId}`
}

export const fetchLogs = async ({ page = 1, pageSize = 20, userId = null, username = null, operationType = null, startDate = null, endDate = null }) => {
  return get(withQuery('/api/logs', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    appendQueryParam(params, 'user_id', userId)
    appendQueryParam(params, 'username', username)
    appendQueryParam(params, 'operation_type', operationType)
    appendQueryParam(params, 'start_date', startDate)
    appendQueryParam(params, 'end_date', endDate)
  }))
}

export const fetchPaidGroupGuardConfig = async () => get('/api/paid-group-guard/config')

export const updatePaidGroupGuardConfig = async (payload) =>
  put('/api/paid-group-guard/config', payload)

export const fetchGroupManageConfig = async () => get('/api/group-manage/config')

export const updateGroupManageConfig = async (payload) =>
  put('/api/group-manage/config', payload)

export const fetchMainBotMenuConfig = async () => get('/api/main-bot/menu-config')

export const updateMainBotMenuConfig = async (payload) =>
  put('/api/main-bot/menu-config', payload)

export const fetchFeatureEntryVisibilityConfig = async () =>
  get('/api/entry-visibility')

export const updateFeatureEntryVisibilityConfig = async (payload) =>
  put('/api/entry-visibility', payload)

/**
 * @param {{ page?: number, pageSize?: number, reason?: string | null, userId?: string | null, startDate?: string | null, endDate?: string | null }} [options]
 */
export const fetchPaidGroupGuardLogs = async ({
  page = 1,
  pageSize = 20,
  reason = null,
  userId = null,
  startDate = null,
  endDate = null
} = {}) => {
  return get(withQuery('/api/paid-group-guard/logs', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    appendQueryParam(params, 'reason', reason)
    appendQueryParam(params, 'user_id', userId)
    appendQueryParam(params, 'start_date', startDate)
    appendQueryParam(params, 'end_date', endDate)
  }))
}

export const fetchGroupManageLogs = async (options = {}) => {
  const { page = 1, pageSize = 20, reason = null, userId = null, startDate = null, endDate = null } = options
  return get(withQuery('/api/group-manage/logs', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    appendQueryParam(params, 'reason', reason)
    appendQueryParam(params, 'user_id', userId)
    appendQueryParam(params, 'start_date', startDate)
    appendQueryParam(params, 'end_date', endDate)
  }))
}

// Recharge System APIs
export const fetchPlans = async () => get('/api/plans')

export const createPlan = async (planData) => post('/api/plans', planData)

export const updatePlan = async (planId, planData) => put(`/api/plans/${planId}`, planData)

export const deletePlan = async (planId) => del(`/api/plans/${planId}`)

export const fetchOrders = async (
  page = 1,
  pageSize = 20,
  status = null,
  orderId = null,
  internalUserId = null,
  username = null
) => {
  return get(withQuery('/api/orders', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    if (status && status !== 'ALL') appendQueryParam(params, 'status', status)
    appendQueryParam(params, 'order_id', orderId)
    appendQueryParam(params, 'internal_user_id', internalUserId)
    appendQueryParam(params, 'username', username)
  }))
}

export const adminGiftPlan = async (userId, planId, note = "后台手动赠送") => {
  return post(`/api/users/${userId}/gift`, {
    plan_id: planId,
    note: note
  })
}

export const transferUserData = async (
  sourceUserId,
  targetUserId,
  note = '后台用户数据转移'
) => post(`/api/users/${sourceUserId}/transfer`, {
  target_user_id: targetUserId,
  note,
})

// Gallery API
export const fetchGalleryPosts = async (params) => get('/api/gallery/all', { params })

export const updateGalleryPost = async (postId, data) => put(`/api/gallery/${postId}`, data)

export const banGalleryUserSubmissionsAndTakedown = async (userId, reason = null) => {
  const payload = {}
  if (reason) payload.reason = reason
  return post(`/api/gallery/users/${userId}/ban-submissions-and-takedown`, payload)
}

export const fetchAllGalleryComments = async (params) =>
  get('/api/gallery/comments/all', { params })

export const updateGalleryComment = async (commentId, data) =>
  put(`/api/gallery/comments/${commentId}`, data)

export const deleteGalleryPost = async (postId) => del(`/api/gallery/${postId}`)

export const fetchGalleryReports = async (params) =>
  get('/api/gallery/reports', { params })

export const resolveGalleryReport = async (reportId) =>
  post(`/api/gallery/reports/${reportId}/resolve`)

export const takedownGalleryReport = async (reportId) =>
  post(`/api/gallery/reports/${reportId}/takedown`)

export const fetchReferralRewards = async () => get('/api/referrals/rewards')

export const fetchSiteNotices = async () => get('/api/site-notices')

export const createSiteNotice = async (payload) => post('/api/site-notices', payload)

export const updateSiteNotice = async (noticeId, payload) => put(`/api/site-notices/${noticeId}`, payload)

export const deleteSiteNotice = async (noticeId) => del(`/api/site-notices/${noticeId}`)

export const fetchAffiliateRedeemRecords = async ({
  page = 1,
  pageSize = 20,
  query = '',
  redeemType = '',
  status = ''
} = {}) => {
  return get(withQuery('/api/referrals/redeems', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    appendQueryParam(params, 'query', query)
    appendQueryParam(params, 'redeem_type', redeemType)
    appendQueryParam(params, 'status', status)
  }))
}

export const completeAffiliateUsdtRedeem = async (redeemId, payload) =>
  post(`/api/referrals/redeems/${redeemId}/complete`, payload)

export const rejectAffiliateUsdtRedeem = async (redeemId, payload) =>
  post(`/api/referrals/redeems/${redeemId}/reject`, payload)

export { apiBaseUrl }
export default api
