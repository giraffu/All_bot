import { ref } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/api'

interface UseDailyCheckinOptions {
  refreshUser: () => Promise<void>
}

export function useDailyCheckin(options: UseDailyCheckinOptions) {
  const checkinLoading = ref(false)

  const handleCheckin = async () => {
    checkinLoading.value = true
    try {
      const response = await api.post('/users/checkin')
      const data = response.data
      if (data.success) {
        message.success(`签到成功！获得 ${data.reward} 灵石`)
        await options.refreshUser()
      } else if (data.error_msg) {
        message.warning(data.error_msg)
      } else {
        message.warning('今日已领取灵石，请明天再来吧！')
      }
    } catch (error) {
      console.error('Checkin error:', error)
      message.error('签到失败，请稍后重试')
    } finally {
      checkinLoading.value = false
    }
  }

  return {
    checkinLoading,
    handleCheckin
  }
}
