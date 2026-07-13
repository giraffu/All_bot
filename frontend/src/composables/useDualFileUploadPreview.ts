import { onBeforeUnmount, ref, watch } from 'vue'

type UploadFileFn = (file: File) => Promise<string | null | undefined>

type UploadEntry = {
  originFileObj?: File
} | File

type TemplateTarget = {
  objectKey: string
  previewUrl?: string | null
}

function revokePreviewUrl(url: string | null) {
  if (url?.startsWith('blob:')) {
    URL.revokeObjectURL(url)
  }
}

function resolveUploadFile(entry: UploadEntry | undefined): File | null {
  if (!entry) {
    return null
  }

  if (entry instanceof File) {
    return entry
  }

  return entry.originFileObj ?? null
}

function createPreviewState() {
  return {
    fileList: ref<UploadEntry[]>([]),
    objectKey: ref<string | null>(null),
    previewUrl: ref<string | null>(null),
  }
}

export function useDualFileUploadPreview(options: { uploadFile: UploadFileFn }) {
  const { uploadFile } = options
  const primary = createPreviewState()
  const secondary = createPreviewState()

  const syncPreview = (fileList: typeof primary.fileList, previewUrl: typeof primary.previewUrl) => {
    watch(fileList, (nextFiles) => {
      const rawFile = resolveUploadFile(nextFiles[0])
      if (!rawFile) {
        revokePreviewUrl(previewUrl.value)
        previewUrl.value = null
        return
      }

      revokePreviewUrl(previewUrl.value)
      previewUrl.value = URL.createObjectURL(rawFile)
    })
  }

  syncPreview(primary.fileList, primary.previewUrl)
  syncPreview(secondary.fileList, secondary.previewUrl)

  const uploadSingle = async (
    state: typeof primary,
    file: File,
  ) => {
    state.fileList.value = [file]
    const key = await uploadFile(file)
    if (key) {
      state.objectKey.value = key
    }
    return false
  }

  const resetState = (state: typeof primary) => {
    state.fileList.value = []
    state.objectKey.value = null
  }

  const applySecondaryTemplateTarget = ({ objectKey, previewUrl }: TemplateTarget) => {
    secondary.fileList.value = []
    secondary.objectKey.value = objectKey
    revokePreviewUrl(secondary.previewUrl.value)
    secondary.previewUrl.value = previewUrl ?? null
  }

  const resetAll = () => {
    resetState(primary)
    resetState(secondary)
  }

  onBeforeUnmount(() => {
    revokePreviewUrl(primary.previewUrl.value)
    revokePreviewUrl(secondary.previewUrl.value)
  })

  return {
    primaryFileList: primary.fileList,
    secondaryFileList: secondary.fileList,
    primaryObjectKey: primary.objectKey,
    secondaryObjectKey: secondary.objectKey,
    primaryPreviewUrl: primary.previewUrl,
    secondaryPreviewUrl: secondary.previewUrl,
    beforeUploadPrimary: (file: File) => uploadSingle(primary, file),
    beforeUploadSecondary: (file: File) => uploadSingle(secondary, file),
    removePrimary: () => resetState(primary),
    removeSecondary: () => resetState(secondary),
    applySecondaryTemplateTarget,
    resetAll,
  }
}
