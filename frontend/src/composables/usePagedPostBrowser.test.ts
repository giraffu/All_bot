import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { usePagedPostBrowser } from './usePagedPostBrowser'

interface TestPost {
  id: number
}

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })

  return { promise, resolve, reject }
}

describe('usePagedPostBrowser', () => {
  it('activates a page when the user navigates to it while prefetch is pending', async () => {
    const pageTwo = createDeferred<{ items: TestPost[]; total: number; pages: number }>()
    const fetchPageData = vi.fn((pageNumber: number) => {
      if (pageNumber === 1) {
        return Promise.resolve({
          items: [{ id: 1 }],
          total: 2,
          pages: 2,
        })
      }

      if (pageNumber === 2) {
        return pageTwo.promise
      }

      return Promise.reject(new Error(`unexpected page ${pageNumber}`))
    })
    const browser = usePagedPostBrowser<TestPost>({
      pageSize: ref(12),
      fetchPageData,
    })

    await browser.loadPosts(true)

    expect(fetchPageData).toHaveBeenCalledTimes(2)
    expect(browser.currentPage.value).toBe(1)

    const changePage = browser.goToPage(2)
    expect(browser.loading.value).toBe(true)

    pageTwo.resolve({
      items: [{ id: 2 }],
      total: 2,
      pages: 2,
    })

    await expect(changePage).resolves.toBe(true)
    expect(fetchPageData).toHaveBeenCalledTimes(2)
    expect(browser.currentPage.value).toBe(2)
    expect(browser.posts.value).toEqual([{ id: 2 }])
    expect(browser.loading.value).toBe(false)
  })
})
