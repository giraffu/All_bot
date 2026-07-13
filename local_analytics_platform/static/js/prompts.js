export function createPromptsLoader({
  fetchJson,
  state,
  getPromptParams,
  renderPromptTaskTypeOptions,
  renderPrompts,
}) {
  return async function loadPrompts(days) {
    state.prompts = await fetchJson("/api/prompts", getPromptParams(days));
    state.promptTaskTypes = state.prompts?.distributions?.task_type || [];
    renderPromptTaskTypeOptions();
    renderPrompts();
  };
}
