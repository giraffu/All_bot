import { describe, expect, it } from 'vitest'
import { resolveTemplateVideoApplyState } from './templateVideoApplyState'

describe('templateVideoApplyState', () => {
  it('restores custom_video settings and keeps controls locked', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'custom_video',
        prompt: 'cinematic action shot',
        width: 1024,
        height: 1024,
        duration: 8,
        source_post_id: 72
      },
      'custom_video'
    )

    expect(state).toEqual({
      prompt: 'cinematic action shot',
      negativePrompt: null,
      loraName: null,
      loraItems: [],
      sourcePostId: 72,
      resolution: 'hd',
      duration: '5',
      isTemplateApplied: true,
      isTemplateVideoSettingsLocked: true,
      isTemplatePromptLocked: true,
      templateApplyNotice: '已加载一键应用模板，原作品的提示词、分辨率与时长等参数已自动填入，您只需上传基础图片即可生成同款大片。',
      templateSettingsWarning: ''
    })
  })

  it('prefers persisted billing tier over raw portrait width for custom_video', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'custom_video',
        prompt: 'cinematic action shot',
        width: 640,
        height: 800,
        duration: 8,
        billing_resolution: '720'
      },
      'custom_video'
    )

    expect(state?.resolution).toBe('standard')
    expect(state?.duration).toBe('5')
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
  })

  it('falls back to normalized tier when billing tier is missing or invalid', () => {
    const missingState = resolveTemplateVideoApplyState(
      {
        task_type: 'custom_video',
        prompt: 'cinematic action shot',
        width: 720,
        height: 1280,
        duration: 8
      },
      'custom_video'
    )
    const invalidState = resolveTemplateVideoApplyState(
      {
        task_type: 'custom_video',
        prompt: 'cinematic action shot',
        width: 720,
        height: 1280,
        duration: 8,
        billing_resolution: 'bad-tier'
      },
      'custom_video'
    )

    expect(missingState?.resolution).toBe('standard')
    expect(invalidState?.resolution).toBe('standard')
    expect(missingState?.duration).toBe('5')
    expect(invalidState?.duration).toBe('5')
  })

  it('ignores legacy custom_video media duration and locks to 5s', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'custom_video',
        prompt: 'cinematic action shot',
        width: 720,
        height: 1280,
        duration: 9,
        requested_duration: null
      },
      'custom_video'
    )

    expect(state?.resolution).toBe('standard')
    expect(state?.duration).toBe('5')
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
  })

  it('keeps video settings editable when custom_video metadata is incomplete', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'custom_video',
        prompt: 'cinematic action shot',
        width: null,
        duration: null
      },
      'custom_video'
    )

    expect(state).toEqual({
      prompt: 'cinematic action shot',
      negativePrompt: null,
      loraName: null,
      loraItems: [],
      sourcePostId: null,
      resolution: null,
      duration: null,
      isTemplateApplied: true,
      isTemplateVideoSettingsLocked: false,
      isTemplatePromptLocked: true,
      templateApplyNotice: '已加载一键应用模板，原作品的提示词已自动填入；由于模板缺少完整画质信息，您仍可手动选择分辨率与时长。',
      templateSettingsWarning: '模板缺少完整的分辨率或时长信息，已保留当前画质设置供您手动调整。'
    })
  })

  it('requires both prompt and LoRA to lock video_lora prompt controls', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'video_lora',
        prompt: 'glowing neon city',
        lora_name: '',
        width: 1024,
        duration: 5
      },
      'video_lora'
    )

    expect(state?.isTemplatePromptLocked).toBe(false)
    expect(state?.templateSettingsWarning).toContain('模板缺少完整的提示词或模型信息')
  })

  it('ignores legacy video_lora media duration and locks to 5s', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'video_lora',
        prompt: 'glowing neon city',
        lora_name: 'BreastGrow',
        width: 1024,
        height: 1024,
        duration: 11,
        requested_duration: null
      },
      'video_lora'
    )

    expect(state?.resolution).toBe('hd')
    expect(state?.duration).toBe('5')
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
  })

  it('restores wan22_video_v2 prompt, negative prompt, tier settings, and fixed duration', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'wan22_video_v2',
        prompt: 'cinematic v2 motion',
        negative_prompt: 'low quality blur',
        width: 512,
        height: 768,
        duration: 13,
        requested_duration: null,
        billing_resolution: 'standard',
        source_post_id: 91
      },
      'wan22_video_v2'
    )

    expect(state?.prompt).toBe('cinematic v2 motion')
    expect(state?.negativePrompt).toBe('low quality blur')
    expect(state?.resolution).toBe('standard')
    expect(state?.duration).toBe('5')
    expect(state?.sourcePostId).toBe(91)
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
    expect(state?.isTemplatePromptLocked).toBe(true)
  })

  it('uses exact width and height for ltx_video templates', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'ltx_video',
        prompt: 'wide cinematic dolly shot',
        lora_name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
        width: 1344,
        height: 768,
        duration: 5
      },
      'ltx_video'
    )

    expect(state?.resolution).toBe('1344x768')
    expect(state?.duration).toBe('5')
    expect(state?.loraName).toBe('ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors')
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
    expect(state?.isTemplatePromptLocked).toBe(true)
  })

  it('prefers requested_duration for ltx_video templates when metadata duration is dirty', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'ltx_video',
        prompt: 'wide cinematic dolly shot',
        width: 1344,
        height: 768,
        duration: 1,
        requested_duration: 20
      },
      'ltx_video'
    )

    expect(state?.duration).toBe('20')
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
  })

  it('maps legacy ltx media duration 21s back to canonical 20s when requested_duration is missing', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'ltx_video',
        prompt: 'wide cinematic dolly shot',
        width: 512,
        height: 704,
        duration: 21,
        requested_duration: null
      },
      'ltx_video'
    )

    expect(state?.resolution).toBe('512x704')
    expect(state?.duration).toBe('20')
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
  })

  it('maps legacy ltx media duration 16s back to canonical 15s when requested_duration is missing', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'ltx_video',
        prompt: 'wide cinematic dolly shot',
        width: 512,
        height: 704,
        duration: 16,
        requested_duration: null
      },
      'ltx_video'
    )

    expect(state?.resolution).toBe('512x704')
    expect(state?.duration).toBe('15')
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
  })

  it('keeps ltx_video settings editable when legacy metadata duration is dirty and canonical duration is missing', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'ltx_video',
        prompt: 'wide cinematic dolly shot',
        width: 1344,
        height: 768,
        duration: 1,
        requested_duration: null
      },
      'ltx_video'
    )

    expect(state?.resolution).toBeNull()
    expect(state?.duration).toBeNull()
    expect(state?.isTemplateVideoSettingsLocked).toBe(false)
    expect(state?.isTemplatePromptLocked).toBe(true)
  })
})
