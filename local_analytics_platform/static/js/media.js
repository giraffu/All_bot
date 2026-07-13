export function createMediaLoader({ fetchJson, state, renderMedia }) {
  return async function loadMedia(days) {
    state.media = await fetchJson("/api/media-audit", { days, limit: 100 });
    renderMedia();
  };
}
