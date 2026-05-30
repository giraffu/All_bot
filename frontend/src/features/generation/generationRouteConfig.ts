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

  return {
    taskType: computed(() => (route.query.type as string) || metaDefaults.value.taskType),
    taskTitle: computed(() => (route.query.title as string) || metaDefaults.value.title),
    taskCost: computed(() => {
      const queryCost = Number(route.query.cost)
      return Number.isFinite(queryCost) && queryCost > 0
        ? queryCost
        : metaDefaults.value.cost
    }),
    routeApplyEnabled: computed(() => route.query.apply === 'true'),
  }
}
