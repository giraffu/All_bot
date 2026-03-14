import axios from 'axios'

const apiBaseUrl = `http://${window.location.hostname}:8043`

const api = axios.create({
  baseURL: apiBaseUrl
})

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
  const response = await api.get('/api/bot/queue')
  return response.data
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

export { apiBaseUrl }
export default api
