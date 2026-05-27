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
      className: 'quick-action-btn--amber',
      icon: options.icons.Wallet,
      onClick: () => options.router.push('/billing'),
    },
    {
      key: 'redeem-credits',
      label: options.t('profile.redeem_credits'),
      className: 'quick-action-btn--emerald',
      icon: options.icons.Wallet,
      onClick: options.openRedeemCreditsModal,
    },
    {
      key: 'redeem-membership',
      label: options.t('profile.redeem_membership'),
      className: 'quick-action-btn--violet',
      icon: options.icons.Award,
      onClick: options.openRedeemMembershipModal,
    },
    {
      key: 'password',
      label: options.user.value?.username
        ? options.t('profile.change_password')
        : options.t('profile.set_password'),
      className: 'quick-action-btn--indigo',
      icon: options.icons.Lock,
      onClick: options.handleBindPasswordModalOpen,
    },
  ])

  return {
    quickActions,
  }
}
