import axios from 'axios'

// Use relative URL in production (proxied by Nginx)
const apiBaseUrl = import.meta.env.PROD ? '' : `http://${window.location.hostname}:8043`

const api = axios.create({
  baseURL: apiBaseUrl
})

// Request interceptor to add token and prevent caching
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  // Add timestamp to GET requests to prevent caching
  if (config.method === 'get') {
    config.params = config.params || {}
    config.params['_t'] = Date.now()
  }

  return config
})

// Response interceptor to handle 401
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token')
      // Let the app know we are unauthorized
      window.dispatchEvent(new Event('unauthorized'))
    }
    return Promise.reject(error)
  }
)

export const login = async (username, password) => {
  const formData = new FormData()
  formData.append('username', username)
  formData.append('password', password)
  const response = await api.post('/api/auth/login', formData)
  return response.data
}

export const fetchStats = async () => {
  const response = await api.get('/api/stats')
  return response.data
}

export const fetchStatsHistory = async (days = 7) => {
  const response = await api.get(`/api/stats/history?days=${days}`)
  return response.data
}

export const fetchHourlyStats = async (dateStr = null) => {
  const url = dateStr ? `/api/stats/hourly?date_str=${dateStr}` : '/api/stats/hourly'
  const response = await api.get(url)
  return response.data
}

export const fetchFinanceHourlyStats = async (dateStr = null) => {
  const url = dateStr ? `/api/stats/finance_hourly?date_str=${dateStr}` : '/api/stats/finance_hourly'
  const response = await api.get(url)
  return response.data
}

export const fetchCumulativeFinanceHourlyStats = async (days = 7) => {
  const response = await api.get(`/api/stats/finance_hourly/cumulative?days=${days}`)
  return response.data
}

export const fetchTypeDistribution = async (dateStr = null) => {
  const url = dateStr ? `/api/stats/type_distribution?date_str=${dateStr}` : '/api/stats/type_distribution'
  const response = await api.get(url)
  return response.data
}

export const fetchCumulativeTypeDistribution = async (days = 7) => {
  const response = await api.get(`/api/stats/type_distribution/cumulative?days=${days}`)
  return response.data
}

export const fetchCumulativeHourlyStats = async (days = 7) => {
  const response = await api.get(`/api/stats/hourly/cumulative?days=${days}`)
  return response.data
}

export const fetchUsers = async (page = 1, pageSize = 20, params_obj = {}) => {
  const params = new URLSearchParams()
  params.append('skip', (page - 1) * pageSize)
  params.append('limit', pageSize)
  
  // Backwards compatibility if a string query is passed
  if (typeof params_obj === 'string') {
    if (params_obj) params.append('query', params_obj)
  } else {
    if (params_obj.query) params.append('query', params_obj.query)
    if (params_obj.query_partial !== undefined) params.append('query_partial', params_obj.query_partial)
    if (params_obj.username) params.append('username', params_obj.username)
    if (params_obj.username_partial !== undefined) params.append('username_partial', params_obj.username_partial)
    if (params_obj.identity) params.append('identity', params_obj.identity)
    if (params_obj.user_group) params.append('user_group', params_obj.user_group)
  }
  
  const response = await api.get(`/api/users?${params.toString()}`)
  return response.data
}

export const fetchUserStats = async (userId) => {
  const response = await api.get(`/api/users/${userId}/stats`)
  return response.data
}

export const fetchUserHistory = async (userId) => {
  const response = await api.get(`/api/history/${userId}`)
  return response.data
}

export const fetchHistoryAll = async (page = 1, pageSize = 20, type = null, rating = null, isPublic = null, workerId = null) => {
  const params = new URLSearchParams()
  params.append('page', page)
  params.append('page_size', pageSize)
  
  if (type && type !== 'all') {
    params.append('type', type)
  }
  
  if (rating !== null) {
    params.append('rating', rating)
  }
  
  if (isPublic !== null) {
    params.append('is_public', isPublic)
  }
  
  if (workerId && workerId !== 'all') {
    params.append('worker_id', workerId)
  }
  
  const response = await api.get(`/api/history/all?${params.toString()}`)
  return response.data
}

export const deleteUser = async (userId) => {
  const response = await api.delete(`/api/users/${userId}`)
  return response.data
}

export const updateUserCredits = async (userId, credits, checkin_count = null) => {
  const payload = { credits }
  if (checkin_count !== null) payload.checkin_count = checkin_count
  const response = await api.post(`/api/users/${userId}/credits`, payload)
  return response.data
}

export const updateUserIdentity = async (userId, identity, expire_at = null, convert = true) => {
  const payload = { identity, convert }
  if (expire_at) payload.expire_at = expire_at
  const response = await api.post(`/api/users/${userId}/identity`, payload)
  return response.data
}

export const updateUserGroup = async (userId, userGroup) => {
  const response = await api.post(`/api/users/${userId}/group`, { user_group: userGroup })
  return response.data
}

export const updateUserChannelMember = async (userId, isChannelMember) => {
  const response = await api.post(`/api/users/${userId}/channel_member`, { is_channel_member: isChannelMember })
  return response.data
}

export const clearUserHistory = async (userId) => {
  const response = await api.delete(`/api/users/${userId}/history`)
  return response.data
}

export const fetchTemplateContributions = async () => {
  const response = await api.get('/api/templates/contributions')
  return response.data
}

export const approveTemplateContribution = async (id) => {
  const response = await api.post(`/api/templates/contributions/${id}/approve`)
  return response.data
}

export const deleteTemplateContribution = async (id) => {
  const response = await api.delete(`/api/templates/contributions/${id}`)
  return response.data
}



export const fetchWorkerList = async () => {
  const response = await api.get('/api/workers/list')
  return response.data
}

export const fetchSystemStatus = async () => {
  const response = await api.get('/api/system/status')
  return response.data
}

export const fetchSystemWorkers = async () => {
  const response = await api.get('/api/system/workers')
  return response.data
}

export const fetchConcurrencyStats = async () => {
  const response = await api.get('/api/system/concurrency_stats')
  return response.data
}

export const fetchActiveBotTasks = async () => {
  const response = await api.get('/api/system/active_bot_tasks')
  return response.data
}

export const refundBotTask = async (taskId) => {
  const response = await api.post('/api/system/refund_bot_task', { task_id: taskId })
  return response.data
}

export const cleanZombieTasks = async () => {
  const response = await api.post('/api/system/clean_zombie_tasks')
  return response.data
}

export const syncUserConcurrency = async (userId) => {
  const response = await api.post('/api/system/sync_user_concurrency', { user_id: userId })
  return response.data
}

export const fetchTaskStatus = async (taskId) => {
  const response = await api.get(`/api/status/${taskId}`)
  return response.data
}

export const fetchTaskImage = (taskId) => {
  return `${api.defaults.baseURL}/api/image/${taskId}`
}

export const fetchTaskVideo = (taskId) => {
  return `${api.defaults.baseURL}/api/video/${taskId}`
}

export const fetchLogs = async ({ page = 1, pageSize = 20, userId = null, operationType = null, startDate = null, endDate = null }) => {
  const params = new URLSearchParams()
  params.append('page', page)
  params.append('page_size', pageSize)
  
  if (userId) params.append('user_id', userId)
  if (operationType) params.append('operation_type', operationType)
  if (startDate) params.append('start_date', startDate)
  if (endDate) params.append('end_date', endDate)

  const response = await api.get(`/api/logs?${params.toString()}`)
  return response.data
}

// Recharge System APIs
export const fetchPlans = async () => {
  const response = await api.get('/api/plans')
  return response.data
}

export const createPlan = async (planData) => {
  const response = await api.post('/api/plans', planData)
  return response.data
}

export const updatePlan = async (planId, planData) => {
  const response = await api.put(`/api/plans/${planId}`, planData)
  return response.data
}

export const deletePlan = async (planId) => {
  const response = await api.delete(`/api/plans/${planId}`)
  return response.data
}

export const fetchOrders = async (page = 1, pageSize = 20, status = null, telegramId = null, username = null) => {
  const params = new URLSearchParams()
  params.append('page', page)
  params.append('page_size', pageSize)
  if (status && status !== 'ALL') {
    params.append('status', status)
  }
  if (telegramId) {
    params.append('telegram_id', telegramId)
  }
  if (username) {
    params.append('username', username)
  }
  const response = await api.get(`/api/orders?${params.toString()}`)
  return response.data
}

export const adminGiftPlan = async (userId, planId, note = "后台手动赠送") => {
  const response = await api.post(`/api/users/${userId}/gift`, {
    plan_id: planId,
    note: note
  })
  return response.data
}

// Gallery API
export const fetchGalleryPosts = async (params) => {
  const response = await api.get('/api/gallery/all', { params })
  return response.data
}

export const updateGalleryPost = async (postId, data) => {
  const response = await api.put(`/api/gallery/${postId}`, data)
  return response.data
}

export const deleteGalleryPost = async (postId) => {
  const response = await api.delete(`/api/gallery/${postId}`)
  return response.data
}

export const fetchReferralRewards = async () => {
  const response = await api.get('/api/referrals/rewards')
  return response.data
}

export { apiBaseUrl }
export default api
