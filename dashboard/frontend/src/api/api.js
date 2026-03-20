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

export const fetchUsers = async () => {
  const response = await api.get('/api/users')
  return response.data
}

export const fetchUserHistory = async (userId) => {
  const response = await api.get(`/api/history/${userId}`)
  return response.data
}

export const fetchHistoryAll = async (page = 1, pageSize = 20, type = null) => {
  let url = `/api/history/all?page=${page}&page_size=${pageSize}`
  if (type && type !== 'all') {
    url += `&type=${type}`
  }
  const response = await api.get(url)
  return response.data
}

export const deleteUser = async (userId) => {
  const response = await api.delete(`/api/users/${userId}`)
  return response.data
}

export const updateUserCredits = async (userId, credits) => {
  const response = await api.post(`/api/users/${userId}/credits`, { credits })
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

export const fetchBotQueue = async () => {
  // Deprecated: Use fetchSystemStatus instead
  const response = await api.get('/api/bot/queue')
  return response.data
}

export const fetchSystemStatus = async () => {
  const response = await api.get('/api/system/status')
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

export const fetchOrders = async (page = 1, pageSize = 20, status = null) => {
  const params = new URLSearchParams()
  params.append('page', page)
  params.append('page_size', pageSize)
  if (status && status !== 'ALL') {
    params.append('status', status)
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

export { apiBaseUrl }
export default api
