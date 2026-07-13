import { flushPromises } from '@vue/test-utils'
import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { installAntDesign } from './antDesign'

describe('installAntDesign', () => {
  let app: ReturnType<typeof createApp> | null = null
  let root: HTMLDivElement | null = null

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
})
