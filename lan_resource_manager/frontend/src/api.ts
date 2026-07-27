import type {
  DeploymentCatalog,
  DeploymentPlan,
  EnvironmentStatus,
  Fleet,
  IntegrationStatus,
  Operation,
  ReleaseCandidate,
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

export const getDeploymentCatalog = () =>
  json<DeploymentCatalog>('/api/v1/deployments/catalog')
export const getReleaseCandidate = () =>
  json<ReleaseCandidate>('/api/v1/releases/candidate')
export const getEnvironmentStatus = (environment: 'test' | 'prod') =>
  json<EnvironmentStatus>(`/api/v1/environments/${environment}/status`)
export const startTrustedBuild = (payload: {
  expected_main_sha: string
  confirmation: string
}) => json<Operation>('/api/v1/releases/builds', mutation(payload))
export const startGPUReleaseBuild = (payload: {
  expected_main_sha: string
  confirmation: string
}) => json<Operation>('/api/v1/releases/gpu-builds', mutation(payload))
export const syncTestConfig = (payload: {
  expected_main_sha: string
  confirmation: string
}) =>
  json<Operation>('/api/v1/environments/test/config-sync', mutation(payload))
export const createDeploymentPlan = (payload: {
  environment: 'test' | 'prod'
  module: string
  candidate_sha: string
  maintenance: 'planner' | 'rolling'
}) => json<DeploymentPlan>('/api/v1/deployment-plans', mutation(payload))
export const executeDeploymentPlan = (
  planId: string,
  confirmation: string,
) =>
  json<Operation>(
    `/api/v1/deployment-plans/${encodeURIComponent(planId)}/execute`,
    mutation({ confirmation }),
  )
export const setMaintenance = (
  environment: 'test' | 'prod',
  payload: {
    enabled: boolean
    expected_enabled: boolean
    reason: string
    confirmation: string
  },
) =>
  json<Operation>(
    `/api/v1/environments/${environment}/maintenance`,
    mutation(payload),
  )
export const getIntegrationStatus = () =>
  json<IntegrationStatus>('/api/v1/integration/status')
export const integrateAll = (expectedMainSha: string, confirmation: string) =>
  json<Operation>(
    '/api/v1/integration/run',
    mutation({ expected_main_sha: expectedMainSha, confirmation }),
  )
export const retryIntegration = (batch: string, confirmation: string) =>
  json<Operation>(
    '/api/v1/integration/retry',
    mutation({ batch, confirmation }),
  )
export const alignWorkspaces = (
  expectedMainSha: string,
  confirmation: string,
) =>
  json<Operation>(
    '/api/v1/workspaces/align',
    mutation({ expected_main_sha: expectedMainSha, confirmation }),
  )
export const deployAllTestModules = (
  candidateSha: string,
  confirmation: string,
) =>
  json<Operation>(
    '/api/v1/environments/test/deploy-all',
    mutation({ candidate_sha: candidateSha, confirmation }),
  )
