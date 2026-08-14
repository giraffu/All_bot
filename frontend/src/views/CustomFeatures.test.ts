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
  'lab.workbench.ltx_extend_generation': '扩展生成',
  'lab.workbench.ltx_stitch_chain': '拼接',
  'lab.workbench.continue_generation': '继续生成',
  'lab.cards.minimax_h3_title': '高级图生视频pro',
  'lab.cards.minimax_h3_desc': '高级视频描述',
  'lab.workbench.minimax_h3_fixed_stack': '固定使用 RedMix 8-step 整合模型，无需选择附加模型。',
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

vi.mock('@/stores/characters', () => ({
  useCharactersStore: () => ({
    readyItems: [],
    loading: false,
    refresh: vi.fn(),
  }),
}))

vi.mock('@/composables/useUpload', () => ({
  useUpload: () => ({
    uploading: ref(false),
    uploadFile: vi.fn(),
  }),
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
  currentMode: computed(() => baseMode),
  currentModeId: ref('wan22_video_v2'),
  prompt: ref(''),
  audioPrompt: ref(''),
  selectedCharacterId: ref(null),
  selectedCharacterIds: ref([]),
  sulphurStrength: ref(0.5),
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
  promptPlaceholder: ref('描述你想生成的视频效果'),
  showStructuredPromptInput: ref(false),
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
  currentTaskIsLtxVideo: ref(false),
  ltxCurrentTaskCanExtend: ref(false),
  ltxCurrentTaskCanStitch: ref(false),
  wan22ChainLoading: ref(false),
  wan22ChainStitching: ref(false),
  ltxChainStitching: ref(false),
  openWan22CurrentTaskEditor: vi.fn(),
  openLtxCurrentTaskEditor: vi.fn(),
  stitchCurrentWan22Chain: vi.fn(),
  stitchCurrentLtxChain: vi.fn(),
})

const createLtxWorkbench = (options?: { hasLastFrame?: boolean; canStitch?: boolean }) => ({
  ...createWorkbench(),
  currentMode: computed(() => ({
    ...baseMode,
    id: 'ltx_video',
    taskType: 'ltx_video',
    titleKey: 'lab.cards.high_res_video_title',
    descriptionKey: 'lab.cards.high_res_video_desc',
  })),
  currentModeId: ref('ltx_video'),
  currentTask: ref({
    id: 'ltx-task-1',
    type: 'ltx_video',
    title: '高级图生视频',
    status: 'success',
    resultUrl: 'https://cdn/ltx-result.mp4',
    extraOutputs: options?.hasLastFrame === false ? {} : {
      last_frame: {
        path: 'history/ltx-task-1/last_frame.png',
        media_type: 'image',
        url: 'https://cdn/ltx-tail.png',
      },
    },
    resultMeta: options?.canStitch ? { ltx_prev_task_id: 'ltx-task-0' } : {},
  }),
  currentTaskIsWan22VideoV2: ref(false),
  wan22CurrentTaskCanExtend: ref(false),
  wan22CurrentTaskCanStitch: ref(false),
  currentTaskIsLtxVideo: ref(true),
  ltxCurrentTaskCanExtend: ref(options?.hasLastFrame !== false),
  ltxCurrentTaskCanStitch: ref(Boolean(options?.canStitch)),
  ltxChainStitching: ref(false),
  openWan22CurrentTaskEditor: vi.fn(),
  openLtxCurrentTaskEditor: vi.fn(),
  stitchCurrentLtxChain: vi.fn(),
})

const createMinimaxWorkbench = () => ({
  ...createWorkbench(),
  currentMode: computed(() => ({
    ...baseMode,
    id: 'minimax_h3',
    taskType: 'minimax_h3_t2v',
    titleKey: 'lab.cards.minimax_h3_title',
    descriptionKey: 'lab.cards.minimax_h3_desc',
  })),
  currentModeId: ref('minimax_h3'),
  currentTask: ref(null),
  displayedReferences: ref([]),
  duration: ref('5'),
  minimaxH3Mode: ref('t2v'),
  minimaxH3ResolutionPreset: ref('preview'),
  minimaxH3AspectRatio: ref('16:9'),
  minimaxH3ReferenceDescriptions: ref(['', '', '', '']),
})

const mountView = () => mount(CustomFeatures, {
  global: {
    mocks: {
      $t: (key: string) => labels[key] ?? key,
    },
    stubs: {
      LabPromptComposer: {
        methods: { close() {} },
        template: '<div class="composer-stub"><slot name="before-prompt" /><slot name="advanced-panel" :close="close" /></div>',
      },
      LabAdvancedOptionsPanel: true,
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
      'a-select': {
        template: '<div><slot /></div>',
      },
      'a-slider': true,
      'a-input-number': true,
    },
  },
})

describe('CustomFeatures Wan22 result actions', () => {
  beforeEach(() => {
    workbench = createWorkbench()
  })

  it('shows extend and regenerate without the generic continue action', () => {
    const wrapper = mountView()
    const actions = wrapper.find('.lab-workbench__result-actions')

    expect(wrapper.text()).toContain('下载结果')
    expect(wrapper.text()).toContain('扩展生成')
    expect(wrapper.text()).toContain('重新生成')
    expect(wrapper.text()).not.toContain('继续生成')
    expect(wrapper.text()).not.toContain('拼接')
    expect(actions.exists()).toBe(true)
    expect(actions.classes()).toContain('flex')
    expect(actions.classes()).not.toContain('grid-cols-1')
  })

  it('shows stitch only for chained segments', () => {
    workbench = createWorkbench({ canStitch: true })
    const wrapper = mountView()

    expect(wrapper.text()).toContain('拼接')
  })
})

describe('CustomFeatures LTX result actions', () => {
  beforeEach(() => {
    workbench = createLtxWorkbench()
  })

  it('shows direct extend action for the current LTX result', async () => {
    const wrapper = mountView()

    expect(wrapper.text()).toContain('下载结果')
    expect(wrapper.text()).toContain('扩展生成')
    expect(wrapper.text()).toContain('继续生成')
    expect(wrapper.text()).not.toContain('拼接')

    const buttons = wrapper.findAll('button')
    const extendButton = buttons.find(button => button.text().includes('扩展生成'))
    expect(extendButton?.attributes('disabled')).toBeUndefined()

    await extendButton?.trigger('click')
    expect(workbench.openLtxCurrentTaskEditor).toHaveBeenCalledTimes(1)
  })

  it('shows stitch for LTX extension segments', async () => {
    workbench = createLtxWorkbench({ canStitch: true })
    const wrapper = mountView()

    expect(wrapper.text()).toContain('拼接')

    const stitchButton = wrapper.findAll('button')
      .find(button => button.text().includes('拼接'))
    await stitchButton?.trigger('click')

    expect(workbench.stitchCurrentLtxChain).toHaveBeenCalledTimes(1)
  })

  it('disables LTX extend when the current result has no tail frame', () => {
    workbench = createLtxWorkbench({ hasLastFrame: false })
    const wrapper = mountView()

    const buttons = wrapper.findAll('button')
    const extendButton = buttons.find(button => button.text().includes('扩展生成'))
    expect(extendButton?.attributes('disabled')).toBeDefined()
  })
})

describe('CustomFeatures MiniMax H3 fixed stack', () => {
  it('shows the fixed RedMix stack and no add-on controls', () => {
    workbench = createMinimaxWorkbench()
    const wrapper = mountView()

    expect(wrapper.text()).toContain('固定使用 RedMix 8-step 整合模型')
    expect(wrapper.text()).not.toContain('全选 LoRA')
    expect(wrapper.findAllComponents({ name: 'ASlider' })).toHaveLength(0)
  })
})

describe('CustomFeatures LTX character settings', () => {
  it('locks the Ingredients resolution without locking supported durations', () => {
    workbench = {
      ...createWorkbench(),
      currentMode: computed(() => ({
        ...baseMode,
        id: 'ltx_t2v',
        taskType: 'ltx_t2v',
      })),
      currentModeId: ref('ltx_t2v'),
      selectedCharacterId: ref('character-1'),
      selectedCharacterIds: ref(['character-1']),
      videoResolutionOptions: [{ value: '768x448', label: '768x448' }],
      resolution: ref('768x448'),
      videoDurationOptions: [
        { value: '5', label: '5 秒' },
        { value: '10', label: '10 秒' },
        { value: '15', label: '15 秒' },
        { value: '20', label: '20 秒' },
      ],
    }

    const wrapper = mountView()
    const optionsPanel = wrapper.findComponent({ name: 'LabAdvancedOptionsPanel' })

    expect(optionsPanel.props('isTemplateVideoSettingsLocked')).toBe(false)
    expect(optionsPanel.props('isVideoResolutionLocked')).toBe(true)
  })
})
