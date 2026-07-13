import { mount, flushPromises } from '@vue/test-utils'
import dayjs from 'dayjs'
import { describe, expect, it, vi } from 'vitest'

import { useComparableDates } from './useComparableDates'

describe('useComparableDates', () => {
  it('loads selected dates and updates the data map when dates change', async () => {
    const loadDate = vi.fn(async (dateKey: string) => ({ value: dateKey.length }))
    let state: ReturnType<typeof useComparableDates<{ value: number }>> | undefined

    mount({
      setup() {
        state = useComparableDates({
          initialDates: ['2026-07-06'],
          loadDate,
        })
        return () => null
      },
    })

    await flushPromises()

    expect(loadDate).toHaveBeenCalledWith('2026-07-06')
    expect(state?.chartDataMap.value['2026-07-06']).toEqual({ value: 10 })

    state?.handleAddDate(dayjs('2026-07-05'))
    await flushPromises()

    expect(state?.selectedDates.value).toEqual(['2026-07-06', '2026-07-05'])
    expect(state?.chartDataMap.value['2026-07-05']).toEqual({ value: 10 })

    state?.removeDate('2026-07-06')

    expect(state?.selectedDates.value).toEqual(['2026-07-05'])
    expect(state?.chartDataMap.value['2026-07-06']).toBeUndefined()
  })
})
