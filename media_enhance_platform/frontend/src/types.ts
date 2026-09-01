export type Role = 'user' | 'admin'
export type TaskType = 'image_upscale' | 'video_upscale' | 'frame_interpolation'
export type TaskStatus =
  | 'queued'
  | 'claimed'
  | 'preprocessing'
  | 'running'
  | 'uploading'
  | 'succeeded'
  | 'failed'
  | 'canceled'

export interface User {
  id: string
  email: string
  role: Role
  available_points: number
  reserved_points: number
  phone_verified: boolean
  phone_masked: string | null
}

export interface MediaFile {
  id: string
  original_name: string
  mime_type: string
  media_kind: 'image' | 'video'
  size_bytes: number
  duration_seconds: number | null
  width: number | null
  height: number | null
  is_output: boolean
  deleted_at: string | null
  created_at: string
}

export interface Attempt {
  id: string
  attempt_number: number
  status: TaskStatus
  worker_id: string | null
  error_code: string | null
  retryable: boolean
  created_at: string
}

export interface Task {
  id: string
  task_type: TaskType
  multiplier: number
  status: TaskStatus
  status_reason: string | null
  progress: number
  cost_points: number
  charged_points: number
  refunded_points: number
  source_file_id: string
  output_file_id: string | null
  error_code: string | null
  created_at: string
  updated_at: string
  attempts: Attempt[]
}

export interface Ticket {
  id: string
  task_id: string | null
  kind: 'support' | 'copyright'
  status: 'open' | 'in_progress' | 'resolved'
  email: string
  subject: string
  content: string
  admin_reply: string | null
  created_at: string
  updated_at: string
}
