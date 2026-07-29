import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/api'
import i18n from '@/i18n'
import type { User } from '@/types'

export const useAuthStore = defineStore('avatar-auth', () => {
  const token = ref<string | null>(localStorage.getItem('avatar_miniapp_token'))
  const user = ref<User | null>(
    JSON.parse(localStorage.getItem('avatar_miniapp_user') || 'null') as User | null,
  )

  async function login(username: string, password: string) {
    const { data } = await api.post<{ access_token: string; user: User }>('/auth/login', {
      username,
      password,
    })
    token.value = data.access_token
    user.value = data.user
    localStorage.setItem('avatar_miniapp_token', data.access_token)
    localStorage.setItem('avatar_miniapp_user', JSON.stringify(data.user))
    if (data.user.language_code === 'en' || data.user.language_code === 'zh') {
      i18n.global.locale.value = data.user.language_code
      localStorage.setItem('avatar_miniapp_locale', data.user.language_code)
    }
  }

  async function restore() {
    if (!token.value) return false
    try {
      const { data } = await api.get<User>('/users/me')
      user.value = data
      localStorage.setItem('avatar_miniapp_user', JSON.stringify(data))
      return true
    } catch {
      logout()
      return false
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('avatar_miniapp_token')
    localStorage.removeItem('avatar_miniapp_user')
  }

  return { token, user, login, restore, logout }
})
