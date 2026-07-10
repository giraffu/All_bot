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
  let rawBody = "";
  try {
    rawBody = await response.text();
  } catch (_) {
    rawBody = "";
  }
  if (!response.ok) {
    if (response.status === 401) {
      window.location.assign(`/login?next=${encodeURIComponent(loginNextPath())}`);
    }
    let detail = response.statusText;
    if (rawBody) {
      try {
        const body = JSON.parse(rawBody);
        detail = body.detail || rawBody || detail;
      } catch (_) {
        detail = rawBody;
      }
    }
    throw new Error(`${response.status} ${detail}`);
  }
  if (!rawBody) return {};
  try {
    return JSON.parse(rawBody);
  } catch (_) {
    return {};
  }
}

export async function logoutLocalAnalytics() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.assign("/login");
  }
}
