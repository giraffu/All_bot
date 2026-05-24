import { computed, type ComputedRef } from 'vue'
import type { Component } from 'vue'

type Translator = (key: string) => string

type ProfileUser = {
  telegram_id?: number | string | null
  id?: number | string | null
  generation_count?: number | null
  checkin_count?: number | null
  priority?: number | null
  invitation_count?: number | null
  invitation_recharge?: {
    total_ton?: number | null
    total_rmb?: number | null
    total_stars?: number | null
  } | null
} | null

type UseProfileMetricsOptions = {
  user: ComputedRef<ProfileUser>
  t: Translator
  totalCommissionUsdt: ComputedRef<string | number>
  spentCommissionUsdt: ComputedRef<string | number>
  availableCommissionUsdt: ComputedRef<string | number>
  icons: {
    User: Component
    Zap: Component
    CalendarCheck: Component
    Award: Component
    Activity: Component
    Wallet: Component
  }
}

export function useProfileMetrics(options: UseProfileMetricsOptions) {
  const statsCards = computed(() => [
    {
      key: 'system-id',
      title: options.t('profile.system_id'),
      value: options.user.value?.telegram_id || options.user.value?.id || '---',
      icon: options.icons.User,
      accent: 'cyan' as const,
    },
    {
      key: 'generations',
      title: options.t('profile.generations'),
      value: `${options.user.value?.generation_count || 0} ${options.t('profile.times_unit')}`,
      icon: options.icons.Zap,
      accent: 'indigo' as const,
    },
    {
      key: 'checkins',
      title: options.t('profile.checkins'),
      value: `${options.user.value?.checkin_count || 0} ${options.t('profile.days_unit')}`,
      icon: options.icons.CalendarCheck,
      accent: 'emerald' as const,
    },
    {
      key: 'priority',
      title: options.t('profile.priority'),
      value: options.user.value?.priority || 0,
      icon: options.icons.Award,
      accent: 'amber' as const,
    },
  ])

  const promotionCards = computed(() => [
    {
      key: 'invitation-count',
      title: options.t('profile.invitations'),
      value: `${options.user.value?.invitation_count || 0} ${options.t('profile.people_unit')}`,
      icon: options.icons.User,
      accent: 'cyan' as const,
    },
    {
      key: 'invited-ton',
      title: options.t('profile.invited_recharge_ton'),
      value: `${options.user.value?.invitation_recharge?.total_ton || 0} TON`,
      icon: options.icons.Activity,
      accent: 'indigo' as const,
    },
    {
      key: 'invited-rmb',
      title: options.t('profile.invited_recharge_cny'),
      value: `¥ ${options.user.value?.invitation_recharge?.total_rmb || 0}`,
      icon: options.icons.Wallet,
      accent: 'emerald' as const,
    },
    {
      key: 'invited-stars',
      title: options.t('profile.invited_recharge_stars'),
      value: `${options.user.value?.invitation_recharge?.total_stars || 0} ⭐`,
      icon: options.icons.Zap,
      accent: 'amber' as const,
    },
    {
      key: 'commission-total',
      title: '历史累计返佣',
      value: `$ ${options.totalCommissionUsdt.value} USDT`,
      iconText: '$',
      accent: 'rose' as const,
      colSpanClass: 'col-span-2 sm:col-span-2 lg:col-span-1',
      valueClass: 'text-lg md:text-xl font-bold text-rose-100 drop-shadow-md',
    },
    {
      key: 'commission-spent',
      title: '已兑换返佣',
      value: `$ ${options.spentCommissionUsdt.value} USDT`,
      icon: options.icons.Wallet,
      accent: 'amber' as const,
      colSpanClass: 'col-span-2 sm:col-span-1 lg:col-span-1',
    },
    {
      key: 'commission-available',
      title: '当前可兑换返佣',
      value: `$ ${options.availableCommissionUsdt.value} USDT`,
      icon: options.icons.Wallet,
      accent: 'emerald' as const,
      colSpanClass: 'col-span-2 sm:col-span-1 lg:col-span-1',
    },
  ])

  return {
    statsCards,
    promotionCards,
  }
}
