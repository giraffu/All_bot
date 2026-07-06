export function loginNextPath() {
  return `${window.location.pathname}${window.location.search}${window.location.hash}` || "/";
}

export async function fetchJson(path, params = {}, options = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  const response = await fetch(url, options);
  if (!response.ok) {
    if (response.status === 401) {
      window.location.assign(`/login?next=${encodeURIComponent(loginNextPath())}`);
    }
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      detail = await response.text();
    }
    throw new Error(`${response.status} ${detail}`);
  }
  return response.json();
}

export async function logoutLocalAnalytics() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.assign("/login");
  }
}

