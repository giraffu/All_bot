export function createTemplatesLoader({
  fetchJson,
  state,
  getTemplateCandidateParams,
  renderTemplateCandidates,
}) {
  return async function loadTemplates() {
    state.templates = await fetchJson(
      "/api/prompt-template-candidates",
      getTemplateCandidateParams({ includeFilters: true })
    );
    renderTemplateCandidates(state.templates);
  };
}
