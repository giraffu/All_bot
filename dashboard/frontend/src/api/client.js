import axios from 'axios'

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

export const api = axios.create({
  baseURL: apiBaseUrl
})

const getAuthToken = () => localStorage.getItem('token')

const notifyUnauthorized = () => {
  localStorage.removeItem('token')
  window.dispatchEvent(new Event('unauthorized'))
}

api.interceptors.request.use(config => {
  const token = getAuthToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  if (config.method === 'get') {
    config.params = config.params || {}
    config.params._t = Date.now()
  }

  return config
})

api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      notifyUnauthorized()
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
