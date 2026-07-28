import type {
  Fleet,
  ModuleCatalog,
  Operation,
  WorkspaceScan,
} from './types'

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

export const getModuleCatalog = () =>
  json<ModuleCatalog>('/api/v1/deployments/catalog')
export const scanWorkspaces = () =>
  json<WorkspaceScan>('/api/v1/workspaces/scan')
export const integrateWorkspaces = (
  expectedMainSha: string,
  slots: string[],
  confirmation: string,
) =>
  json<Operation>(
    '/api/v1/workspaces/integrate',
    mutation({
      expected_main_sha: expectedMainSha,
      slots,
      confirmation,
    }),
  )
export const alignWorkspaces = (
  expectedMainSha: string,
  slots: string[],
  confirmation: string,
) =>
  json<Operation>(
    '/api/v1/workspaces/align',
    mutation({
      expected_main_sha: expectedMainSha,
      slots,
      confirmation,
    }),
  )
export const buildModules = (
  sha: string,
  modules: string[],
  confirmation: string,
) =>
  json<Operation>(
    '/api/v1/modules/build',
    mutation({ sha, modules, confirmation }),
  )
export const deployModules = (
  environment: 'test' | 'prod',
  artifacts: Record<string, string>,
  targets: Record<string, { operator: 'runpod' | 'lan'; slot: string }>,
  confirmation: string,
) =>
  json<Operation>(
    '/api/v1/modules/deploy',
    mutation({ environment, artifacts, targets, confirmation }),
  )
