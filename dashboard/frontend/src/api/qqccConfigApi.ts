import axios from 'axios'
import type { AxiosResponse } from 'axios'

import {
  clearQqccConfigAuthToken,
  getQqccConfigAuthToken,
} from '../composables/useQqccConfigAuth'

export const resolveQqccApiBaseUrl = () => {
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
  baseURL: resolveQqccApiBaseUrl(),
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

const unwrapData = (response: AxiosResponse) => response.data

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

const fileToBase64 = async (file: File) => {
  const bytes = new Uint8Array(await file.arrayBuffer())
  const chunkSize = 0x8000
  let binary = ''
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return btoa(binary)
}

export const uploadQqccDemoMedia = async (
  sceneKind: 'video' | 'ai_video' | 'draw' | 'filter',
  sceneId: string,
  slot: 'input' | 'output',
  file: File,
) => {
  const contentBase64 = await fileToBase64(file)
  return qqccConfigApi
    .put(
      `/api/qqcc/demo-media-json/${encodeURIComponent(sceneKind)}/${encodeURIComponent(sceneId)}/${encodeURIComponent(slot)}`,
      {
        file_name: file.name,
        mime_type: file.type,
        content_base64: contentBase64,
      },
    )
    .then(unwrapData)
}

export const generateQqccDemoMedia = async (sceneKind: string, scene: unknown) =>
  qqccConfigApi.post(`/api/qqcc/demo-generation/${encodeURIComponent(sceneKind)}`, { scene }).then(unwrapData)

export const getQqccDemoGeneration = async (sceneKind: string, sceneId: string, generationId: string) =>
  qqccConfigApi.get(`/api/qqcc/demo-generation/${encodeURIComponent(sceneKind)}/${encodeURIComponent(sceneId)}/${encodeURIComponent(generationId)}`).then(unwrapData)

export type PrivateBotRuntimeStatus =
  | 'provisioning'
  | 'active'
  | 'paused'
  | 'disabled'
  | 'error'

export interface PrivateBotOwnerIdentity {
  id: number
  telegram_id: number
  username: string | null
  full_name: string | null
}

export interface PrivateBotStatusPayload {
  id: number
  telegram_bot_id: number
  telegram_username: string | null
  telegram_display_name: string | null
  owner_enabled: boolean
  admin_enabled: boolean
  runtime_status: PrivateBotRuntimeStatus
  last_error_code: string | null
  last_error_message: string | null
  last_webhook_at: string | null
  last_update_at: string | null
  updated_at: string
}

export interface PrivateBotConfigPayload {
  bot: PrivateBotStatusPayload
  config: Record<string, unknown>
  config_version: number
  options: Record<string, unknown>
}

export interface PrivateBotAdminListItem extends PrivateBotStatusPayload {
  owner: PrivateBotOwnerIdentity
  token_fingerprint_hint: string
  created_at: string
}

export interface PrivateBotAuditLog {
  id: number
  actor_type: string
  actor_identifier: string | null
  action: string
  before_status: string | null
  after_status: string | null
  details: Record<string, unknown> | null
  created_at: string
}

export interface PrivateBotAdminDetail extends PrivateBotAdminListItem {
  config: Record<string, unknown>
  config_version: number
  options: Record<string, unknown>
  audit_logs: PrivateBotAuditLog[]
}

export interface PrivateBotAdminListResponse {
  items: PrivateBotAdminListItem[]
  total: number
  page: number
  page_size: number
}

export interface PrivateBotAdminListParams {
  page: number
  page_size: number
  status?: PrivateBotRuntimeStatus
  admin_enabled?: boolean
  owner?: string
  username?: string
}

export const fetchPrivateBotsAdmin = async (params: PrivateBotAdminListParams) =>
  qqccConfigApi
    .get<PrivateBotAdminListResponse>('/api/private-bots/admin', { params })
    .then(unwrapData) as Promise<PrivateBotAdminListResponse>

export const fetchPrivateBotAdminDetail = async (privateBotId: number) =>
  qqccConfigApi
    .get<PrivateBotAdminDetail>(`/api/private-bots/admin/${privateBotId}`)
    .then(unwrapData) as Promise<PrivateBotAdminDetail>

export const disablePrivateBotAdmin = async (privateBotId: number) =>
  qqccConfigApi
    .post<PrivateBotConfigPayload>(`/api/private-bots/admin/${privateBotId}/disable`)
    .then(unwrapData) as Promise<PrivateBotConfigPayload>

export const enablePrivateBotAdmin = async (privateBotId: number) =>
  qqccConfigApi
    .post<PrivateBotConfigPayload>(`/api/private-bots/admin/${privateBotId}/enable`)
    .then(unwrapData) as Promise<PrivateBotConfigPayload>

export const deletePrivateBotAdmin = async (privateBotId: number) =>
  qqccConfigApi.delete(`/api/private-bots/admin/${privateBotId}`).then(unwrapData)
