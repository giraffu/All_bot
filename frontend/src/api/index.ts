import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'
import { message } from 'ant-design-vue'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000
})

api.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      router.push('/login')
      message.error('Session expired, please login again.')
    } else if (error.response?.status === 402) {
      message.warning(error.response?.data?.detail || 'Insufficient balance.')
    } else if (error.response?.status === 429) {
      message.warning(error.response?.data?.detail || 'Too many tasks running.')
    } else {
      message.error(error.response?.data?.detail || 'System error occurred.')
    }
    return Promise.reject(error)
  }
)

export default api
