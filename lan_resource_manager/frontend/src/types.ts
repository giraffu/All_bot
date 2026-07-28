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
  current?: { slot_id: string; profile: string; state?: string } | null
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
  kind: string
  status: string
  stage: string
  request: Record<string, string | null>
  result?: Record<string, unknown> | null
  started_at: string
  updated_at: string
  finished_at?: string | null
  error_code?: string | null
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

export interface WorkspaceRow {
  slot: string
  branch?: string | null
  head?: string | null
  clean: boolean
  at_base: boolean
  safe_to_assign?: boolean
}

export interface HandoffRow {
  id: string
  slot?: string | null
  branch?: string | null
  head?: string | null
  status: string
  main_sha?: string | null
  reason?: string | null
  conflict_files?: string[]
}

export interface WorkspaceScan {
  main_sha: string
  slots: WorkspaceRow[]
  queue: Record<
    'pending' | 'integrating' | 'needs-rebase' | 'completed',
    HandoffRow[]
  >
}

export interface ModuleInfo {
  kind: string
  adapter: string
  environments: Array<'test' | 'prod'>
  build_only: boolean
  requires_target: boolean
}

export interface ModuleCatalog {
  modules: Record<string, ModuleInfo>
}
