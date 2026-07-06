export function createFinanceModule({
  fetchJson,
  state,
  renderFinance,
  renderFinanceCharts,
  getCompareDates,
  selectNumber,
  fmt,
  setError,
}) {
  async function loadFinance(days) {
    state.finance = await fetchJson("/api/finance", { days, limit: 12 });
    renderFinance();
  }

  async function loadFinanceHourlyComparison() {
    try {
      setError(null);
      const dates = getCompareDates("#financeCompareDatesInput", state.finance?.daily || []);
      const payload = await fetchJson("/api/finance/hourly-comparison", { dates: dates.join(",") });
      state.financeHourlyMode = "comparison";
      renderFinanceCharts(payload.hourly || [], "日期对比");
    } catch (error) {
      setError(error);
    }
  }

  async function loadFinanceHourlyCumulative() {
    try {
      setError(null);
      const days = selectNumber("#financeHourlyRangeSelect", 30);
      const payload = await fetchJson("/api/finance/hourly-cumulative", { days });
      state.financeHourlyMode = "cumulative";
      renderFinanceCharts(payload.hourly || [], `近 ${fmt(days)} 天累计`);
    } catch (error) {
      setError(error);
    }
  }

  return {
    loadFinance,
    loadFinanceHourlyComparison,
    loadFinanceHourlyCumulative,
  };
}
