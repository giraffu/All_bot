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

export const fetchHourlyStats = async (dateStr = null) => {
  return get(withQuery('/api/stats/hourly', params => {
    appendQueryParam(params, 'date_str', dateStr)
  }))
}

export const fetchFinanceHourlyStats = async (dateStr = null) => {
  return get(withQuery('/api/stats/finance_hourly', params => {
    appendQueryParam(params, 'date_str', dateStr)
  }))
}

export const fetchCumulativeFinanceHourlyStats = async (days = 7) =>
  get(withQuery('/api/stats/finance_hourly/cumulative', params => {
    appendQueryParam(params, 'days', days)
  }))

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
    appendQueryParam(params, 'query', params_obj.query)
    appendQueryParam(params, 'query_partial', params_obj.query_partial)
    appendQueryParam(params, 'username', params_obj.username)
    appendQueryParam(params, 'username_partial', params_obj.username_partial)
    appendQueryParam(params, 'identity', params_obj.identity)
    appendQueryParam(params, 'user_group', params_obj.user_group)
  }))
}

export const fetchUserStats = async (userId) => get(`/api/users/${userId}/stats`)

export const fetchUserHistory = async (userId) => get(`/api/history/${userId}`)

export const fetchHistoryAll = async (page = 1, pageSize = 20, type = null, rating = null, isPublic = null, workerId = null) => {
  return get(withQuery('/api/history/all', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    if (type && type !== 'all') appendQueryParam(params, 'type', type)
    if (rating !== null) appendQueryParam(params, 'rating', rating)
    if (isPublic !== null) appendQueryParam(params, 'is_public', isPublic)
    if (workerId && workerId !== 'all') appendQueryParam(params, 'worker_id', workerId)
  }))
}

export const deleteUser = async (userId) => del(`/api/users/${userId}`)

export const updateUserCredits = async (userId, credits, checkin_count = null) => {
  const payload = { credits }
  if (checkin_count !== null) payload.checkin_count = checkin_count
  return post(`/api/users/${userId}/credits`, payload)
}

export const updateUserIdentity = async (userId, identity, expire_at = null, convert = true) => {
  const payload = { identity, convert }
  if (expire_at) payload.expire_at = expire_at
  return post(`/api/users/${userId}/identity`, payload)
}

export const updateUserGroup = async (userId, userGroup) =>
  post(`/api/users/${userId}/group`, { user_group: userGroup })

export const updateUserChannelMember = async (userId, isChannelMember) =>
  post(`/api/users/${userId}/channel_member`, { is_channel_member: isChannelMember })

export const clearUserHistory = async (userId) => del(`/api/users/${userId}/history`)

export const fetchTemplateContributions = async () => get('/api/templates/contributions')

export const approveTemplateContribution = async (id) =>
  post(`/api/templates/contributions/${id}/approve`)

export const deleteTemplateContribution = async (id) =>
  del(`/api/templates/contributions/${id}`)



export const fetchWorkerList = async () => get('/api/workers/list')

export const fetchWorkerHistory = async ({ page = 1, size = 20, workerId = null } = {}) =>
  get(withQuery('/api/workers/history', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'size', size)
    appendQueryParam(params, 'worker_id', workerId)
  }))

export const fetchSystemStatus = async () => get('/api/system/status')

export const fetchSystemWorkers = async () => get('/api/system/workers')

export const fetchConcurrencyStats = async () => get('/api/system/concurrency_stats')

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

export const fetchLogs = async ({ page = 1, pageSize = 20, userId = null, operationType = null, startDate = null, endDate = null }) => {
  return get(withQuery('/api/logs', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    appendQueryParam(params, 'user_id', userId)
    appendQueryParam(params, 'operation_type', operationType)
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

// Gallery API
export const fetchGalleryPosts = async (params) => get('/api/gallery/all', { params })

export const updateGalleryPost = async (postId, data) => put(`/api/gallery/${postId}`, data)

export const fetchGalleryComments = async (params) => get('/api/gallery/comments', { params })

export const fetchAllGalleryComments = async (params) =>
  get('/api/gallery/comments/all', { params })

export const updateGalleryComment = async (commentId, data) =>
  put(`/api/gallery/comments/${commentId}`, data)

export const deleteGalleryPost = async (postId) => del(`/api/gallery/${postId}`)

export const fetchReferralRewards = async () => get('/api/referrals/rewards')

export const fetchAffiliateRedeemRecords = async ({
  page = 1,
  pageSize = 20,
  query = '',
  redeemType = ''
} = {}) => {
  return get(withQuery('/api/referrals/redeems', params => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
    appendQueryParam(params, 'query', query)
    appendQueryParam(params, 'redeem_type', redeemType)
  }))
}

export { apiBaseUrl }
export default api
