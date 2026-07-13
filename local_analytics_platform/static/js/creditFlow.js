export function createCreditFlowLoader({ fetchJson, state, renderCreditFlow }) {
  return async function loadCreditFlow(days) {
    state.creditFlow = await fetchJson("/api/credit-flow-analytics", { days, limit: 12 });
    renderCreditFlow();
  };
}
