import { flushPromises } from '@vue/test-utils'
import { createApp, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { installAntDesign } from './antDesign'

describe('installAntDesign', () => {
  let app: ReturnType<typeof createApp> | null = null
  let root: HTMLDivElement | null = null

  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addListener: vi.fn(),
        removeListener: vi.fn(),
      })),
    })
  })

  afterEach(() => {
    app?.unmount()
    root?.remove()
    app = null
    root = null
  })

  it('renders a native file input for upload controls', async () => {
    root = document.createElement('div')
    document.body.appendChild(root)
    app = createApp({
      template: `
        <a-upload :show-upload-list="false" accept="image/png">
          <a-button>输入示范</a-button>
        </a-upload>
      `,
    })

    installAntDesign(app)
    app.mount(root)
    await flushPromises()
    await nextTick()

    await vi.waitFor(
      () => {
        expect(root?.querySelector('input[type="file"]')).not.toBeNull()
      },
      { timeout: 5_000 }
    )
  })

  it('renders list items through the Ant Design render-item slot', async () => {
    root = document.createElement('div')
    document.body.appendChild(root)
    app = createApp({
      data: () => ({ tickets: [{ id: 42, label: '充值问题' }] }),
      template: `
        <a-list :data-source="tickets">
          <template #renderItem="{ item }">
            <a-list-item>#{{ item.id }} {{ item.label }}</a-list-item>
          </template>
        </a-list>
      `,
    })

    installAntDesign(app)
    app.mount(root)
    await flushPromises()
    await nextTick()

    await vi.waitFor(
      () => {
        expect(root?.textContent).toContain('#42 充值问题')
      },
      { timeout: 5_000 }
    )
  })
})
