import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'
import { message } from 'ant-design-vue'
import i18n from '@/i18n'

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
    const t = i18n.global.t
    if (!error.response) {
      message.error(t('api.network_error'))
      return Promise.reject(error)
    }
    
    const status = error.response.status
    const data = error.response.data
    const requestUrl = String(error.config?.url || '')
    const isGalleryCommentsRequest = /\/gallery\/posts\/\d+\/comments(?:\?.*)?$/.test(requestUrl)

    // 评论接口在“无评论”或评论资源不可用时可能返回 404，这里静默交给调用方处理，
    // 避免详情弹窗误报“帖子不存在或已下架”影响浏览内容。
    if (status === 404 && isGalleryCommentsRequest) {
      return Promise.reject(error)
    }
    
    if (status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      router.push('/login')
      message.error(t('api.session_expired'))
    } else if (status === 402) {
      message.warning(data?.message || t('api.insufficient_balance'))
    } else if (status === 429) {
      message.warning(data?.detail || t('api.too_many_tasks'))
    } else if (status === 422) {
      // Handle Pydantic validation errors
      let errMsg = t('api.validation_error', { msg: 'Invalid parameters' })
      if (data?.details && data.details.length > 0) {
        const firstErr = data.details[0]
        const loc = firstErr.loc.join('.')
        errMsg = t('api.validation_error', { msg: `${loc}: ${firstErr.msg}` })
      }
      message.error(errMsg)
    } else if (status === 503) {
      // 如果是维护模式，直接跳转到维护页面
      if (data?.code === 5030 || data?.intent === 'MAINTENANCE') {
        if (router.currentRoute.value.path !== '/maintenance') {
          router.push('/maintenance')
        }
      } else {
        message.error(t('api.system_error'))
      }
    } else {
      message.error(data?.message || data?.detail || t('api.system_error'))
    }
    return Promise.reject(error)
  }
)

export default api
