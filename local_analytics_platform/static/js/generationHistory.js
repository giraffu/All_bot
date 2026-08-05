const $ = (selector) => document.querySelector(selector);

export function createGenerationHistoryModule({
  fetchJson,
  state,
  escapeHtml,
  fmt,
  fmtDate,
  setError,
}) {
  function params() {
    return {
      task_type: $("#generationHistoryTaskTypeSelect")?.value || "",
      sort: $("#generationHistorySortSelect")?.value || "created_desc",
      page: state.generationHistoryPage || 1,
    };
  }

  function renderTaskTypes() {
    const select = $("#generationHistoryTaskTypeSelect");
    if (!select) return;
    const selected = state.generationHistory?.filters?.task_type ?? select.value ?? "";
    const options = [
      '<option value="">所有任务类别</option>',
      ...(state.generationHistory?.task_types || []).map((row) => (
        `<option value="${escapeHtml(row.task_type)}">${escapeHtml(row.task_type)}（${fmt(row.generation_count)}）</option>`
      )),
    ];
    select.innerHTML = options.join("");
    select.value = selected;
  }

  function renderRows() {
    const body = $("#generationHistoryRows");
    if (!body) return;
    const rows = state.generationHistory?.rows || [];
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="14" class="empty">暂无历史生成记录</td></tr>';
      return;
    }
    const taskTypeCounts = new Map(
      (state.generationHistory?.task_types || []).map((row) => [row.task_type, row.generation_count])
    );
    body.innerHTML = rows.map((row) => `
      <tr>
        <td class="mono generation-history-user-id">${escapeHtml(row.user_id ?? "-")}</td>
        <td>${escapeHtml(row.nickname || "-")}</td>
        <td>
          <strong>${escapeHtml(row.task_type || "unknown")}</strong>
          <div class="muted small">该类 ${fmt(taskTypeCounts.get(row.task_type) || 0)} 条</div>
        </td>
        <td>${escapeHtml(row.source || "-")}</td>
        <td class="generation-history-prompt"><div class="generation-history-prompt-text">${escapeHtml(row.prompt || "-")}</div></td>
        <td>${escapeHtml(row.billing_resolution || "-")}</td>
        <td>${fmt(row.duration)}</td>
        <td>${fmt(row.width)}</td>
        <td>${fmt(row.height)}</td>
        <td>${fmt(row.favorite_count)}</td>
        <td>${fmt(row.rating)}</td>
        <td class="generation-history-time">${fmtDate(row.created_at)}</td>
        <td class="generation-history-address">${escapeHtml(row.input_address || "")}</td>
        <td class="generation-history-address">${escapeHtml(row.output_address || "")}</td>
      </tr>
    `).join("");
  }

  function renderPagination() {
    const container = $("#generationHistoryPagination");
    if (!container) return;
    const pagination = state.generationHistory?.pagination || {};
    const current = Number(pagination.page || 1);
    const totalPages = Math.max(1, Number(pagination.total_pages || 1));
    container.innerHTML = `
      <div class="generation-history-page-summary">
        共 ${fmt(pagination.total || 0)} 条 · 第 ${fmt(current)} / ${fmt(totalPages)} 页 · 每页 10 条
      </div>
      <div class="generation-history-page-actions">
        <button type="button" data-history-page="${Math.max(1, current - 1)}" ${current <= 1 ? "disabled" : ""}>上一页</button>
        <form id="generationHistoryPageForm">
          <label for="generationHistoryPageInput">跳至</label>
          <input id="generationHistoryPageInput" type="number" min="1" max="${totalPages}" value="${current}" />
          <button type="submit">跳转</button>
        </form>
        <button type="button" data-history-page="${Math.min(totalPages, current + 1)}" ${current >= totalPages ? "disabled" : ""}>下一页</button>
      </div>
    `;
  }

  function render() {
    renderTaskTypes();
    renderRows();
    renderPagination();
  }

  async function loadGenerationHistory() {
    state.generationHistory = await fetchJson("/api/generation-history", params());
    state.generationHistoryPage = state.generationHistory?.pagination?.page || 1;
    render();
  }

  function resetAndLoad() {
    state.generationHistoryPage = 1;
    loadGenerationHistory().catch(setError);
  }

  $("#generationHistoryTaskTypeSelect")?.addEventListener("change", resetAndLoad);
  $("#generationHistorySortSelect")?.addEventListener("change", resetAndLoad);
  $("#generationHistoryPagination")?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-history-page]");
    if (!button || button.disabled) return;
    state.generationHistoryPage = Number(button.dataset.historyPage || 1);
    loadGenerationHistory().catch(setError);
  });
  $("#generationHistoryPagination")?.addEventListener("submit", (event) => {
    if (event.target.id !== "generationHistoryPageForm") return;
    event.preventDefault();
    const totalPages = Math.max(1, Number(state.generationHistory?.pagination?.total_pages || 1));
    const requested = Number($("#generationHistoryPageInput")?.value || 1);
    state.generationHistoryPage = Math.min(Math.max(1, Math.trunc(requested)), totalPages);
    loadGenerationHistory().catch(setError);
  });

  return { loadGenerationHistory };
}
