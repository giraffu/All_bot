import axios from 'axios'
import { clearAuthToken, getAuthToken } from '../composables/useDashboardAuth'

const resolveApiBaseUrl = () => {
  const explicitBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()
  if (explicitBaseUrl) {
    return explicitBaseUrl
  }

  if (import.meta.env.PROD) {
    return ''
  }

  const apiPort = import.meta.env.VITE_DASHBOARD_API_PORT?.trim() || '8043'
  return `http://${window.location.hostname}:${apiPort}`
}

export const apiBaseUrl = resolveApiBaseUrl()

const cacheableGetPaths = new Set([
  '/api/system/status',
  '/api/system/workers',
  '/api/system/concurrency_stats',
])

const resolveRequestPath = (url) => {
  if (!url) {
    return ''
  }

  try {
    return new URL(url, window.location.origin).pathname
  } catch {
    return url.split('?')[0]
  }
}

export const shouldBypassDashboardCache = (url) => {
  const path = resolveRequestPath(url)
  return !(path.startsWith('/api/stats') || cacheableGetPaths.has(path))
}

export const api = axios.create({
  baseURL: apiBaseUrl
})

api.interceptors.request.use(config => {
  const token = getAuthToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  const url = config.url || ''
  if (config.method === 'get' && shouldBypassDashboardCache(url)) {
    config.params = config.params || {}
    config.params._t = Date.now()
  }

  return config
})

api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      clearAuthToken()
    }
    return Promise.reject(error)
  }
)

export const unwrapData = response => response.data

export const appendQueryParam = (params, key, value) => {
  if (value === undefined || value === null || value === '') {
    return
  }
  params.append(key, value)
}

export const buildQueryString = buildParams => {
  const params = new URLSearchParams()
  buildParams(params)
  return params.toString()
}

export const withQuery = (path, buildParams) => {
  const query = buildQueryString(buildParams)
  return query ? `${path}?${query}` : path
}
