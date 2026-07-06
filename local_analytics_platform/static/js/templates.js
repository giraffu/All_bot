export function createTemplatesLoader({
  fetchJson,
  state,
  getTemplatePromptParams,
  renderTemplateCandidates,
}) {
  return async function loadTemplates(days) {
    state.templates = await fetchJson("/api/prompts", getTemplatePromptParams(days));
    renderTemplateCandidates(state.templates);
  };
}
