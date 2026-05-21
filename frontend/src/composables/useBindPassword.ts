import { onBeforeUnmount, reactive, ref, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/api'
import type { User } from '@/stores/auth'

interface UseBindPasswordOptions {
  isMobile: Ref<boolean>
  user: Ref<User | null | undefined>
  onUserBound: (username: string) => void
  showMainButton: (text: string, handler: () => void | Promise<void>) => void
  hideMainButton: (handler?: () => void | Promise<void>) => void
  hapticFeedback: (type?: 'light' | 'medium' | 'heavy') => void
}

export function useBindPassword(options: UseBindPasswordOptions) {
  const bindFormState = reactive({
    username: '',
    password: ''
  })
  const bindingLoading = ref(false)
  const showBindModal = ref(false)

  const handleBindPassword = async () => {
    if (!bindFormState.username || !bindFormState.password) {
      message.warning('请填写道号与密咒')
      return
    }

    if (bindFormState.password.length < 6) {
      message.warning('密咒长度不能少于 6 位')
      return
    }

    bindingLoading.value = true
    try {
      await api.post('/auth/bind-password', bindFormState)
      message.success('密咒设置成功！之后可以使用该道号与密咒破界登录。')
      options.onUserBound(bindFormState.username)
      showBindModal.value = false
      bindFormState.password = ''
    } catch (error: any) {
      console.error('Bind password error:', error)

      let errorMsg = '密咒设置失败'
      const detail = error.response?.data?.detail

      if (detail) {
        if (Array.isArray(detail)) {
          errorMsg = detail
            .map((err) => {
              if (err.loc && err.loc.includes('username')) return '道号格式不正确：' + err.msg
              if (err.loc && err.loc.includes('password')) return '密咒格式不正确：' + err.msg
              return err.msg
            })
            .join('; ')
        } else if (typeof detail === 'string') {
          errorMsg = detail
        }
      }

      message.error(errorMsg)
    } finally {
      bindingLoading.value = false
    }
  }

  const handleBindPasswordModalOpen = () => {
    showBindModal.value = true
    bindFormState.username = options.user.value?.username || ''
    bindFormState.password = ''

    if (options.isMobile.value) {
      options.hapticFeedback('medium')
      options.showMainButton('确认结契', handleBindPassword)
    }
  }

  watch(showBindModal, (isOpen) => {
    if (!isOpen) {
      options.hideMainButton(handleBindPassword)
    }
  })

  onBeforeUnmount(() => {
    options.hideMainButton(handleBindPassword)
  })

  return {
    bindFormState,
    bindingLoading,
    showBindModal,
    handleBindPassword,
    handleBindPasswordModalOpen
  }
}
