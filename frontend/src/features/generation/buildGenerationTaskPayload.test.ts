import { describe, expect, it } from 'vitest'

import { buildGenerationTaskPayload } from './buildGenerationTaskPayload'

describe('buildGenerationTaskPayload', () => {
  it('fails closed for a task type missing from the generated public contract', () => {
    expect(() => buildGenerationTaskPayload({
      taskType: 'not_registered',
      images: [],
    })).toThrow('Unknown task type: not_registered')
  })

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

  it('builds scail2 payload with reference image and motion video order', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'scail2_action_transfer',
        images: ['reference-key', 'motion-video-key'],
        duration: 5,
        prompt: 'natural motion',
        negativePrompt: 'blur',
        promptTarget: 'inputs',
      }),
    ).toEqual({
      task_type: 'scail2_action_transfer',
      inputs: {
        images: ['reference-key', 'motion-video-key'],
        duration: 5,
        prompt: 'natural motion',
        negative_prompt: 'blur',
      },
      priority: 0,
      is_template: false,
    })
  })

  it('builds scail2 face swap v2 payload with the same SCAIL-2 input contract', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'scail2_face_swap_v2',
        images: ['reference-face-key', 'motion-video-key'],
        duration: 8,
        prompt: 'natural face swap',
        negativePrompt: 'blur',
        promptTarget: 'inputs',
      }),
    ).toEqual({
      task_type: 'scail2_face_swap_v2',
      inputs: {
        images: ['reference-face-key', 'motion-video-key'],
        duration: 8,
        prompt: 'natural face swap',
        negative_prompt: 'blur',
      },
      priority: 0,
      is_template: false,
    })
  })

  it('allows scail2 payloads to omit an empty prompt', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'scail2_face_swap_v2',
        images: ['reference-face-key', 'motion-video-key'],
        duration: 5,
        prompt: '   ',
        promptTarget: 'inputs',
      }),
    ).toEqual({
      task_type: 'scail2_face_swap_v2',
      inputs: {
        images: ['reference-face-key', 'motion-video-key'],
        duration: 5,
      },
      priority: 0,
      is_template: false,
    })
  })

  it('builds ltx video payload with optional lora inside inputs', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'ltx_video',
        images: ['img-1'],
        resolution: '1280x704',
        duration: 10,
        prompt: 'cinematic motion',
        promptTarget: 'inputs',
        loraName: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
        loraStrength: 0.8,
      }),
    ).toEqual({
      task_type: 'ltx_video',
      inputs: {
        images: ['img-1'],
        resolution: '1280x704',
        duration: 10,
        prompt: 'cinematic motion',
        lora_name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
        lora_strength: 0.8,
      },
      priority: 0,
      is_template: false,
    })
  })

  it('builds ltx video payload with multi lora items', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'ltx_video',
        images: ['img-1'],
        resolution: '1280x704',
        duration: 10,
        prompt: 'cinematic motion',
        promptTarget: 'inputs',
        loraItems: [
          {
            name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
            strength: 0.8,
          },
          {
            name: 'ltx2.3/SynthPussy_01_rank32.safetensors',
            strength: 0.75,
          },
        ],
      }),
    ).toEqual({
      task_type: 'ltx_video',
      inputs: {
        images: ['img-1'],
        resolution: '1280x704',
        duration: 10,
        prompt: 'cinematic motion',
        lora_items: [
          {
            name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
            strength: 0.8,
          },
          {
            name: 'ltx2.3/SynthPussy_01_rank32.safetensors',
            strength: 0.75,
          },
        ],
      },
      priority: 0,
      is_template: false,
    })
  })

  it('omits undefined extra inputs from ltx video payloads', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'ltx_video',
        images: ['img-1'],
        resolution: '1280x704',
        duration: 5,
        extraInputs: {
          ltx_mode: 'i2v',
          video: undefined,
          extract_last_frame: true,
        },
      }),
    ).toEqual({
      task_type: 'ltx_video',
      inputs: {
        images: ['img-1'],
        resolution: '1280x704',
        duration: 5,
        ltx_mode: 'i2v',
        extract_last_frame: true,
      },
      priority: 0,
      is_template: false,
    })
  })

  it('builds text to image payload without source images', () => {
    expect(
      buildGenerationTaskPayload({
        taskType: 'txt2img',
        images: [],
        prompt: '  moonlit garden  ',
        promptTarget: 'topLevel',
      }),
    ).toEqual({
      task_type: 'txt2img',
      inputs: {
        images: [],
      },
      prompt: 'moonlit garden',
      priority: 0,
      is_template: false,
    })
  })
})
