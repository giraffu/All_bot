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
    authStoreMock.user = {
      id: 1,
      credits: 10,
      user_group: '练气期',
      current_identity: '内门弟子'
    }

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
  })

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
})
