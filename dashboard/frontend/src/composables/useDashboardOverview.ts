import { ref, watch } from 'vue'
import { fetchStats, fetchStatsHistory } from '../api/api'

const defaultStats = () => ({
  total_users: 0,
  inner_disciple_count: 0,
  core_disciple_count: 0,
  true_disciple_count: 0,
  total_generations: 0,
  total_credits: 0,
  total_active_credits: 0,
  total_referrals: 0,
  total_template_contributions: 0,
  total_approved_contributions: 0,
  today_users: 0,
  today_generations: 0,
  today_active_users: 0,
  today_checkins: 0,
  today_type_distribution: {},
  total_type_distribution: {},
  generation_distribution: {},
  avg_daily_distribution: {},
  credit_distribution: {},
  avg_daily_credit_distribution: {},
  credit_holding_distribution: {}
})

export function useDashboardOverview() {
  const stats = ref(defaultStats())
  const statsHistory = ref<any[]>([])
  const cumulativeStatsHistory = ref<any[]>([])
  const historyTimeRange = ref(7)
  const refreshLoading = ref(false)

  const timeRangeOptions = [
    { label: '最近 7 天', value: 7 },
    { label: '最近 2 周', value: 14 },
    { label: '最近 1 个月', value: 30 },
    { label: '最近 2 个月', value: 60 },
    { label: '最近 3 个月', value: 90 },
    { label: '最近半年', value: 180 },
    { label: '最近 1 年', value: 365 }
  ]

  const loadStats = async () => {
    try {
      stats.value = await fetchStats()
    } catch (error) {
      console.error('Error fetching stats:', error)
    }
  }

  const loadHistory = async () => {
    try {
      statsHistory.value = await fetchStatsHistory(historyTimeRange.value)
    } catch (error) {
      console.error('Error fetching history:', error)
    }
  }

  const refreshData = async () => {
    refreshLoading.value = true
    try {
      await Promise.all([loadStats(), loadHistory()])
    } finally {
      refreshLoading.value = false
    }
  }

  watch(
    [() => stats.value.total_users, statsHistory],
    ([totalUsers, history]) => {
      if (!totalUsers || history.length === 0) {
        cumulativeStatsHistory.value = []
        return
      }

      let currentTotal = totalUsers
      const reversedData = [...history].reverse()

      cumulativeStatsHistory.value = reversedData
        .map((day: any) => {
          const totalForDay = currentTotal
          currentTotal -= day.new_users
          return {
            date: day.date,
            cumulative_users: totalForDay,
            cumulative_en_users: day.cumulative_en_users,
            cumulative_zh_users: day.cumulative_zh_users,
            cumulative_pwd_users: day.cumulative_pwd_users,
            new_pwd_users: day.new_pwd_users
          }
        })
        .reverse()
    },
    { immediate: true }
  )

  return {
    stats,
    statsHistory,
    cumulativeStatsHistory,
    historyTimeRange,
    refreshLoading,
    timeRangeOptions,
    loadStats,
    loadHistory,
    refreshData
  }
}
