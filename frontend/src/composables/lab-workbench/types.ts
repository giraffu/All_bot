import type { GenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import type { LabUploadPreviewKind, LabUploadSlotId } from '@/features/generation/labModeConfig'

export type UploadedReference = {
  key: string
  preview: string
  name: string
  locked?: boolean
  lockedLabel?: string
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
