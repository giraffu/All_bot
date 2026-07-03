import axios from 'axios'

import {
  clearQqccConfigAuthToken,
  getQqccConfigAuthToken,
} from '../composables/useQqccConfigAuth'

const resolveApiBaseUrl = () => {
  const explicitBaseUrl = import.meta.env.VITE_QQCC_CONFIG_API_BASE_URL?.trim()
  if (explicitBaseUrl) {
    return explicitBaseUrl
  }

  if (import.meta.env.PROD) {
    return ''
  }

  const apiPort = import.meta.env.VITE_QQCC_CONFIG_API_PORT?.trim() || '8045'
  return `http://${window.location.hostname}:${apiPort}`
}

export const qqccConfigApi = axios.create({
  baseURL: resolveApiBaseUrl(),
})

qqccConfigApi.interceptors.request.use(config => {
  const token = getQqccConfigAuthToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

qqccConfigApi.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      clearQqccConfigAuthToken()
    }
    return Promise.reject(error)
  }
)

const unwrapData = response => response.data

export const loginQqccConfig = async (username: string, password: string) => {
  const formData = new FormData()
  formData.append('username', username)
  formData.append('password', password)
  return qqccConfigApi.post('/api/auth/login', formData).then(unwrapData)
}

export const fetchQqccConfig = async () =>
  qqccConfigApi.get('/api/qqcc/config', { params: { _t: Date.now() } }).then(unwrapData)

export const updateQqccConfig = async (payload: unknown) =>
  qqccConfigApi.put('/api/qqcc/config', payload).then(unwrapData)
