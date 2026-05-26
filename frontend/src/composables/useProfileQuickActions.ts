import { computed, type ComputedRef } from 'vue'

type ProfileUser = {
  username?: string | null
}

type Translate = (key: string) => string

type RouterLike = {
  push: (...args: any[]) => unknown
}

export function useProfileQuickActions(options: {
  user: ComputedRef<ProfileUser | null | undefined>
  t: Translate
  router: RouterLike
  openRedeemCreditsModal: () => void
  openRedeemMembershipModal: () => void
  handleBindPasswordModalOpen: () => void
  icons: {
    Wallet: unknown
    Award: unknown
    Lock: unknown
  }
}) {
  const quickActions = computed(() => [
    {
      key: 'billing',
      label: options.t('menu.recharge'),
      className:
        'bg-slate-500 text-amber-300 border-amber-500/30 hover:text-amber-200 hover:border-amber-400 shadow-md',
      icon: options.icons.Wallet,
      onClick: () => options.router.push('/billing'),
    },
    {
      key: 'redeem-credits',
      label: options.t('profile.redeem_credits'),
      className:
        'bg-slate-500 text-emerald-300 border-emerald-500/30 hover:text-emerald-200 hover:border-emerald-400 shadow-md',
      icon: options.icons.Wallet,
      onClick: options.openRedeemCreditsModal,
    },
    {
      key: 'redeem-membership',
      label: options.t('profile.redeem_membership'),
      className:
        'bg-slate-500 text-violet-300 border-violet-500/30 hover:text-violet-200 hover:border-violet-400 shadow-md',
      icon: options.icons.Award,
      onClick: options.openRedeemMembershipModal,
    },
    {
      key: 'password',
      label: options.user.value?.username
        ? options.t('profile.change_password')
        : options.t('profile.set_password'),
      className:
        'bg-slate-500 text-indigo-300 border-indigo-500/30 hover:text-indigo-200 hover:border-indigo-400 shadow-md',
      icon: options.icons.Lock,
      onClick: options.handleBindPasswordModalOpen,
    },
  ])

  return {
    quickActions,
  }
}
