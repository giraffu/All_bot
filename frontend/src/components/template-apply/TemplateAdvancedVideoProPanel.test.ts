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
  props: ['beforeUpload', 'title', 'filePreview', 'uploadingSlots', 'progressBySlot'],
  emits: ['remove'],
  template: '<div class="upload-stub">{{ title }}</div>'
})
const FooterStub = defineComponent({
  name: 'TemplateApplyActionFooter',
  emits: ['generate'],
  props: ['taskCost', 'isSubmitting', 'hasPendingUploads', 'hasObjectKey'],
  template: '<button class="generate" @click="$emit(\'generate\')">generate</button>'
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

const mountPanel = () => mount(TemplateAdvancedVideoProPanel, {
  props: { sessionId: 'session-h3', context },
  global: {
    plugins: [i18n],
    stubs: {
      TemplateApplyUploadSection: UploadStub,
      TemplateApplyActionFooter: FooterStub,
      TemplateApplyResultSection: true,
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
})
