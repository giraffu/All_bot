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
        negative_prompt: '  low quality blur  ',
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
      negativePrompt: 'low quality blur',
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

  it('normalizes free edit v2 task types as workbench templates', () => {
    const normalized = normalizeTemplateApplyContext(
      {
        post_id: 19,
        source_post_id: 19,
        task_type: 'pornmaster_flux2_multi_edit',
        prompt: 'adjust clothes and lighting'
      },
      { source: 'gallery', entryEntityId: 19 }
    )

    expect(normalized).not.toBeNull()
    expect(normalized).toMatchObject({
      rawTaskType: 'pornmaster_flux2_multi_edit',
      taskType: 'pornmaster_flux2_multi_edit',
      supportMode: 'workbench',
      sourcePostId: 19,
      prompt: 'adjust clothes and lighting'
    })
  })

  it('normalizes reusable input file arrays for scail2 templates', () => {
    const normalized = normalizeTemplateApplyContext(
      {
        post_id: 22,
        source_post_id: 22,
        task_type: 'scail2_action_transfer_long',
        input_file: null,
        input_file_url: null,
        input_files: ['history/demo/motion.mp4'],
        input_file_urls: ['https://example.com/motion.mp4'],
        requested_duration: '20'
      },
      { source: 'gallery', entryEntityId: 22 }
    )

    expect(normalized).not.toBeNull()
    expect(normalized).toMatchObject({
      rawTaskType: 'scail2_action_transfer_long',
      taskType: 'scail2_action_transfer',
      supportMode: 'workbench',
      inputFile: 'history/demo/motion.mp4',
      inputFileUrl: 'https://example.com/motion.mp4',
      inputFiles: ['history/demo/motion.mp4'],
      inputFileUrls: ['https://example.com/motion.mp4'],
      requestedDuration: 20
    })
  })
})
