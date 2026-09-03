export interface HistoryInputRecord {
  type?: string | null
  input_file?: string | null
  input_file_url?: string | null
  input_file_preview_url?: string | null
  input_media?: Array<{
    file: string
    url: string
    preview_url?: string | null
    resolve_url?: string | null
    kind: 'image' | 'video' | 'audio'
    label?: string | null
  }> | null
}

export interface HistoryInputMediaItem {
  file: string
  url: string
  previewUrl: string
  label: string
  kind?: 'image' | 'video' | 'audio'
  resolveUrl?: string
}

const splitMediaValues = (value: string | null | undefined): string[] =>
  value ? value.split('|') : []

export const buildHistoryInputMedia = (
  record: HistoryInputRecord,
): HistoryInputMediaItem[] => {
  if (record.input_media) {
    return record.input_media.map((media) => ({
      file: media.file,
      url: media.url,
      previewUrl: media.preview_url || '',
      resolveUrl: media.resolve_url || '',
      label: media.label || '',
      kind: media.kind,
    }))
  }

  const files = splitMediaValues(record.input_file).filter(Boolean)
  const urls = splitMediaValues(record.input_file_url)
  const previewUrls = splitMediaValues(record.input_file_preview_url)
  const isH3ReferenceVideo = record.type === 'minimax_h3_ref2v'

  return files.map((file, index) => ({
    file,
    url: urls[index] || '',
    previewUrl: previewUrls[index] || '',
    label: isH3ReferenceVideo ? `参考图 ${index + 1}` : '',
  }))
}
