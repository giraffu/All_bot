import { onMounted, ref } from 'vue'
import dayjs, { type Dayjs } from 'dayjs'

export const CUMULATIVE_DATE_KEY = 'cumulative'

type ComparableDateLoader<T> = (dateKey: string) => Promise<T>

interface UseComparableDatesOptions<T> {
  initialDates?: string[]
  maxDates?: number
  colors?: string[]
  specialColors?: Record<string, string>
  formatLabel?: (dateKey: string) => string
  loadDate: ComparableDateLoader<T>
}

export function useComparableDates<T>({
  initialDates = [dayjs().format('YYYY-MM-DD')],
  maxDates = 3,
  colors = ['#1890ff', '#52c41a', '#faad14'],
  specialColors = {},
  formatLabel,
  loadDate,
}: UseComparableDatesOptions<T>) {
  const selectedDates = ref<string[]>([...initialDates])
  const chartDataMap = ref<Record<string, T>>({})
  const loading = ref(false)

  const formatDate = (dateKey: string) => {
    if (formatLabel) {
      return formatLabel(dateKey)
    }
    return dayjs(dateKey).format('MM-DD')
  }

  const getDateColor = (dateKey: string) => {
    if (specialColors[dateKey]) {
      return specialColors[dateKey]
    }
    const index = selectedDates.value.indexOf(dateKey)
    return index !== -1 ? colors[index % colors.length] : '#ccc'
  }

  const disabledDate = (current: Dayjs) => current && current > dayjs().endOf('day')

  const fetchData = async () => {
    if (selectedDates.value.length === 0) {
      chartDataMap.value = {}
      return
    }

    loading.value = true
    try {
      const results = await Promise.all(
        selectedDates.value.map(async dateKey => ({
          dateKey,
          data: await loadDate(dateKey),
        })),
      )
      chartDataMap.value = Object.fromEntries(
        results.map(({ dateKey, data }) => [dateKey, data]),
      ) as Record<string, T>
    } catch (error) {
      console.error('Failed to fetch comparable date data:', error)
    } finally {
      loading.value = false
    }
  }

  const handleAddDate = (date: Dayjs | null) => {
    if (!date) return
    const dateKey = date.format('YYYY-MM-DD')
    const regularDateCount = selectedDates.value.filter(item => item !== CUMULATIVE_DATE_KEY).length
    if (!selectedDates.value.includes(dateKey) && regularDateCount < maxDates) {
      selectedDates.value.push(dateKey)
      void fetchData()
    }
  }

  const removeDate = (dateKey: string) => {
    selectedDates.value = selectedDates.value.filter(item => item !== dateKey)
    const nextMap = { ...chartDataMap.value }
    delete nextMap[dateKey]
    chartDataMap.value = nextMap
  }

  const toggleDateKey = (dateKey: string) => {
    if (selectedDates.value.includes(dateKey)) {
      removeDate(dateKey)
      return
    }
    selectedDates.value.push(dateKey)
    void fetchData()
  }

  onMounted(() => {
    void fetchData()
  })

  return {
    selectedDates,
    chartDataMap,
    loading,
    formatDate,
    getDateColor,
    disabledDate,
    fetchData,
    handleAddDate,
    removeDate,
    toggleDateKey,
  }
}
