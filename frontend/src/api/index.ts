import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'
import { message } from 'ant-design-vue'
import i18n from '@/i18n'
import { getRuntimeConfig } from '@/config/runtime'
import { getRateLimitFallbackKey } from './errorMessages'

const api = axios.create({
  baseURL: getRuntimeConfig('api_base_url', '/api'),
  timeout: 30000
})

const callerHandledUnauthorizedPaths = [
  '/auth/login',
  '/auth/telegram',
  '/auth/telegram/payment',
]

function isCallerHandledUnauthorized(url?: string): boolean {
  if (!url) return false
  return callerHandledUnauthorizedPaths.some((path) => url.endsWith(path))
}

type ApiErrorPayload = {
  code?: string | number
  reason?: unknown
  intent?: unknown
  message?: unknown
  detail?: unknown
}

function asNonEmptyString(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim()
  return normalized || undefined
}

function asPayloadObject(value: unknown): ApiErrorPayload | undefined {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return undefined
  return value as ApiErrorPayload
}

function resolveApiErrorMessage(data: ApiErrorPayload | undefined, fallback: string): string {
  const detailPayload = asPayloadObject(data?.detail)
  const code = String(data?.code ?? detailPayload?.code ?? '').trim()
  if (code) {
    const codeKey = `api.errors.${code}`
    if (i18n.global.te(codeKey)) return i18n.global.t(codeKey)
  }

  const reason = (
    asNonEmptyString(data?.reason)
    || asNonEmptyString(data?.intent)
    || asNonEmptyString(detailPayload?.reason)
    || asNonEmptyString(detailPayload?.intent)
  )
  if (reason) {
    const reasonKey = `api.reasons.${reason}`
    if (i18n.global.te(reasonKey)) return i18n.global.t(reasonKey)
  }

  const detailMessage = detailPayload
    ? asNonEmptyString(detailPayload.message) || asNonEmptyString(detailPayload.detail)
    : asNonEmptyString(data?.detail)

  return (
    asNonEmptyString(data?.message)
    || detailMessage
    || fallback
  )
}

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
    if (error.config?.suppressGlobalError) {
      return Promise.reject(error)
    }

    const t = i18n.global.t
    if (!error.response) {
      message.error(t('api.network_error'))
      return Promise.reject(error)
    }

    const status = error.response.status
    const data = error.response.data

    if (status === 401) {
      if (isCallerHandledUnauthorized(error.config?.url)) {
        return Promise.reject(error)
      }

      const authStore = useAuthStore()
      authStore.logout()
      router.push('/login')
      message.error(t('api.session_expired'))
    } else if (status === 402) {
      message.warning(resolveApiErrorMessage(data, t('api.insufficient_balance')))
    } else if (status === 429) {
      message.warning(
        resolveApiErrorMessage(data, t(getRateLimitFallbackKey(error.config?.url)))
      )
    } else if (status === 422) {
      // Handle Pydantic validation errors
      let errMsg = t('api.validation_error', { msg: 'Invalid parameters' })
      const validationDetails = Array.isArray(data?.detail) ? data.detail : Array.isArray(data?.details) ? data.details : []
      if (validationDetails.length > 0) {
        const firstErr = validationDetails[0]
        const loc = firstErr.loc.join('.')
        errMsg = t('api.validation_error', { msg: `${loc}: ${firstErr.msg}` })
      }
      message.error(errMsg)
    } else if (status === 503) {
      // 如果是维护模式，直接跳转到维护页面
      const detailPayload = asPayloadObject(data?.detail)
      if (
        data?.code === 5030
        || detailPayload?.code === 5030
        || data?.intent === 'MAINTENANCE'
        || detailPayload?.intent === 'MAINTENANCE'
      ) {
        if (router.currentRoute.value.path !== '/maintenance') {
          router.push('/maintenance')
        }
      } else {
        message.error(t('api.system_error'))
      }
    } else {
      message.error(resolveApiErrorMessage(data, t('api.system_error')))
    }
    return Promise.reject(error)
  }
)

export const fetchSiteNoticeCenter = async () => {
  const response = await api.get('/app/site-notices')
  return response.data
}

export default api
