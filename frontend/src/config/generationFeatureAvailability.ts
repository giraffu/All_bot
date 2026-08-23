import { getRuntimeFlag } from '@/config/runtime'

export const isLtxVideoFeatureEnabled = (): boolean =>
  getRuntimeFlag('enable_ltx_video', true)

export const isMinimaxH3FeatureEnabled = (): boolean =>
  getRuntimeFlag('enable_minimax_h3', false)

export const isMinimaxH3EntryEnabled = (): boolean =>
  isMinimaxH3FeatureEnabled()
  && getRuntimeFlag('enable_minimax_h3_entry', false)

export const isGenerationTaskTypeEnabled = (taskType: string): boolean => {
  if (taskType === 'ltx_video' || taskType === 'ltx_video_flf2v') {
    return isLtxVideoFeatureEnabled()
  }
  if (taskType === 'minimax_h3' || taskType.startsWith('minimax_h3_')) {
    return isMinimaxH3FeatureEnabled()
  }
  return true
}

export const isGenerationTaskTypeEntryEnabled = (taskType: string): boolean => {
  if (taskType === 'minimax_h3' || taskType.startsWith('minimax_h3_')) {
    return isMinimaxH3EntryEnabled()
  }
  return isGenerationTaskTypeEnabled(taskType)
}
