import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveTemplateVideoApplyState } from './templateVideoApplyState.ts'

test('favorite custom_video template restores high-tier settings and keeps controls locked', () => {
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

  assert.deepEqual(state, {
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

test('favorite custom_video template keeps video settings editable when metadata is incomplete', () => {
  const state = resolveTemplateVideoApplyState(
    {
      task_type: 'custom_video',
      prompt: 'cinematic action shot',
      width: null,
      duration: null
    },
    'custom_video'
  )

  assert.deepEqual(state, {
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
