// @vitest-environment jsdom

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
      prompt: 'demo'
    })
  })

  it('treats disabled i2i draw templates as unsupported without dropping context', () => {
    const normalized = normalizeTemplateApplyContext(
      {
        post_id: 8,
        source_post_id: 8,
        task_type: 'i2i_draw',
        prompt: 'repaint local area'
      },
      { source: 'gallery', entryEntityId: 8 }
    )

    expect(normalized).not.toBeNull()
    expect(normalized).toMatchObject({
      rawTaskType: 'i2i_draw',
      taskType: null,
      sourcePostId: 8,
      prompt: 'repaint local area'
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
      sourcePostId: 18,
      inputFile: 'history/demo/original.png'
    })
  })

  it('normalizes LTX FLF2V execution alias to the shared high-res video task type', () => {
    const normalized = normalizeTemplateApplyContext(
      {
        post_id: 20,
        source_post_id: 20,
        task_type: 'ltx_video_flf2v',
        input_files: ['history/demo/start.png', 'history/demo/end.png'],
        input_file_urls: ['https://example.com/start.png', 'https://example.com/end.png'],
        requested_duration: 20,
        width: 1344,
        height: 768
      },
      { source: 'gallery', entryEntityId: 20 }
    )

    expect(normalized).not.toBeNull()
    expect(normalized).toMatchObject({
      rawTaskType: 'ltx_video_flf2v',
      taskType: 'ltx_video',
      sourcePostId: 20,
      inputFiles: ['history/demo/start.png', 'history/demo/end.png'],
      inputFileUrls: ['https://example.com/start.png', 'https://example.com/end.png'],
      requestedDuration: 20,
      width: 1344,
      height: 768
    })
  })

  it('canonicalizes historical free edit task types to v3 templates', () => {
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
      taskType: 'pornmaster_flux2_edit_bf16',
      sourcePostId: 19,
      prompt: 'adjust clothes and lighting'
    })
  })

  it('preserves free edit v2.5 as an independent template type', () => {
    const normalized = normalizeTemplateApplyContext(
      {
        post_id: 25,
        source_post_id: 25,
        task_type: 'free_edit_v2_5',
        prompt: 'preserve this prompt',
        required_image_count: 2
      },
      { source: 'gallery', entryEntityId: 25 }
    )

    expect(normalized).not.toBeNull()
    expect(normalized).toMatchObject({
      rawTaskType: 'free_edit_v2_5',
      taskType: 'free_edit_v2_5',
      sourcePostId: 25,
      prompt: 'preserve this prompt',
      requiredImageCount: 2
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
      inputFile: 'history/demo/motion.mp4',
      inputFileUrl: 'https://example.com/motion.mp4',
      inputFiles: ['history/demo/motion.mp4'],
      inputFileUrls: ['https://example.com/motion.mp4'],
      requestedDuration: 20
    })
  })

  it('normalizes MiniMax H3 locked context with its public addon catalog', () => {
    window.__ALLBOT_CONFIG__ = { enable_minimax_h3: true }
    const normalized = normalizeTemplateApplyContext(
      {
        post_id: 31,
        source_post_id: 31,
        task_type: 'minimax_h3_flf2v',
        prompt: 'locked motion',
        requested_duration: 10,
        required_image_count: 2,
        resolution_preset: 'standard',
        aspect_ratio: 'source',
        lora_items: [
          { name: 'sex_pose', strength: 0.5 },
          { name: 'naughty_times', strength: 1.2 },
          { name: 'ltx2.3/not-allowed.safetensors', strength: 1 },
        ],
        reference_audio_ref: { source: 'gallery_post', post_id: '31' },
        reference_audio_url: 'https://example.com/voice.m4a',
      },
      { source: 'gallery', entryEntityId: 31 }
    )

    expect(normalized).toMatchObject({
      rawTaskType: 'minimax_h3_flf2v',
      taskType: 'minimax_h3_flf2v',
      sourcePostId: 31,
      requestedDuration: 10,
      requiredImageCount: 2,
      resolutionPreset: 'standard',
      aspectRatio: 'source',
      loraItems: [
        { name: 'sex_pose', strength: 0.5 },
        { name: 'naughty_times', strength: 1.2 },
      ],
      referenceAudioRef: { source: 'gallery_post', post_id: 31 },
      referenceAudioUrl: 'https://example.com/voice.m4a',
    })
  })
})
