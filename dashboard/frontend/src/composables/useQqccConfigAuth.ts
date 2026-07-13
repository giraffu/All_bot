import { ref } from 'vue'

const TOKEN_KEY = 'qqcc_config_token'

const readStoredToken = () => {
  if (typeof window === 'undefined') {
    return null
  }
  return window.localStorage.getItem(TOKEN_KEY)
}

export const isQqccConfigAuthenticated = ref(!!readStoredToken())

export const getQqccConfigAuthToken = () => readStoredToken()

export const setQqccConfigAuthToken = (token: string) => {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(TOKEN_KEY, token)
  isQqccConfigAuthenticated.value = true
}

export const clearQqccConfigAuthToken = () => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(TOKEN_KEY)
  }
  isQqccConfigAuthenticated.value = false
}

export const useQqccConfigAuth = () => ({
  isAuthenticated: isQqccConfigAuthenticated,
  getAuthToken: getQqccConfigAuthToken,
  setAuthToken: setQqccConfigAuthToken,
  clearAuthToken: clearQqccConfigAuthToken,
})
