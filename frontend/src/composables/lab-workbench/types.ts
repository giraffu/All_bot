import type { GenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import type { LabUploadPreviewKind, LabUploadSlotId } from '@/features/generation/labModeConfig'
import type { CharacterViewType } from '@/api/characters'

export type H3ReferenceRef =
  | { source: 'upload'; object_key: string }
  | { source: 'private_character_view'; character_id: string; view_type: CharacterViewType }

export type UploadedReference = {
  key: string
  preview: string
  name: string
  width?: number
  height?: number
  locked?: boolean
  lockedLabel?: string
  referenceRef?: H3ReferenceRef
}

export type PendingReferenceUpload = UploadedReference & {
  uploading: true
}

export type UploadedSlotAsset = UploadedReference & {
  previewKind: LabUploadPreviewKind
  uploading?: true
}

export type LabAssetUploadSlot = {
  id: LabUploadSlotId
  label: string
  hint: string
  buttonLabel: string
  accept: string
  previewKind: LabUploadPreviewKind
  required: boolean
  item: (UploadedSlotAsset & { progress?: number }) | null
}

export type TranslateFn = (key: string, params?: Record<string, unknown>) => string

export type UploadFileFn = (
  file: File,
  options?: { maxSizeBytes: number; maxSizeLabel: string },
) => Promise<string | null | undefined>

export type SubmitTaskFn = (
  payload: GenerationTaskPayload,
  taskTitle: string,
) => Promise<string | null | undefined>
