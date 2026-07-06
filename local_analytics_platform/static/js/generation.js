export function createGenerationModule({
  fetchJson,
  state,
  renderGeneration,
  renderGenerationCharts,
  getCompareDates,
  selectNumber,
  setError,
}) {
  async function loadGeneration(days) {
    state.generation = await fetchJson("/api/generation", { days, limit: 12 });
    renderGeneration();
  }

  async function loadGenerationHourlyComparison() {
    try {
      setError(null);
      const dates = getCompareDates("#generationCompareDatesInput", state.generation?.daily || []);
      const payload = await fetchJson("/api/generation/hourly-comparison", { dates: dates.join(",") });
      state.generationCompareMode = "hourly-comparison";
      renderGenerationCharts(payload.hourly || [], "hourly-comparison");
    } catch (error) {
      setError(error);
    }
  }

  async function loadGenerationHourlyCumulative() {
    try {
      setError(null);
      const days = selectNumber("#generationHourlyRangeSelect", 30);
      const payload = await fetchJson("/api/generation/hourly-cumulative", { days });
      state.generationCompareMode = "hourly-cumulative";
      renderGenerationCharts(payload.hourly || [], "hourly-cumulative");
    } catch (error) {
      setError(error);
    }
  }

  async function loadGenerationTypeComparison() {
    try {
      setError(null);
      const dates = getCompareDates("#generationCompareDatesInput", state.generation?.daily || []);
      const payload = await fetchJson("/api/generation/type-comparison", { dates: dates.join(",") });
      state.generationCompareMode = "types";
      renderGenerationCharts(payload.types || [], "types");
    } catch (error) {
      setError(error);
    }
  }

  return {
    loadGeneration,
    loadGenerationHourlyComparison,
    loadGenerationHourlyCumulative,
    loadGenerationTypeComparison,
  };
}
