// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  authStoreMock,
  checkWebAccessMock,
  templateApplyStoreMock,
  confirmTemplateApplyCloseMock
} = vi.hoisted(() => ({
  authStoreMock: {
    token: 'token',
    sessionPurpose: 'full',
    user: {
      id: 1,
      credits: 10,
      user_group: '练气期',
      current_identity: '内门弟子'
    },
    logout: vi.fn()
  },
  checkWebAccessMock: vi.fn(() => true),
  templateApplyStoreMock: {
    visible: false,
    requestClose: vi.fn(),
    confirmCloseAndCleanup: vi.fn()
  },
  confirmTemplateApplyCloseMock: vi.fn()
}))

async function loadRouter() {
  vi.resetModules()

  vi.doMock('@/stores/auth', () => ({
    useAuthStore: () => authStoreMock,
    checkWebAccess: checkWebAccessMock
  }))

  vi.doMock('@/stores/templateApply', () => ({
    useTemplateApplyStore: () => templateApplyStoreMock,
    confirmTemplateApplyClose: confirmTemplateApplyCloseMock
  }))

  const { default: router } = await import('@/router')
  return router
}

describe('router template apply guard', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/')

    authStoreMock.token = 'token'
    authStoreMock.sessionPurpose = 'full'
    authStoreMock.user = {
      id: 1,
      credits: 10,
      user_group: '练气期',
      current_identity: '内门弟子'
    }
    authStoreMock.logout.mockReset()

    checkWebAccessMock.mockReset()
    checkWebAccessMock.mockReturnValue(true)

    templateApplyStoreMock.visible = false
    templateApplyStoreMock.requestClose.mockReset()
    templateApplyStoreMock.confirmCloseAndCleanup.mockReset()
    templateApplyStoreMock.confirmCloseAndCleanup.mockResolvedValue(undefined)

    confirmTemplateApplyCloseMock.mockReset()
  })

  it('allows bypass routes after cleanup without running close confirmation flow', async () => {
    const router = await loadRouter()

    await router.push('/profile')
    await router.isReady()

    templateApplyStoreMock.visible = true

    await router.push('/maintenance')

    expect(templateApplyStoreMock.confirmCloseAndCleanup).toHaveBeenCalledWith('route_leave')
    expect(templateApplyStoreMock.requestClose).not.toHaveBeenCalled()
    expect(confirmTemplateApplyCloseMock).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/maintenance')
  }, 15_000)

  it('blocks navigation when the user cancels the close confirmation', async () => {
    const router = await loadRouter()

    await router.push('/profile')
    await router.isReady()

    templateApplyStoreMock.visible = true
    templateApplyStoreMock.requestClose.mockResolvedValue({
      status: 'confirm_required',
      trigger: 'route_leave',
      confirmReason: 'dirty'
    })
    confirmTemplateApplyCloseMock.mockResolvedValue(false)

    await router.push('/history')

    expect(templateApplyStoreMock.requestClose).toHaveBeenCalledWith('route_leave')
    expect(confirmTemplateApplyCloseMock).toHaveBeenCalledWith('dirty')
    expect(templateApplyStoreMock.confirmCloseAndCleanup).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/profile')
  })

  it('cleans up and continues navigation when the workbench can close immediately', async () => {
    const router = await loadRouter()

    await router.push('/profile')
    await router.isReady()

    templateApplyStoreMock.visible = true
    templateApplyStoreMock.requestClose.mockResolvedValue({
      status: 'close_now'
    })

    await router.push('/history')

    expect(templateApplyStoreMock.requestClose).toHaveBeenCalledWith('route_leave')
    expect(templateApplyStoreMock.confirmCloseAndCleanup).toHaveBeenCalledWith('route_leave')
    expect(confirmTemplateApplyCloseMock).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/history')
  })

  it('redirects legacy generation routes into the unified workbench with query preserved', async () => {
    const router = await loadRouter()
    const cases = [
      ['/face-swap', 'face_swap'],
      ['/single-image', 'random_faceswap'],
      ['/image-prompt', 'i2i_pro'],
      ['/text-to-image', 'txt2img'],
      ['/single-image-video', 'custom_video'],
      ['/wan22-video-v2', 'wan22_video_v2'],
      ['/video-swap', 'scail2_face_swap_v2'],
    ] as const

    for (const [path, type] of cases) {
      await router.push({ path, query: { apply_id: '42', keep: 'yes' } })
      await router.isReady()

      expect(router.currentRoute.value.name).toBe('CustomFeatures')
      expect(router.currentRoute.value.path).toBe('/custom-features')
      expect(router.currentRoute.value.query).toMatchObject({
        apply_id: '42',
        keep: 'yes',
        type,
      })
    }
  })

  it('does not register the character library route when production LTX is disabled', async () => {
    const router = await loadRouter()

    expect(router.getRoutes().map(route => route.name)).not.toContain('Characters')
  })

  it('preserves Telegram Mini App launch hash when redirecting guests to login', async () => {
    authStoreMock.token = ''
    authStoreMock.user = null as any
    checkWebAccessMock.mockReturnValue(false)

    const router = await loadRouter()
    await router.push('/?v=release-42#tgWebAppData=encoded-init-data&tgWebAppVersion=7.0')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query).toMatchObject({ v: 'release-42' })
    expect(router.currentRoute.value.hash).toBe('#tgWebAppData=encoded-init-data&tgWebAppVersion=7.0')
  })

  it('preserves the TON billing target when redirecting a guest to login', async () => {
    authStoreMock.token = ''
    authStoreMock.user = null as any
    checkWebAccessMock.mockReturnValue(false)

    const router = await loadRouter()
    await router.push('/billing?method=ton&kind=membership#tgWebAppData=encoded-init-data')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe(
      '/billing?method=ton&kind=membership'
    )
    expect(router.currentRoute.value.hash).toBe('#tgWebAppData=encoded-init-data')
  })

  it('allows a payment-only user into billing but not protected Web pages', async () => {
    authStoreMock.token = 'payment-token'
    authStoreMock.sessionPurpose = 'payment'
    authStoreMock.user = {
      id: 2,
      credits: 6,
      user_group: '凡人',
      current_identity: '外门弟子'
    }
    checkWebAccessMock.mockReturnValue(false)

    const router = await loadRouter()
    await router.push('/billing?method=ton&kind=membership')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/billing')

    await router.push('/history')
    expect(authStoreMock.logout).toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('does not let a privileged payment session enter protected Web pages', async () => {
    authStoreMock.token = 'payment-token'
    authStoreMock.sessionPurpose = 'payment'
    authStoreMock.user = {
      id: 3,
      credits: 6,
      user_group: '练气期',
      current_identity: '核心弟子'
    }
    checkWebAccessMock.mockReturnValue(true)

    const router = await loadRouter()
    await router.push('/history')
    await router.isReady()

    expect(authStoreMock.logout).toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
