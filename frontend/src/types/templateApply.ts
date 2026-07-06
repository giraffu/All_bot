export type TemplateApplySource = 'gallery' | 'favorites' | 'submissions'

export type TemplateApplyTaskType =
  | 'i2i_pro'
  | 'i2i_draw'
  | 'edit'
  | 'img2img_lora'
  | 'pornmaster_flux2_single_edit'
  | 'pornmaster_flux2_multi_edit'
  | 'face_swap'
  | 'face_video'
  | 'custom_video'
  | 'video_lora'
  | 'wan22_video_v2'
  | 'ltx_video'
  | 'scail2_action_transfer'
  | 'scail2_action_transfer_long'
  | 'scail2_video_replacement'
  | 'scail2_face_swap_v2'

export type TemplateApplyPanelKind =
  | 'imagePrompt'
  | 'imageToVideo'
  | 'faceSwap'
  | 'videoSwap'
  | 'scail2Video'

export interface RawApplyContextResponse {
  post_id: unknown
  source_post_id?: unknown
  billing_resolution?: unknown
  requested_duration?: unknown
  task_id?: unknown
  media_type?: unknown
  prompt?: unknown
  negative_prompt?: unknown
  lora_name?: unknown
  lora_strength?: unknown
  lora_items?: unknown
  input_file?: unknown
  input_file_url?: unknown
  input_files?: unknown
  input_file_urls?: unknown
  width?: unknown
  height?: unknown
  duration?: unknown
  task_type: unknown
}

export interface NormalizeContextOptions {
  source: TemplateApplySource
  entryEntityId: number | string | null
}

export interface TemplateApplyContext {
  raw: RawApplyContextResponse
  source: TemplateApplySource
  entryEntityId: number | string | null
  rawEntityId: number | null
  rawTaskType: string
  taskType: TemplateApplyTaskType | null
  sourcePostId: number | null
  prompt: string | null
  negativePrompt: string | null
  loraName: string | null
  loraStrength: number | null
  loraItems: Array<{ name: string; strength: number }>
  inputFile: string | null
  inputFileUrl: string | null
  inputFiles?: string[]
  inputFileUrls?: string[]
  width: number | null
  height: number | null
  duration: number | null
  requestedDuration: number | null
  billingResolution: string | null
}

export interface TemplateTaskMeta {
  taskType: TemplateApplyTaskType
  panelKind: TemplateApplyPanelKind
  titleKey: string
}

export interface TemplateApplySessionMeta {
  sessionId: string
  source: TemplateApplySource
  entryEntityId: number | string | null
  openedAt: number
}

export interface TemplateApplyPanelController {
  sessionId: string
  cleanup: () => Promise<void> | void
}

export interface OpenTemplateApplyParams {
  source: TemplateApplySource
  entryEntityId: number | string | null
  rawContext: RawApplyContextResponse
}

export type CloseTrigger =
  | 'user_close'
  | 'mask_close'
  | 'esc'
  | 'gesture_close'
  | 'route_leave'
  | 'open_replace'

export type CloseConfirmReason =
  | 'dirty'
  | 'uploading'
  | 'dirty_and_uploading'

export type RequestCloseResult =
  | { status: 'close_now' }
  | {
      status: 'confirm_required'
      trigger: CloseTrigger
      confirmReason: CloseConfirmReason
    }
  | { status: 'blocked'; reason: 'opening' | 'closing' }

export type OpenTemplateApplyResult =
  | { status: 'opened'; sessionId: string }
  | {
      status: 'unsupported'
      rawTaskType: string
      context: TemplateApplyContext
    }
  | { status: 'invalid'; message: string }
  | {
      status: 'confirm_required'
      trigger: 'open_replace'
      confirmReason: CloseConfirmReason
    }
  | { status: 'blocked'; reason: 'opening' | 'closing' }
