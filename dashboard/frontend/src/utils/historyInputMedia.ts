export interface HistoryInputRecord {
  type?: string | null
  input_file?: string | null
  input_file_url?: string | null
  input_file_preview_url?: string | null
}

export interface HistoryInputMediaItem {
  file: string
  url: string
  previewUrl: string
  label: string
}

const splitMediaValues = (value: string | null | undefined): string[] =>
  value ? value.split('|') : []

export const buildHistoryInputMedia = (
  record: HistoryInputRecord,
): HistoryInputMediaItem[] => {
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
