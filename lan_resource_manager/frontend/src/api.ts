import type { Fleet, Operation } from './types'

let csrfToken = ''

async function json<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export async function initializeSecurity(): Promise<void> {
  const payload = await json<{ csrf_token: string }>('/api/v1/security/csrf')
  csrfToken = payload.csrf_token
}

function mutation(body: object): RequestInit {
  return {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-csrf-token': csrfToken,
    },
    body: JSON.stringify(body),
  }
}

export const getFleet = () => json<Fleet>('/api/v1/fleet')
export const refreshFleet = () =>
  json<Operation>('/api/v1/fleet/refresh', mutation({}))
export const switchProfile = (
  nodeId: string,
  gpuIndex: number,
  payload: {
    target_slot_id: string
    expected_current_slot_id: string | null
    confirmation_profile: string
  },
) =>
  json<Operation>(
    `/api/v1/physical-slots/${encodeURIComponent(nodeId)}/${gpuIndex}/switches`,
    mutation(payload),
  )
export const getOperation = (id: string) =>
  json<Operation>(`/api/v1/operations/${encodeURIComponent(id)}`)
