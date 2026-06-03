import { describe, expect, it } from 'vitest'

import type { HistoryItem } from '@/types/gallery'

import {
  buildWan22ChainPrefill,
  resolveWan22ReusableInputKey,
} from './wan22Chain'

const buildHistory = (overrides: Partial<HistoryItem>): HistoryItem => ({
  id: 1,
  task_id: 'task-1',
  type: 'wan22_video_v2',
  prompt: 'first prompt',
  input_file: 'bot-data/user/start.png',
  input_file_urls: ['https://cdn/start.png'],
  output_file: 'bot-data/user/out.mp4',
  output_file_url: 'https://cdn/out.mp4',
  extra_outputs: {
    last_frame: {
      path: 'tail.png',
      media_type: 'image',
      url: 'https://cdn/tail.png',
    },
  },
  result_meta: {
    wan22_negative_prompt: 'bad blur',
    wan22_resolution_preset: 'standard',
    wan22_use_end_frame: false,
  },
  created_at: '2026-06-02T00:00:00Z',
  ...overrides,
})

describe('wan22Chain helpers', () => {
  it('normalizes reusable last frame paths for Comfy input reuse', () => {
    expect(resolveWan22ReusableInputKey('tail.png')).toBe('comfyui-temp/tail.png')
    expect(resolveWan22ReusableInputKey('comfyui-temp/tail.png')).toBe('comfyui-temp/tail.png')
    expect(resolveWan22ReusableInputKey('bot-data/user/tail.png')).toBe('bot-data/user/tail.png')
    expect(resolveWan22ReusableInputKey('bot-data-test/user/tail.png')).toBe('bot-data-test/user/tail.png')
    expect(resolveWan22ReusableInputKey('template:abc')).toBe('template:abc')
  })

  it('builds extension prefill from the current segment tail frame', () => {
    const result = buildWan22ChainPrefill('extend', 'task-1', [
      buildHistory({ task_id: 'task-1' }),
    ])

    expect(result.status).toBe('ready')
    if (result.status !== 'ready') return
    expect(result.prevTaskId).toBe('task-1')
    expect(result.chainTaskIds).toEqual(['task-1'])
    expect(result.startFrame).toMatchObject({
      key: 'comfyui-temp/tail.png',
      preview: 'https://cdn/tail.png',
      locked: true,
    })
    expect(result.endFrame).toBeNull()
    expect(result.prompt).toBe('')
    expect(result.negativePrompt).toBe('bad blur')
    expect(result.resolutionPreset).toBe('standard')
  })

  it('returns blank first-segment regenerate state without reusing source assets', () => {
    const result = buildWan22ChainPrefill('regenerate', 'task-1', [
      buildHistory({ task_id: 'task-1' }),
    ])

    expect(result).toEqual({
      status: 'blank',
      mode: 'regenerate',
      sourceTaskId: 'task-1',
      segmentIndex: 1,
      chainTaskIds: [],
      prevTaskId: null,
    })
  })

  it('builds later-segment regenerate prefill from the previous segment tail frame', () => {
    const result = buildWan22ChainPrefill('regenerate', 'task-2', [
      buildHistory({ task_id: 'task-1' }),
      buildHistory({
        id: 2,
        task_id: 'task-2',
        prompt: 'second prompt',
        input_file: 'bot-data/user/previous-tail.png|bot-data/user/end.png',
        input_file_urls: ['https://cdn/previous-tail.png', 'https://cdn/end.png'],
        result_meta: {
          wan22_negative_prompt: 'low quality',
          wan22_resolution_preset: 'hd',
          wan22_use_end_frame: true,
          wan22_prev_task_id: 'task-1',
          wan22_chain_task_ids: ['task-1'],
        },
      }),
    ])

    expect(result.status).toBe('ready')
    if (result.status !== 'ready') return
    expect(result.mode).toBe('regenerate')
    expect(result.prevTaskId).toBe('task-1')
    expect(result.chainTaskIds).toEqual(['task-1'])
    expect(result.startFrame.key).toBe('comfyui-temp/tail.png')
    expect(result.endFrame).toMatchObject({
      key: 'bot-data/user/end.png',
      preview: 'https://cdn/end.png',
    })
    expect(result.prompt).toBe('second prompt')
    expect(result.negativePrompt).toBe('low quality')
    expect(result.resolutionPreset).toBe('hd')
  })

  it('reports missing tail frames before extension can be applied', () => {
    const result = buildWan22ChainPrefill('extend', 'task-1', [
      buildHistory({
        task_id: 'task-1',
        extra_outputs: {},
      }),
    ])

    expect(result).toEqual({
      status: 'error',
      reason: 'last_frame_missing',
    })
  })
})
