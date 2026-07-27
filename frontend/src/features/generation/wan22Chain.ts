import type { HistoryItem } from '@/types/gallery'
import { resolveMediaUrl } from '@/utils/mediaUrl'

import {
  DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
  DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET,
  normalizeWan22VideoV2DurationSeconds,
  normalizeWan22VideoV2ResolutionPreset,
  type Wan22VideoV2DurationSeconds,
  type Wan22VideoV2ResolutionPreset,
} from './imageToVideo'

export type Wan22ChainEditMode = 'extend' | 'regenerate'

export type Wan22ChainPrefillAsset = {
  key: string
  preview: string
  name: string
  locked?: boolean
  lockedLabel?: string
}

export type Wan22ChainPrefillErrorReason =
  | 'history_empty'
  | 'record_not_found'
  | 'last_frame_missing'
  | 'previous_record_missing'
  | 'previous_last_frame_missing'

export type Wan22ChainPrefillResult =
  | {
      status: 'ready'
      mode: Wan22ChainEditMode
      sourceTaskId: string
      taskType: string
      prevTaskId: string | null
      chainTaskIds: string[]
      startFrame: Wan22ChainPrefillAsset
      endFrame: Wan22ChainPrefillAsset | null
      prompt: string
      negativePrompt: string
      resolutionPreset: Wan22VideoV2ResolutionPreset
      duration: Wan22VideoV2DurationSeconds
      loraName: string | null
      segmentIndex: number
      contextCount: number
    }
  | {
      status: 'blank'
      mode: 'regenerate'
      sourceTaskId: string
      taskType: string
      segmentIndex: 1
      chainTaskIds: []
      prevTaskId: null
    }
  | {
      status: 'error'
      reason: Wan22ChainPrefillErrorReason
    }

const REUSABLE_INPUT_PREFIXES = [
  'comfyui-temp/',
  'bot-data/',
  'bot-data-test/',
  'template:',
]

export const resolveWan22ReusableInputKey = (path?: string | null) => {
  const normalizedPath = String(path || '').trim()
  if (!normalizedPath) {
    return ''
  }
  if (REUSABLE_INPUT_PREFIXES.some(prefix => normalizedPath.startsWith(prefix))) {
    return normalizedPath
  }
  return `comfyui-temp/${normalizedPath}`
}

const normalizeTaskIds = (items: HistoryItem[]) =>
  items
    .map(item => String(item.task_id || '').trim())
    .filter((taskId): taskId is string => Boolean(taskId))

const resolveNegativePrompt = (record: HistoryItem) =>
  record.result_meta?.wan22_negative_prompt || DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT

const resolveResolutionPreset = (record: HistoryItem) =>
  normalizeWan22VideoV2ResolutionPreset(
    record.result_meta?.wan22_resolution_preset || DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET,
  )

const resolveDuration = (record: HistoryItem) =>
  normalizeWan22VideoV2DurationSeconds(
    record.result_meta?.wan22_duration_seconds
    ?? record.requested_duration
    ?? record.duration
  )

const buildLastFrameAsset = (
  record: HistoryItem,
  segmentIndex: number,
  lockedLabel: string,
): Wan22ChainPrefillAsset | null => {
  const lastFrame = record.extra_outputs?.last_frame
  const key = resolveWan22ReusableInputKey(lastFrame?.path)
  if (!key) {
    return null
  }
  return {
    key,
    preview: lastFrame?.url || resolveMediaUrl(key),
    name: `第 ${segmentIndex} 段尾帧`,
    locked: true,
    lockedLabel,
  }
}

const buildEndFrameAsset = (record: HistoryItem): Wan22ChainPrefillAsset | null => {
  if (!record.result_meta?.wan22_use_end_frame) {
    return null
  }
  const endKey = record.input_file?.split('|')[1]?.trim()
  if (!endKey) {
    return null
  }
  return {
    key: endKey,
    preview: record.input_file_urls?.[1] || resolveMediaUrl(endKey),
    name: '终止帧',
  }
}

export const buildWan22ChainPrefill = (
  mode: Wan22ChainEditMode,
  taskId: string,
  items: HistoryItem[],
): Wan22ChainPrefillResult => {
  if (!items.length) {
    return { status: 'error', reason: 'history_empty' }
  }

  const currentRecord = items.find(item => item.task_id === taskId)
  if (!currentRecord?.task_id) {
    return { status: 'error', reason: 'record_not_found' }
  }

  const recordIndex = items.findIndex(item => item.task_id === currentRecord.task_id)
  const segmentIndex = recordIndex + 1
  const allChainTaskIds = normalizeTaskIds(items)

  if (mode === 'extend') {
    const startFrame = buildLastFrameAsset(currentRecord, segmentIndex, '上一段尾帧')
    if (!startFrame) {
      return { status: 'error', reason: 'last_frame_missing' }
    }

    return {
      status: 'ready',
      mode,
      sourceTaskId: currentRecord.task_id,
      taskType: currentRecord.type || 'wan22_video_v2',
      prevTaskId: currentRecord.task_id,
      chainTaskIds: allChainTaskIds,
      startFrame,
      endFrame: null,
      prompt: '',
      negativePrompt: resolveNegativePrompt(currentRecord),
      resolutionPreset: resolveResolutionPreset(currentRecord),
      duration: resolveDuration(currentRecord),
      loraName: currentRecord.result_meta?.lora_name || null,
      segmentIndex,
      contextCount: allChainTaskIds.length,
    }
  }

  const previousRecord = recordIndex > 0 ? items[recordIndex - 1] : null
  if (!previousRecord) {
    return {
      status: 'blank',
      mode: 'regenerate',
      sourceTaskId: currentRecord.task_id,
      taskType: currentRecord.type || 'wan22_video_v2',
      segmentIndex: 1,
      chainTaskIds: [],
      prevTaskId: null,
    }
  }
  if (!previousRecord.task_id) {
    return { status: 'error', reason: 'previous_record_missing' }
  }

  const startFrame = buildLastFrameAsset(previousRecord, recordIndex, '上一段尾帧')
  if (!startFrame) {
    return { status: 'error', reason: 'previous_last_frame_missing' }
  }

  const contextTaskIds = normalizeTaskIds(items.slice(0, recordIndex))
  return {
    status: 'ready',
    mode,
    sourceTaskId: currentRecord.task_id,
    taskType: currentRecord.type || 'wan22_video_v2',
    prevTaskId: previousRecord.task_id,
    chainTaskIds: contextTaskIds,
    startFrame,
    endFrame: buildEndFrameAsset(currentRecord),
    prompt: currentRecord.prompt || '',
    negativePrompt: resolveNegativePrompt(currentRecord),
    resolutionPreset: resolveResolutionPreset(currentRecord),
    duration: resolveDuration(currentRecord),
    loraName: currentRecord.result_meta?.lora_name || null,
    segmentIndex,
    contextCount: contextTaskIds.length,
  }
}
