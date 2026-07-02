import { computed, type ComputedRef } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'

export interface GenerationRouteDefaults {
  taskType: string
  title: string
  cost: number
}

export interface ResolvedGenerationRouteConfig {
  taskType: ComputedRef<string>
  taskTitle: ComputedRef<string>
  taskCost: ComputedRef<number>
  routeApplyEnabled: ComputedRef<boolean>
}

const WEB_DISABLED_QUERY_TASK_TYPES = new Set<string>(['i2i_draw'])

function resolveMetaDefaults(
  route: RouteLocationNormalizedLoaded,
  fallback: GenerationRouteDefaults,
): GenerationRouteDefaults {
  const meta = (route.meta?.generation ?? {}) as Partial<GenerationRouteDefaults>
  return {
    taskType: meta.taskType || fallback.taskType,
    title: meta.title || fallback.title,
    cost: typeof meta.cost === 'number' ? meta.cost : fallback.cost,
  }
}

export function useGenerationRouteConfig(
  route: RouteLocationNormalizedLoaded,
  fallback: GenerationRouteDefaults,
): ResolvedGenerationRouteConfig {
  const metaDefaults = computed(() => resolveMetaDefaults(route, fallback))
  const queryTaskType = computed(() => (
    typeof route.query.type === 'string' ? route.query.type : ''
  ))
  const isQueryTaskDisabled = computed(() => (
    WEB_DISABLED_QUERY_TASK_TYPES.has(queryTaskType.value)
  ))

  return {
    taskType: computed(() => (
      queryTaskType.value && !isQueryTaskDisabled.value
        ? queryTaskType.value
        : metaDefaults.value.taskType
    )),
    taskTitle: computed(() => (
      typeof route.query.title === 'string' && !isQueryTaskDisabled.value
        ? route.query.title
        : metaDefaults.value.title
    )),
    taskCost: computed(() => {
      const queryCost = Number(route.query.cost)
      return Number.isFinite(queryCost) && queryCost > 0 && !isQueryTaskDisabled.value
        ? queryCost
        : metaDefaults.value.cost
    }),
    routeApplyEnabled: computed(() => route.query.apply === 'true'),
  }
}
