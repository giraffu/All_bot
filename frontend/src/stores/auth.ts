import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

export interface InvitationRechargeStats {
  recharged_invitees_count: number
  total_recharge_count: number
  total_ton: number
  total_rmb: number
  total_stars: number
  commission_usdt: number
}

export interface User {
  id: number
  telegram_id: number | null
  username: string | null
  full_name: string | null
  credits: number
  user_group: string
  current_identity: string
  identity_expire_at?: string | null
  priority?: number
  generation_count?: number
  checkin_count?: number
  invitation_count?: number
  invitation_recharge?: InvitationRechargeStats | null
}

export function checkWebAccess(user: User | null): boolean {
  if (!user) return false
  const allowedGroups = ['练气期', '筑基期', '金丹期', '元婴期', '化神期', '炼虚期', '合体期', '大乘期', '渡劫期']
  const allowedIdentities = ['内门弟子', '核心弟子', '真传弟子']
  return allowedGroups.includes(user.user_group) || allowedIdentities.includes(user.current_identity)
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token') || null)
  const user = ref<User | null>(JSON.parse(localStorage.getItem('user') || 'null'))

  function setAuth(newToken: string, newUser: User) {
    token.value = newToken
    user.value = newUser
    localStorage.setItem('token', newToken)
    localStorage.setItem('user', JSON.stringify(newUser))
  }

  function updateBalance(newCredits: number) {
    if (user.value) {
      user.value.credits = newCredits
      localStorage.setItem('user', JSON.stringify(user.value))
    }
  }
  
  async function fetchUser() {
    try {
      const response = await api.get('/users/me')
      if (response.data) {
        user.value = response.data
        localStorage.setItem('user', JSON.stringify(user.value))
      }
    } catch (e) {
      console.error('Failed to fetch user data', e)
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { token, user, setAuth, updateBalance, fetchUser, logout }
})
