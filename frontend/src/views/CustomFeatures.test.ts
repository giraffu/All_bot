// @vitest-environment jsdom

import { computed, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CustomFeatures from './CustomFeatures.vue'

const labels: Record<string, string> = {
  'lab.cards.wan22_video_v2_title': '图生视频 v2',
  'lab.cards.wan22_video_v2_desc': '图生视频 v2 描述',
  'lab.workbench.mode_kinds.video': '视频',
  'template_apply.common.result_title': '生成结果',
  'template_apply.common.download_result': '下载结果',
  'lab.workbench.result_empty_title': '结果预览区',
  'lab.workbench.result_empty_desc': '结果描述',
  'lab.workbench.wan22_extend_generation': '扩展生成',
  'lab.workbench.wan22_regenerate_generation': '重新生成',
  'lab.workbench.wan22_stitch_chain': '拼接',
  'lab.workbench.continue_generation': '继续生成',
}

let workbench: any

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => labels[key] ?? key,
  }),
}))

vi.mock('@/composables/useLabWorkbench', () => ({
  useLabWorkbench: () => workbench,
}))

const baseMode = {
  id: 'wan22_video_v2',
  taskType: 'wan22_video_v2',
  titleKey: 'lab.cards.wan22_video_v2_title',
  descriptionKey: 'lab.cards.wan22_video_v2_desc',
  kindKey: 'lab.workbench.mode_kinds.video',
  submitLabelKey: 'lab.workbench.submit_video',
  supportsUpload: true,
  supportsAdvancedOptions: true,
}

const createWorkbench = (options?: { canStitch?: boolean }) => ({
  unifiedModes: [],
  legacyModes: [],
  currentMode: computed(() => baseMode),
  currentModeId: ref('wan22_video_v2'),
  prompt: ref(''),
  displayedReferences: ref([]),
  isSubmitting: ref(false),
  currentTask: ref({
    id: 'task-1',
    type: 'wan22_video_v2',
    title: '图生视频 v2',
    status: 'success',
    resultUrl: 'https://cdn/result.mp4',
    extraOutputs: {
      last_frame: {
        path: 'tail.png',
        media_type: 'image',
        url: 'https://cdn/tail.png',
      },
    },
    resultMeta: options?.canStitch ? { wan22_prev_task_id: 'task-0' } : {},
  }),
  isImageUrl: vi.fn(() => false),
  downloadResult: vi.fn(),
  selectMode: vi.fn(),
  openLegacyMode: vi.fn(),
  beforeUpload: vi.fn(),
  beforeUploadSlot: vi.fn(),
  handleRemoveReference: vi.fn(),
  handleRemoveUploadSlot: vi.fn(),
  handleSubmit: vi.fn(),
  resetAfterResult: vi.fn(),
  cost: ref(8),
  costHint: ref(''),
  canSubmit: ref(true),
  hasAdvancedOptions: ref(true),
  assetUploadSlots: ref([]),
  canUploadReference: ref(true),
  referenceTitle: ref('起始帧 / 终止帧'),
  uploadButtonLabel: ref('添加起始帧'),
  editLoraOptions: [],
  selectedEditLora: ref(''),
  customEditLoraStrength: ref(1),
  videoLoraOptions: [],
  selectedVideoLora: ref(''),
  ltxLoraOptions: [],
  selectedLtxLoraNames: ref([]),
  ltxLoraItems: ref([]),
  syncLtxLoraItems: vi.fn(),
  removeLtxLoraItem: vi.fn(),
  updateLtxLoraStrength: vi.fn(),
  negativePrompt: ref(''),
  wan22ResolutionOptions: [],
  wan22ResolutionPreset: ref('preview'),
  videoResolutionOptions: [],
  resolution: ref('512'),
  videoDurationOptions: [],
  duration: ref('5'),
  templateNotice: ref(''),
  templateWarning: ref(''),
  composerNotice: ref(''),
  composerWarning: ref(''),
  isTemplatePromptLocked: ref(false),
  isTemplateEditSettingsLocked: ref(false),
  isTemplateVideoSettingsLocked: ref(false),
  currentTaskIsWan22VideoV2: ref(true),
  wan22CurrentTaskCanExtend: ref(true),
  wan22CurrentTaskCanStitch: ref(Boolean(options?.canStitch)),
  wan22ChainLoading: ref(false),
  wan22ChainStitching: ref(false),
  openWan22CurrentTaskEditor: vi.fn(),
  stitchCurrentWan22Chain: vi.fn(),
})

const mountView = () => mount(CustomFeatures, {
  global: {
    mocks: {
      $t: (key: string) => labels[key] ?? key,
    },
    stubs: {
      LabPromptComposer: { template: '<div class="composer-stub"></div>' },
      LabAdvancedOptionsPanel: true,
      LabLegacyModeGrid: true,
      LabModeRail: true,
      TaskResultPreviewPanel: {
        props: ['currentTask'],
        template: '<div class="result-stub"><slot name="success-actions" :task="currentTask" /></div>',
      },
      'a-button': {
        props: ['disabled', 'loading'],
        emits: ['click'],
        template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
      },
    },
  },
})

describe('CustomFeatures Wan22 result actions', () => {
  beforeEach(() => {
    workbench = createWorkbench()
  })

  it('shows extend and regenerate without the generic continue action', () => {
    const wrapper = mountView()

    expect(wrapper.text()).toContain('下载结果')
    expect(wrapper.text()).toContain('扩展生成')
    expect(wrapper.text()).toContain('重新生成')
    expect(wrapper.text()).not.toContain('继续生成')
    expect(wrapper.text()).not.toContain('拼接')
  })

  it('shows stitch only for chained segments', () => {
    workbench = createWorkbench({ canStitch: true })
    const wrapper = mountView()

    expect(wrapper.text()).toContain('拼接')
  })
})
