export interface Candidate {
  slot_id: string
  profile: string
  phase: string
  enabled: boolean
  retargetable: boolean
  switchable: boolean
  task_types: string[]
  cache?: { cache_state?: string; synced_at?: string } | null
  notes?: string | null
}

export interface PhysicalSlot {
  physical_slot: string
  node_id: string
  gpu_index: number
  host_port: number
  current?: {
    slot_id: string
    profile: string
    state?: string
  } | null
  intentionally_empty?: { reason?: string } | null
  worker?: {
    status?: string
    current_task_id?: string | null
    current_task_type?: string | null
  } | null
  candidates: Candidate[]
  blocked_observations: Array<{ profile?: string; reason?: string }>
  last_verified_at?: string | null
}

export interface Operation {
  operation_id: string
  kind:
    | 'refresh'
    | 'switch'
    | 'build'
    | 'gpu-release-build'
    | 'test-config-sync'
    | 'deploy'
    | 'deploy-all-test'
    | 'maintenance'
    | 'integration'
    | 'integration-retry'
    | 'workspace-align'
  status: string
  stage: string
  request: Record<string, string | null>
  started_at: string
  updated_at: string
  finished_at?: string | null
  error_code?: string | null
}

export interface IntegrationStatus {
  main_sha: string
  queue: Record<
    'pending' | 'running' | 'failed',
    Array<{
      id: string
      status: string
      stage?: string | null
      branch?: string | null
      head?: string | null
      main_sha?: string | null
      error?: string | null
      members?: Array<{ slot?: string; branch?: string; head?: string }>
    }>
  >
  slots: Array<{
    slot: string
    branch?: string | null
    head?: string | null
    clean: boolean
    at_base: boolean
    safe_to_assign?: boolean
  }>
}

export interface DeploymentCatalog {
  modules: Record<string, { artifacts: string[] }>
  environments: Record<
    'test' | 'prod',
    { label: string; modules: string[]; maintenance_supported: boolean }
  >
}

export interface ReleaseCandidate {
  main_sha: string
  deployable_sha?: string | null
  scope: string
  ci?: { status?: string; conclusion?: string | null; run_id?: number } | null
  bundle: { status: string }
  build?: { status?: string; conclusion?: string | null; run_id?: number } | null
  blockers: string[]
}

export interface EnvironmentStatus {
  environment: 'test' | 'prod'
  current_sha?: string | null
  artifacts?: Record<string, { digest?: string; source_sha?: string }>
  health?: Record<string, string>
  config_revision?: string | null
  maintenance: {
    enabled: boolean
    owner?: string | null
    reason?: string | null
    can_disable: boolean
  }
  active_transaction?: { transaction?: string; status?: string } | null
  config_drift: boolean
}

export interface DeploymentPlan {
  plan_id: string
  environment: 'test' | 'prod'
  module: string
  candidate_sha: string
  maintenance: 'planner' | 'rolling'
  expires_at: string
  preview: {
    status?: string
    artifacts?: Record<string, { digest?: string }>
    maintenance_required?: boolean
    blockers?: string[]
  }
}

export interface Fleet {
  physical_slots: PhysicalSlot[]
  state: {
    status: string
    drift: Array<{ kind?: string; physical_slot?: string | null }>
    captured_at?: string | null
    stale: boolean
  }
  active_operation?: Operation | null
}
