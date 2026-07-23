type ReleaseUpdateMonitorOptions = {
  currentEntryUrl: string
  origin: string
  fetchHtml: () => Promise<string>
  reload: () => void
  intervalMs?: number
}

type ReleaseUpdateMonitor = {
  check: () => Promise<void>
  stop: () => void
}

const dashboardEntryUrl = (html: string, origin: string): string | null => {
  const document = new DOMParser().parseFromString(html, 'text/html')
  const entry = Array.from(document.querySelectorAll<HTMLScriptElement>('script[type="module"][src]'))
    .map((script) => script.getAttribute('src'))
    .find((source) => source && /(?:^|\/)main-[^/]+\.js(?:\?.*)?$/.test(source))

  return entry ? new URL(entry, origin).href : null
}

export const hasFrontendUpdate = (
  currentEntryUrl: string,
  html: string,
  origin: string,
): boolean => {
  const latestEntryUrl = dashboardEntryUrl(html, origin)
  return latestEntryUrl !== null && latestEntryUrl !== currentEntryUrl
}

export const startFrontendUpdateMonitor = ({
  currentEntryUrl,
  origin,
  fetchHtml,
  reload,
  intervalMs = 60_000,
}: ReleaseUpdateMonitorOptions): ReleaseUpdateMonitor => {
  let stopped = false
  let reloading = false

  const check = async () => {
    if (stopped || reloading) return
    try {
      const html = await fetchHtml()
      if (hasFrontendUpdate(currentEntryUrl, html, origin)) {
        reloading = true
        reload()
      }
    } catch {
      // A transient control-plane or network failure must not interrupt the admin UI.
    }
  }
  const checkWhenVisible = () => {
    if (document.visibilityState === 'visible') void check()
  }
  const timer = window.setInterval(checkWhenVisible, intervalMs)
  window.addEventListener('focus', checkWhenVisible)
  document.addEventListener('visibilitychange', checkWhenVisible)

  return {
    check,
    stop: () => {
      stopped = true
      window.clearInterval(timer)
      window.removeEventListener('focus', checkWhenVisible)
      document.removeEventListener('visibilitychange', checkWhenVisible)
    },
  }
}
