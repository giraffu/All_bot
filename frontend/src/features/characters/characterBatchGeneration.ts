import type {
  CharacterBatchCapacity,
  CharacterViewType,
} from '@/api/characters'

type ViewStatus = {
  type: CharacterViewType
  status: 'pending' | 'ready' | 'failed'
}

type BatchProgress = {
  submitted: number
  remaining: number
}

type BatchOptions = {
  viewTypes: CharacterViewType[]
  getCapacity: () => Promise<CharacterBatchCapacity>
  submit: (viewType: CharacterViewType) => Promise<unknown>
  waitForCapacity: () => Promise<void>
  isActive: () => boolean
  onProgress?: (progress: BatchProgress) => void
  shouldRetry?: (error: unknown) => boolean
}

export function getMissingCharacterViewTypes(
  allViewTypes: CharacterViewType[],
  views: ViewStatus[],
): CharacterViewType[] {
  const statuses = new Map(views.map(view => [view.type, view.status]))
  return allViewTypes.filter((viewType) => {
    const status = statuses.get(viewType)
    return status !== 'ready' && status !== 'pending'
  })
}

export async function runCharacterViewBatch(options: BatchOptions): Promise<{
  submitted: number
  failed: number
  cancelled: boolean
}> {
  const queue = [...options.viewTypes]
  let submitted = 0
  let failed = 0

  while (queue.length > 0 && options.isActive()) {
    const capacity = await options.getCapacity()
    const submissionCount = Math.min(
      Math.max(capacity.available, 0),
      queue.length,
    )
    if (submissionCount === 0) {
      await options.waitForCapacity()
      continue
    }

    const current = queue.splice(0, submissionCount)
    const results = await Promise.allSettled(
      current.map(viewType => options.submit(viewType)),
    )
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        submitted += 1
        return
      }
      if (options.shouldRetry?.(result.reason)) {
        queue.push(current[index])
        return
      }
      failed += 1
    })
    options.onProgress?.({ submitted, remaining: queue.length })

    if (queue.length > 0 && options.isActive()) {
      await options.waitForCapacity()
    }
  }

  return {
    submitted,
    failed,
    cancelled: !options.isActive(),
  }
}
