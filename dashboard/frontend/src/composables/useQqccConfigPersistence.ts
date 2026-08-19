import { onMounted, ref } from 'vue'
import message from 'ant-design-vue/es/message'

import { isQqccConfigAuthExpiredError } from './useQqccConfigAuth'

interface QqccConfigPersistenceOptions<TConfig, TResponse> {
  fetchConfig: () => Promise<TResponse>
  updateConfig: (payload: TConfig) => Promise<TResponse>
  applyResponse: (payload: TResponse) => void
  buildPayload: () => TConfig
  validate: () => string | null
}

export function useQqccConfigPersistence<TConfig, TResponse>(
  options: QqccConfigPersistenceOptions<TConfig, TResponse>,
) {
  const loading = ref(false)
  const saving = ref(false)

  const loadConfig = async () => {
    loading.value = true
    try {
      options.applyResponse(await options.fetchConfig())
    } catch (error) {
      message.error(
        isQqccConfigAuthExpiredError(error)
          ? '登录已过期，请重新登录'
          : '加载懒人Bot配置失败',
      )
    } finally {
      loading.value = false
    }
  }

  const saveConfig = async () => {
    const validationError = options.validate()
    if (validationError) {
      message.error(validationError)
      return
    }
    saving.value = true
    try {
      options.applyResponse(await options.updateConfig(options.buildPayload()))
      message.success('懒人Bot配置已保存')
    } catch (error) {
      message.error(
        isQqccConfigAuthExpiredError(error)
          ? '登录已过期，请重新登录后再次保存'
          : '保存懒人Bot配置失败',
      )
    } finally {
      saving.value = false
    }
  }

  onMounted(() => void loadConfig())
  return { loading, saving, loadConfig, saveConfig }
}
