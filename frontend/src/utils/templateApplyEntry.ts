import { getTemplateTaskMeta } from '@/constants/templateTaskMeta'
import type {
  NormalizeContextOptions,
  RawApplyContextResponse,
  TemplateApplyContext,
  TemplateApplyPreferredMode,
  TemplateTaskMeta
} from '@/types/templateApply'
import { normalizeTemplateApplyContext } from '@/utils/normalizeTemplateApplyContext'

type TemplateApplyEntryBase = {
  context: TemplateApplyContext
}

export type ResolvedTemplateApplyEntry =
  | ({ status: 'invalid'; context: null; meta: null })
  | ({ status: 'unknown_task_type'; meta: null } & TemplateApplyEntryBase)
  | ({ status: 'workbench' | 'legacy_supported'; meta: TemplateTaskMeta } & TemplateApplyEntryBase)

export interface ResolveTemplateApplyEntryParams extends NormalizeContextOptions {
  rawContext: RawApplyContextResponse
  preferredMode?: TemplateApplyPreferredMode
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

  const prefersLegacy = params.preferredMode === 'legacy'
  const shouldUseLegacy = prefersLegacy || meta.supportMode === 'legacy' || !meta.panelKind

  return {
    status: shouldUseLegacy ? 'legacy_supported' : 'workbench',
    context,
    meta
  }
}

export const buildLegacyTemplateRoute = (
  entry: Extract<ResolvedTemplateApplyEntry, { status: 'legacy_supported' | 'workbench' }>,
  t: (key: string) => string
) => ({
  name: entry.meta.legacyRouteName,
  query: entry.meta.buildLegacyQuery(entry.context, t)
})
