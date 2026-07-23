const API_BASE = '/api'

let accessToken = localStorage.getItem('clarity_access_token') || ''

export function setAccessToken(token: string) {
  accessToken = token
  if (token) localStorage.setItem('clarity_access_token', token)
  else localStorage.removeItem('clarity_access_token')
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (response.status === 401 && retry && !path.startsWith('/auth/')) {
    const refreshed = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
    if (refreshed.ok) {
      const payload = await refreshed.json()
      setAccessToken(payload.access_token)
      return api<T>(path, init, false)
    }
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'request_failed' }))
    throw new Error(body.detail || `HTTP_${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function downloadFile(fileId: string, filename = 'clarity-result') {
  const response = await fetch(`${API_BASE}/uploads/${fileId}/download`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    credentials: 'include',
  })
  if (!response.ok) throw new Error('download_failed')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
