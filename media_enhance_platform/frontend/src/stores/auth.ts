import { defineStore } from 'pinia'
import { api, setAccessToken } from '@/api'
import type { User } from '@/types'

interface AuthPayload {
  access_token: string
  user: User
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null,
    ready: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.user),
    isAdmin: (state) => state.user?.role === 'admin',
  },
  actions: {
    async bootstrap() {
      try {
        this.user = await api<User>('/auth/me')
      } catch {
        try {
          const data = await api<AuthPayload>('/auth/refresh', { method: 'POST' }, false)
          setAccessToken(data.access_token)
          this.user = data.user
        } catch {
          setAccessToken('')
          this.user = null
        }
      } finally {
        this.ready = true
      }
    },
    async login(email: string, password: string) {
      const data = await api<AuthPayload>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
      setAccessToken(data.access_token)
      this.user = data.user
    },
    async register(email: string, password: string) {
      const data = await api<AuthPayload>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password, accepted_terms: true }),
      })
      setAccessToken(data.access_token)
      this.user = data.user
    },
    async refreshMe() {
      this.user = await api<User>('/auth/me')
    },
    async logout() {
      await api('/auth/logout', { method: 'POST' }).catch(() => undefined)
      setAccessToken('')
      this.user = null
    },
  },
})
