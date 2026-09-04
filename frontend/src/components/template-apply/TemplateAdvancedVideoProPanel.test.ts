// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import TemplateAdvancedVideoProPanel from '@/components/template-apply/TemplateAdvancedVideoProPanel.vue'

const mocks = vi.hoisted(() => ({
  uploadFile: vi.fn(),
  submitTask: vi.fn(),
  closeAfterSubmission: vi.fn(),
  readImageDimensions: vi.fn(),
  setDirtyState: vi.fn(),
  setPendingUploads: vi.fn(),
  registerPanelController: vi.fn(),
}))

vi.mock('@/composables/useTemplateApplyUpload', () => ({
  useTemplateApplyUpload: () => ({
    uploadFile: mocks.uploadFile,
    uploadingSlots: { value: {} },
    progressBySlot: { value: {} },
    hasPendingUploads: { value: false },
  })
}))
vi.mock('@/composables/useTaskSubmission', () => ({
  useTaskSubmission: () => ({ isSubmitting: { value: false }, submitTask: mocks.submitTask })
}))
vi.mock('@/composables/useTaskResult', () => ({
  useTaskResult: () => ({
    currentTask: { value: null }, setSubmittedTaskId: vi.fn(),
    isImageUrl: vi.fn(), downloadResult: vi.fn(),
  })
}))
vi.mock('@/stores/templateApply', () => ({
  useTemplateApplyStore: () => ({
    setDirtyState: mocks.setDirtyState,
    setPendingUploads: mocks.setPendingUploads,
    registerPanelController: mocks.registerPanelController,
    closeAfterSubmission: mocks.closeAfterSubmission,
  })
}))
vi.mock('@/utils/minimaxH3Template', async () => {
  const actual = await vi.importActual<typeof import('@/utils/minimaxH3Template')>('@/utils/minimaxH3Template')
  return { ...actual, readImageDimensions: mocks.readImageDimensions }
})

const UploadStub = defineComponent({
  name: 'TemplateApplyUploadSection',
  props: ['beforeUpload', 'title', 'filePreview', 'uploadingSlots', 'progressBySlot', 'replaceText'],
  emits: ['remove'],
  template: '<div class="upload-stub">{{ title }}</div>'
})
const FooterStub = defineComponent({
  name: 'TemplateApplyActionFooter',
  emits: ['generate'],
  props: ['taskCost', 'isSubmitting', 'hasPendingUploads', 'hasObjectKey'],
  template: '<button class="generate" @click="$emit(\'generate\')">generate</button>'
})
const AudioStub = defineComponent({
  name: 'H3ReferenceAudioUpload',
  props: ['item', 'uploading', 'beforeUpload'],
  emits: ['remove'],
  template: '<button class="audio-stub" @click="$emit(\'remove\')">audio</button>'
})
const VideoStub = defineComponent({
  name: 'H3ReferenceVideoUpload',
  props: ['item', 'uploading', 'beforeUpload'],
  emits: ['remove'],
  template: '<button class="video-stub" @click="$emit(\'remove\')">video</button>'
})

const context = {
  raw: { task_type: 'minimax_h3_flf2v', post_id: 44 },
  source: 'gallery', entryEntityId: 44, rawEntityId: 44,
  rawTaskType: 'minimax_h3_flf2v', taskType: 'minimax_h3_flf2v',
  sourcePostId: 44, prompt: 'locked motion', negativePrompt: null,
  loraName: null, loraStrength: null,
  loraItems: [{ name: 'sex_pose', strength: 0.5 }],
  inputFile: null, inputFileUrl: null, inputFiles: [], inputFileUrls: [],
  width: 640, height: 960, duration: 10, requestedDuration: 10,
  requiredImageCount: 2, billingResolution: null,
  resolutionPreset: 'standard', aspectRatio: 'source',
} as any

const mountPanel = (panelContext = context) => mount(TemplateAdvancedVideoProPanel, {
  props: { sessionId: 'session-h3', context: panelContext },
  global: {
    plugins: [i18n],
    stubs: {
      TemplateApplyUploadSection: UploadStub,
      TemplateApplyActionFooter: FooterStub,
      TemplateApplyResultSection: true,
      H3ReferenceAudioUpload: AudioStub,
      H3ReferenceVideoUpload: VideoStub,
    }
  }
})

describe('TemplateAdvancedVideoProPanel', () => {
  beforeEach(() => {
    mocks.uploadFile.mockReset()
    mocks.uploadFile
      .mockResolvedValueOnce({ uploadId: '1', objectKey: 'uploads/first.png' })
      .mockResolvedValueOnce({ uploadId: '2', objectKey: 'uploads/last.png' })
    mocks.readImageDimensions.mockReset()
    mocks.readImageDimensions
      .mockResolvedValueOnce({ width: 600, height: 900 })
      .mockResolvedValueOnce({ width: 602, height: 900 })
    mocks.submitTask.mockReset()
    mocks.submitTask.mockResolvedValue('task-derived')
    mocks.closeAfterSubmission.mockReset()
    URL.createObjectURL = vi.fn(() => 'blob:preview')
    URL.revokeObjectURL = vi.fn()
  })

  it('uploads two new frames and submits the exact locked template payload', async () => {
    const wrapper = mountPanel()
    const uploads = wrapper.findAllComponents(UploadStub)
    await uploads[0].props('beforeUpload')(new File(['a'], 'first.png', { type: 'image/png' }))
    await uploads[1].props('beforeUpload')(new File(['b'], 'last.png', { type: 'image/png' }))
    await wrapper.find('button.generate').trigger('click')
    await flushPromises()

    expect(mocks.submitTask).toHaveBeenCalledWith({
      task_type: 'minimax_h3_flf2v',
      inputs: {
        images: ['uploads/first.png', 'uploads/last.png'],
        prompt: 'locked motion',
        duration: 10,
        resolution_preset: 'standard',
        aspect_ratio: 'source',
        reference_descriptions: [],
      },
      priority: 0,
      is_template: true,
      source_post_id: 44,
    }, expect.any(String))
    expect(mocks.closeAfterSubmission).toHaveBeenCalledWith('session-h3')
  })

  it('rejects FLF2V frames whose ratios differ by more than one percent', async () => {
    mocks.readImageDimensions
      .mockReset()
      .mockResolvedValueOnce({ width: 600, height: 900 })
      .mockResolvedValueOnce({ width: 900, height: 600 })
    const wrapper = mountPanel()
    const uploads = wrapper.findAllComponents(UploadStub)
    await uploads[0].props('beforeUpload')(new File(['a'], 'first.png'))
    await uploads[1].props('beforeUpload')(new File(['b'], 'last.png'))
    await wrapper.find('button.generate').trigger('click')
    await flushPromises()

    expect(mocks.submitTask).not.toHaveBeenCalled()
  })

  it('prefills later REF2V references and lets the user replace them while choosing a new first image', async () => {
    mocks.uploadFile.mockReset()
    mocks.uploadFile
      .mockResolvedValueOnce({ uploadId: '1', objectKey: 'uploads/new-person.png' })
      .mockResolvedValueOnce({ uploadId: '2', objectKey: 'uploads/new-pose.png' })
    mocks.readImageDimensions.mockReset()
    mocks.readImageDimensions
      .mockResolvedValueOnce({ width: 900, height: 1600 })
      .mockResolvedValueOnce({ width: 1024, height: 1024 })
    const ref2vContext = {
      ...context,
      raw: { task_type: 'minimax_h3_ref2v', post_id: 45 },
      rawEntityId: 45,
      rawTaskType: 'minimax_h3_ref2v',
      taskType: 'minimax_h3_ref2v',
      sourcePostId: 45,
      requiredImageCount: 1,
      requestedDuration: 5,
      resolutionPreset: 'preview',
      aspectRatio: '16:9',
      inputFile: 'task-inputs/source/1.png',
      inputFileUrl: 'https://example.com/pose.png',
      inputFiles: ['task-inputs/source/1.png', 'task-inputs/source/2.png'],
      inputFileUrls: ['https://example.com/pose.png', 'https://example.com/style.png'],
      referenceAudioRef: { source: 'gallery_post', post_id: 45 },
      referenceAudioUrl: 'https://example.com/voice.m4a',
    } as any

    const wrapper = mountPanel(ref2vContext)
    const uploads = wrapper.findAllComponents(UploadStub)

    expect(uploads).toHaveLength(3)
    expect(uploads[0].props('filePreview')).toBeNull()
    expect(uploads[1].props('filePreview')).toBe('https://example.com/pose.png')
    expect(uploads[2].props('filePreview')).toBe('https://example.com/style.png')
    expect(uploads[1].props('replaceText')).toBeTruthy()

    await uploads[0].props('beforeUpload')(new File(['person'], 'person.png', { type: 'image/png' }))
    await uploads[1].props('beforeUpload')(new File(['pose'], 'pose.png', { type: 'image/png' }))
    await wrapper.find('button.generate').trigger('click')
    await flushPromises()

    expect(mocks.submitTask).toHaveBeenCalledWith({
      task_type: 'minimax_h3_ref2v',
      inputs: {
        images: [
          'uploads/new-person.png',
          'uploads/new-pose.png',
          'task-inputs/source/2.png',
        ],
        prompt: 'locked motion',
        duration: 5,
        resolution_preset: 'preview',
        aspect_ratio: '16:9',
        reference_descriptions: [],
        reference_audio_ref: { source: 'gallery_post', post_id: 45 },
      },
      priority: 0,
      is_template: true,
      source_post_id: 45,
    }, expect.any(String))
  })

  it('lets the user replace the contributed reference audio with a new upload', async () => {
    mocks.uploadFile.mockReset()
    mocks.uploadFile
      .mockResolvedValueOnce({ uploadId: '1', objectKey: 'uploads/new-person.png' })
      .mockResolvedValueOnce({ uploadId: '2', objectKey: 'uploads/new-voice.m4a' })
    mocks.readImageDimensions.mockReset().mockResolvedValueOnce({ width: 900, height: 1600 })
    const ref2vContext = {
      ...context,
      rawTaskType: 'minimax_h3_ref2v',
      taskType: 'minimax_h3_ref2v',
      sourcePostId: 45,
      requiredImageCount: 1,
      requestedDuration: 5,
      resolutionPreset: 'preview',
      aspectRatio: '16:9',
      inputFiles: [],
      inputFileUrls: [],
      referenceAudioRef: { source: 'gallery_post', post_id: 45 },
      referenceAudioUrl: 'https://example.com/voice.m4a',
    } as any
    const wrapper = mountPanel(ref2vContext)
    const imageUpload = wrapper.findComponent(UploadStub)
    const audioUpload = wrapper.findComponent(AudioStub)

    await imageUpload.props('beforeUpload')(new File(['person'], 'person.png', { type: 'image/png' }))
    await audioUpload.props('beforeUpload')(new File(['voice'], 'voice.m4a', { type: 'audio/mp4' }))
    await wrapper.find('button.generate').trigger('click')
    await flushPromises()

    expect(mocks.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      inputs: expect.objectContaining({
        reference_audio_ref: {
          source: 'upload',
          object_key: 'uploads/new-voice.m4a',
        },
      }),
    }), expect.any(String))
  })
})
