import { ref } from 'vue'

const OWNER_TOKEN_KEY = 'qqcc_private_bot_owner_token'

const readOwnerToken = () => {
  if (typeof window === 'undefined') return null
  return window.sessionStorage.getItem(OWNER_TOKEN_KEY)
}

export const isPrivateBotOwnerAuthenticated = ref(Boolean(readOwnerToken()))

export const getPrivateBotOwnerToken = () => readOwnerToken()

export const setPrivateBotOwnerToken = (token: string) => {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(OWNER_TOKEN_KEY, token)
  isPrivateBotOwnerAuthenticated.value = true
}

export const clearPrivateBotOwnerToken = () => {
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(OWNER_TOKEN_KEY)
  }
  isPrivateBotOwnerAuthenticated.value = false
}

export const usePrivateBotOwnerAuth = () => ({
  isAuthenticated: isPrivateBotOwnerAuthenticated,
  getAuthToken: getPrivateBotOwnerToken,
  setAuthToken: setPrivateBotOwnerToken,
  clearAuthToken: clearPrivateBotOwnerToken,
})
