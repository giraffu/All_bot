import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('avatar_miniapp_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('avatar_miniapp_token')
      localStorage.removeItem('avatar_miniapp_user')
      if (location.pathname !== '/login') location.assign('/login')
    }
    return Promise.reject(error)
  },
)

export default api
