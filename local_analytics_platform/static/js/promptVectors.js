export function createPromptVectorsModule({
  fetchJson,
  state,
  getPromptVectorParams,
  renderPromptVectors,
  renderPromptVectorResumeStatus,
  markTabStale,
  markTabLoaded,
  setError,
}) {
  async function loadPromptVectors() {
    state.promptVectors = await fetchJson("/api/prompt-vectors", getPromptVectorParams());
    renderPromptVectors();
  }

  async function resumePromptVectorEmbeddings() {
    state.promptVectorResumeLoading = true;
    renderPromptVectorResumeStatus();
    setError(null);
    try {
      state.promptVectorResume = await fetchJson("/api/prompt-vectors/resume", {}, { method: "POST" });
      markTabStale("prompt-vectors");
      await loadPromptVectors();
      markTabLoaded("prompt-vectors");
    } catch (error) {
      setError(error);
    } finally {
      state.promptVectorResumeLoading = false;
      renderPromptVectorResumeStatus();
    }
  }

  return {
    loadPromptVectors,
    resumePromptVectorEmbeddings,
  };
}
