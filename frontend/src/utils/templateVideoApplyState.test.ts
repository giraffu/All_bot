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
      loraName: null,
      sourcePostId: 72,
      resolution: '1024',
      duration: '8',
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

    expect(state?.resolution).toBe('720')
    expect(state?.duration).toBe('8')
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
  })

  it('falls back to normalized tier when billing tier is missing or invalid', () => {
    const missingState = resolveTemplateVideoApplyState(
      {
        task_type: 'custom_video',
        prompt: 'cinematic action shot',
        width: 640,
        height: 800,
        duration: 8
      },
      'custom_video'
    )
    const invalidState = resolveTemplateVideoApplyState(
      {
        task_type: 'custom_video',
        prompt: 'cinematic action shot',
        width: 640,
        height: 800,
        duration: 8,
        billing_resolution: 'bad-tier'
      },
      'custom_video'
    )

    expect(missingState?.resolution).toBe('720')
    expect(invalidState?.resolution).toBe('720')
    expect(missingState?.duration).toBe('8')
    expect(invalidState?.duration).toBe('8')
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
      loraName: null,
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

  it('uses exact width and height for ltx_video templates', () => {
    const state = resolveTemplateVideoApplyState(
      {
        task_type: 'ltx_video',
        prompt: 'wide cinematic dolly shot',
        width: 1344,
        height: 768,
        duration: 5
      },
      'ltx_video'
    )

    expect(state?.resolution).toBe('1344x768')
    expect(state?.duration).toBe('5')
    expect(state?.isTemplateVideoSettingsLocked).toBe(true)
    expect(state?.isTemplatePromptLocked).toBe(true)
  })
})
