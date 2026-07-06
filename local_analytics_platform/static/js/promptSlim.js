export function createPromptSlimLoader({ fetchJson, state, getPromptSlimParams, renderPromptSlim }) {
  return async function loadPromptSlim() {
    state.promptSlim = await fetchJson("/api/prompt-slim", getPromptSlimParams());
    renderPromptSlim();
  };
}
