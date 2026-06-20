import type {
  TemplateApplyContext,
  TemplateApplyTaskType,
  TemplateTaskMeta
} from '@/types/templateApply'

const TEMPLATE_TASK_TYPE_ALIASES: Record<string, TemplateApplyTaskType> = {
  faceswap: 'face_swap'
}

const buildLegacyQuery = (
  _ctx: TemplateApplyContext,
  t: (key: string) => string,
  meta: Pick<TemplateTaskMeta, 'taskType' | 'legacyTitleKey' | 'legacyCost'>
) => ({
  apply: 'true',
  type: meta.taskType,
  title: t(meta.legacyTitleKey),
  cost: String(meta.legacyCost)
})

const createMeta = (
  meta: Omit<TemplateTaskMeta, 'buildLegacyQuery'>
): TemplateTaskMeta => ({
  ...meta,
  buildLegacyQuery: (_ctx, t) => buildLegacyQuery(_ctx, t, meta)
})

export const TEMPLATE_TASK_META_MAP: Record<TemplateApplyTaskType, TemplateTaskMeta> = {
  i2i_pro: createMeta({
    taskType: 'i2i_pro',
    supportMode: 'workbench',
    panelKind: 'imagePrompt',
    legacyRouteName: 'ImageAndPrompt',
    legacyTitleKey: 'lab.cards.i2i_pro_title',
    legacyCost: 6
  }),
  i2i_draw: createMeta({
    taskType: 'i2i_draw',
    supportMode: 'workbench',
    panelKind: 'imagePrompt',
    legacyRouteName: 'ImageAndPrompt',
    legacyTitleKey: 'lab.cards.i2i_draw_title',
    legacyCost: 3
  }),
  edit: createMeta({
    taskType: 'edit',
    supportMode: 'workbench',
    panelKind: 'imagePrompt',
    legacyRouteName: 'ImageAndPrompt',
    legacyTitleKey: 'lab.cards.custom_edit_title',
    legacyCost: 2
  }),
  img2img_lora: createMeta({
    taskType: 'img2img_lora',
    supportMode: 'workbench',
    panelKind: 'imagePrompt',
    legacyRouteName: 'ImageAndPrompt',
    legacyTitleKey: 'lab.cards.custom_edit_title',
    legacyCost: 2
  }),
  face_swap: createMeta({
    taskType: 'face_swap',
    supportMode: 'workbench',
    panelKind: 'faceSwap',
    legacyRouteName: 'FaceSwap',
    legacyTitleKey: 'lab.cards.fast_face_swap_title',
    legacyCost: 1
  }),
  face_video: createMeta({
    taskType: 'face_video',
    supportMode: 'workbench',
    panelKind: 'videoSwap',
    legacyRouteName: 'VideoSwap',
    legacyTitleKey: 'lab.cards.video_face_swap_title',
    legacyCost: 18
  }),
  custom_video: createMeta({
    taskType: 'custom_video',
    supportMode: 'workbench',
    panelKind: 'imageToVideo',
    legacyRouteName: 'SingleImageToVideo',
    legacyTitleKey: 'lab.cards.custom_video_title',
    legacyCost: 6
  }),
  video_lora: createMeta({
    taskType: 'video_lora',
    supportMode: 'workbench',
    panelKind: 'imageToVideo',
    legacyRouteName: 'SingleImageToVideo',
    legacyTitleKey: 'lab.cards.custom_video_title',
    legacyCost: 6
  }),
  wan22_video_v2: createMeta({
    taskType: 'wan22_video_v2',
    supportMode: 'workbench',
    panelKind: 'imageToVideo',
    legacyRouteName: 'Wan22VideoV2',
    legacyTitleKey: 'lab.cards.wan22_video_v2_title',
    legacyCost: 6
  }),
  ltx_video: createMeta({
    taskType: 'ltx_video',
    supportMode: 'workbench',
    panelKind: 'imageToVideo',
    legacyRouteName: 'SingleImageToVideo',
    legacyTitleKey: 'lab.cards.high_res_video_title',
    legacyCost: 10
  }),
  scail2_action_transfer: createMeta({
    taskType: 'scail2_action_transfer',
    supportMode: 'workbench',
    panelKind: 'scail2Video',
    legacyRouteName: 'CustomFeatures',
    legacyTitleKey: 'lab.cards.scail2_action_transfer_title',
    legacyCost: 40
  }),
  scail2_video_replacement: createMeta({
    taskType: 'scail2_video_replacement',
    supportMode: 'workbench',
    panelKind: 'scail2Video',
    legacyRouteName: 'CustomFeatures',
    legacyTitleKey: 'lab.cards.scail2_video_replacement_title',
    legacyCost: 40
  }),
  scail2_face_swap_v2: createMeta({
    taskType: 'scail2_face_swap_v2',
    supportMode: 'workbench',
    panelKind: 'scail2Video',
    legacyRouteName: 'CustomFeatures',
    legacyTitleKey: 'lab.cards.scail2_face_swap_v2_title',
    legacyCost: 40
  })
}

export const getCanonicalTemplateTaskType = (taskType: string): TemplateApplyTaskType | null => {
  const normalizedTaskType = TEMPLATE_TASK_TYPE_ALIASES[taskType] ?? taskType
  return TEMPLATE_TASK_META_MAP[normalizedTaskType as TemplateApplyTaskType]
    ? (normalizedTaskType as TemplateApplyTaskType)
    : null
}

export const getTemplateTaskMeta = (taskType: string): TemplateTaskMeta | null =>
  (() => {
    const canonicalTaskType = getCanonicalTemplateTaskType(taskType)
    return canonicalTaskType ? TEMPLATE_TASK_META_MAP[canonicalTaskType] : null
  })()
