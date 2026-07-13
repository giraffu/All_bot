import { getTemplateTaskMeta } from '@/constants/templateTaskMeta'
import type {
  NormalizeContextOptions,
  RawApplyContextResponse,
  TemplateApplyContext,
  TemplateTaskMeta
} from '@/types/templateApply'
import { normalizeTemplateApplyContext } from '@/utils/normalizeTemplateApplyContext'

type TemplateApplyEntryBase = {
  context: TemplateApplyContext
}

export type ResolvedTemplateApplyEntry =
  | ({ status: 'invalid'; context: null; meta: null })
  | ({ status: 'unknown_task_type'; meta: null } & TemplateApplyEntryBase)
  | ({ status: 'workbench'; meta: TemplateTaskMeta } & TemplateApplyEntryBase)

export interface ResolveTemplateApplyEntryParams extends NormalizeContextOptions {
  rawContext: RawApplyContextResponse
}

export const resolveTemplateApplyEntry = (
  params: ResolveTemplateApplyEntryParams
): ResolvedTemplateApplyEntry => {
  const context = normalizeTemplateApplyContext(params.rawContext, {
    source: params.source,
    entryEntityId: params.entryEntityId
  })

  if (!context) {
    return {
      status: 'invalid',
      context: null,
      meta: null
    }
  }

  const meta = getTemplateTaskMeta(context.rawTaskType)
  if (!meta) {
    return {
      status: 'unknown_task_type',
      context,
      meta: null
    }
  }

  return {
    status: 'workbench',
    context,
    meta
  }
}
