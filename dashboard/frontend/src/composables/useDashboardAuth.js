import { ref } from 'vue'

const TOKEN_KEY = 'token'

const readStoredToken = () => {
  if (typeof window === 'undefined') {
    return null
  }
  return window.localStorage.getItem(TOKEN_KEY)
}

export const isAuthenticated = ref(!!readStoredToken())

export const getAuthToken = () => readStoredToken()

export const setAuthToken = (token) => {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(TOKEN_KEY, token)
  isAuthenticated.value = true
}

export const clearAuthToken = () => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(TOKEN_KEY)
  }
  isAuthenticated.value = false
}

export const useDashboardAuth = () => ({
  isAuthenticated,
  getAuthToken,
  setAuthToken,
  clearAuthToken,
})
