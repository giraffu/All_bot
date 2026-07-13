import axios from 'axios'
import type { AxiosResponse } from 'axios'

import { resolveQqccApiBaseUrl } from './qqccConfigApi'
import type {
  PrivateBotConfigPayload,
  PrivateBotRuntimeStatus,
  PrivateBotStatusPayload,
} from './qqccConfigApi'
import {
  clearPrivateBotOwnerToken,
  getPrivateBotOwnerToken,
} from '../composables/usePrivateBotOwnerAuth'

export type PrivateBotOwnerBot = PrivateBotStatusPayload

export type PrivateBotOwnerMeResponse = PrivateBotConfigPayload

export interface PrivateBotCredentialUpdateResponse extends PrivateBotOwnerMeResponse {
  provision: {
    created: boolean
    runtime_status: PrivateBotRuntimeStatus
  }
}

export interface PrivateBotOwnerTokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface PrivateBotOwnerConfigUpdate {
  config_version: number
  config: unknown
}

const unwrapData = <T>(response: AxiosResponse<T>) => response.data

export const privateBotOwnerApi = axios.create({
  baseURL: resolveQqccApiBaseUrl(),
})

privateBotOwnerApi.interceptors.request.use((config) => {
  const token = getPrivateBotOwnerToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

privateBotOwnerApi.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      clearPrivateBotOwnerToken()
    }
    return Promise.reject(error)
  },
)

export const exchangePrivateBotOwnerTicket = async (ticket: string) =>
  privateBotOwnerApi
    .post<PrivateBotOwnerTokenResponse>('/api/private-bots/owner/auth/exchange', { ticket })
    .then(unwrapData)

export const fetchPrivateBotOwnerMe = async () =>
  privateBotOwnerApi
    .get<PrivateBotOwnerMeResponse>('/api/private-bots/owner/me', {
      params: { _t: Date.now() },
    })
    .then(unwrapData)

export const updatePrivateBotOwnerConfig = async (payload: PrivateBotOwnerConfigUpdate) =>
  privateBotOwnerApi
    .put<PrivateBotOwnerMeResponse>('/api/private-bots/owner/config', payload)
    .then(unwrapData)

export const pausePrivateBotOwner = async () =>
  privateBotOwnerApi
    .post<PrivateBotOwnerMeResponse>('/api/private-bots/owner/pause')
    .then(unwrapData)

export const resumePrivateBotOwner = async () =>
  privateBotOwnerApi
    .post<PrivateBotOwnerMeResponse>('/api/private-bots/owner/resume')
    .then(unwrapData)

export const retryPrivateBotOwner = async () =>
  privateBotOwnerApi
    .post<PrivateBotOwnerMeResponse>('/api/private-bots/owner/retry')
    .then(unwrapData)

export const updatePrivateBotOwnerCredentials = async (token: string) =>
  privateBotOwnerApi
    .put<PrivateBotCredentialUpdateResponse>('/api/private-bots/owner/credentials', { token })
    .then(unwrapData)

export const uploadPrivateBotOwnerDemoMedia = async (
  sceneKind: 'video' | 'draw' | 'filter',
  sceneId: string,
  slot: 'input' | 'output',
  file: File,
) => {
  const formData = new FormData()
  formData.append('file', file)
  return privateBotOwnerApi
    .post(
      `/api/private-bots/owner/demo-media/${encodeURIComponent(sceneKind)}/${encodeURIComponent(sceneId)}/${encodeURIComponent(slot)}`,
      formData,
    )
    .then(unwrapData)
}

export const generatePrivateBotOwnerDemoMedia = async (sceneKind: string, scene: unknown) =>
  privateBotOwnerApi.post(`/api/private-bots/owner/demo-generation/${encodeURIComponent(sceneKind)}`, { scene }).then(unwrapData)

export const getPrivateBotOwnerDemoGeneration = async (sceneKind: string, sceneId: string, generationId: string) =>
  privateBotOwnerApi.get(`/api/private-bots/owner/demo-generation/${encodeURIComponent(sceneKind)}/${encodeURIComponent(sceneId)}/${encodeURIComponent(generationId)}`).then(unwrapData)
