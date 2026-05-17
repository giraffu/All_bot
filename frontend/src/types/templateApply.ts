export type TemplateApplySource = 'gallery' | 'favorites' | 'submissions'

export type TemplateApplyTaskType =
  | 'i2i_pro'
  | 'i2i_draw'
  | 'edit'
  | 'img2img_lora'
  | 'face_swap'
  | 'face_video'
  | 'custom_video'
  | 'video_lora'
  | 'ltx_video'

export type TemplateApplySupportMode = 'workbench' | 'legacy' | 'unknown'
export type TemplateApplyPreferredMode = 'workbench' | 'legacy'

export type TemplateApplyPanelKind =
  | 'imagePrompt'
  | 'imageToVideo'
  | 'faceSwap'
  | 'videoSwap'

export interface RawApplyContextResponse {
  post_id: unknown
  source_post_id?: unknown
  billing_resolution?: unknown
  requested_duration?: unknown
  task_id?: unknown
  media_type?: unknown
  prompt?: unknown
  lora_name?: unknown
  lora_strength?: unknown
  input_file?: unknown
  input_file_url?: unknown
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
  supportMode: TemplateApplySupportMode
  sourcePostId: number | null
  prompt: string | null
  loraName: string | null
  loraStrength: number | null
  inputFile: string | null
  inputFileUrl: string | null
  width: number | null
  height: number | null
  duration: number | null
  requestedDuration: number | null
  billingResolution: string | null
}

export type LegacyQueryBuilder = (
  ctx: TemplateApplyContext,
  t: (key: string) => string
) => Record<string, string>

export interface TemplateTaskMeta {
  taskType: TemplateApplyTaskType
  supportMode: Exclude<TemplateApplySupportMode, 'unknown'>
  panelKind?: TemplateApplyPanelKind
  legacyRouteName: string
  legacyTitleKey: string
  legacyCost: number
  buildLegacyQuery: LegacyQueryBuilder
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
  preferredMode?: TemplateApplyPreferredMode
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
      status: 'legacy_fallback'
      fallbackKind: 'legacy_supported' | 'unknown_task_type'
      rawTaskType: string
      context: TemplateApplyContext | null
      meta: TemplateTaskMeta | null
    }
  | { status: 'invalid'; message: string }
  | {
      status: 'confirm_required'
      trigger: 'open_replace'
      confirmReason: CloseConfirmReason
    }
  | { status: 'blocked'; reason: 'opening' | 'closing' }
