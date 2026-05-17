import { describe, expect, it } from 'vitest'
import { normalizeTemplateApplyContext } from '@/utils/normalizeTemplateApplyContext'

describe('normalizeTemplateApplyContext', () => {
  it('returns null when raw context is missing or invalid', () => {
    expect(normalizeTemplateApplyContext(null, { source: 'gallery', entryEntityId: 1 })).toBeNull()
    expect(
      normalizeTemplateApplyContext(
        {
          task_type: '',
          post_id: null
        } as any,
        { source: 'gallery', entryEntityId: 1 }
      )
    ).toBeNull()
  })

  it('normalizes supported workbench tasks with numeric fields', () => {
    const normalized = normalizeTemplateApplyContext(
      {
        post_id: '12',
        source_post_id: '88',
        billing_resolution: '1024p',
        requested_duration: '10',
        task_id: 'task_1',
        media_type: 'image',
        prompt: '  cinematic portrait  ',
        lora_name: 'qwen/test.safetensors',
        lora_strength: '0.75',
        input_file: 'history/demo/original.png',
        input_file_url: 'https://example.com/demo.png',
        width: '1024',
        height: '768',
        duration: '8',
        task_type: 'face_swap'
      },
      { source: 'gallery', entryEntityId: '12' }
    )

    expect(normalized).not.toBeNull()
    expect(normalized).toMatchObject({
      rawTaskType: 'face_swap',
      taskType: 'face_swap',
      supportMode: 'workbench',
      rawEntityId: 12,
      sourcePostId: 88,
      prompt: 'cinematic portrait',
      loraName: 'qwen/test.safetensors',
      loraStrength: 0.75,
      inputFile: 'history/demo/original.png',
      inputFileUrl: 'https://example.com/demo.png',
      width: 1024,
      height: 768,
      duration: 8,
      requestedDuration: 10,
      billingResolution: '1024p'
    })
  })

  it('marks unknown task types as unsupported without dropping context', () => {
    const normalized = normalizeTemplateApplyContext(
      {
        post_id: 7,
        task_type: 'unknown_video_task',
        prompt: 'demo'
      },
      { source: 'favorites', entryEntityId: 7 }
    )

    expect(normalized).not.toBeNull()
    expect(normalized).toMatchObject({
      rawTaskType: 'unknown_video_task',
      taskType: null,
      supportMode: 'unknown',
      prompt: 'demo'
    })
  })

  it('normalizes known legacy aliases to canonical task types', () => {
    const normalized = normalizeTemplateApplyContext(
      {
        post_id: 18,
        source_post_id: 18,
        task_type: 'faceswap',
        input_file: 'history/demo/original.png'
      },
      { source: 'gallery', entryEntityId: 18 }
    )

    expect(normalized).not.toBeNull()
    expect(normalized).toMatchObject({
      rawTaskType: 'faceswap',
      taskType: 'face_swap',
      supportMode: 'workbench',
      sourcePostId: 18,
      inputFile: 'history/demo/original.png'
    })
  })
})
