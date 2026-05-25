import { describe, expect, it } from 'vitest'

import { buildGenerationTaskPayload } from './buildGenerationTaskPayload'

describe('buildGenerationTaskPayload', () => {
  it('builds single image payload with template metadata', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'random_faceswap',
        images: ['img-1'],
        isTemplate: true,
        sourcePostId: 66,
      }),
    ).toEqual({
      task_type: 'random_faceswap',
      inputs: {
        images: ['img-1'],
      },
      priority: 0,
      is_template: true,
      source_post_id: 66,
    })
  })

  it('builds image prompt payload with top-level prompt and lora normalization', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'edit',
        images: ['img-1', 'img-2'],
        prompt: '  enhance details  ',
        promptTarget: 'topLevel',
        loraName: 'qwen/YARN_1.0.safetensors',
        loraStrength: 0.3,
        normalizeEditLoraTask: true,
      }),
    ).toEqual({
      task_type: 'img2img_lora',
      inputs: {
        images: ['img-1', 'img-2'],
        lora_name: 'qwen/YARN_1.0.safetensors',
        lora_strength: 0.3,
      },
      prompt: 'enhance details',
      priority: 0,
      is_template: false,
    })
  })

  it('builds image to video payload with prompt inside inputs', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'custom_video',
        images: ['img-1'],
        resolution: 720,
        duration: 8,
        prompt: 'run forward',
        promptTarget: 'inputs',
        loraName: 'BreastGrow',
      }),
    ).toEqual({
      task_type: 'custom_video',
      inputs: {
        images: ['img-1'],
        resolution: 720,
        duration: 8,
        prompt: 'run forward',
        lora_name: 'BreastGrow',
      },
      priority: 0,
      is_template: false,
    })
  })
})
