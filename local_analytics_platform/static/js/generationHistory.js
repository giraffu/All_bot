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
      history_id: $("#generationHistoryIdInput")?.value || "",
      task_id: $("#generationHistoryTaskIdInput")?.value || "",
      user_id: $("#generationHistoryUserIdInput")?.value || "",
      date_from: $("#generationHistoryDateFromInput")?.value || "",
      date_to: $("#generationHistoryDateToInput")?.value || "",
      archive_status: $("#generationHistoryArchiveStatusSelect")?.value || "",
      asset_role: $("#generationHistoryAssetRoleSelect")?.value || "",
      archive_source: $("#generationHistoryArchiveSourceInput")?.value || "",
      loss_only: $("#generationHistoryLossOnly")?.checked || false,
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
      body.innerHTML = '<tr><td colspan="15" class="empty">暂无历史生成记录</td></tr>';
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
        <td><button type="button" data-history-media="${escapeHtml(row.id)}">查看媒体</button></td>
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
    const status = state.archiveStatus || {};
    const summary = $("#archiveStatusSummary");
    if (summary) summary.innerHTML = [
      ["逻辑资产", status.logical_assets], ["已验收", status.verified_assets],
      ["归档字节", status.archived_bytes], ["待探测", status.pending_assets],
      ["来源离线", status.offline_assets], ["校验错误", status.checksum_errors],
      ["归档积压", status.outbox?.backlog ?? "未同步"],
      ["当前吞吐", status.throughput_bytes_per_second ? `${(Number(status.throughput_bytes_per_second) / 1024 / 1024).toFixed(2)} MiB/s` : "-"],
      ["容量使用", status.usage_ratio == null ? "未配置" : `${(Number(status.usage_ratio) * 100).toFixed(1)}%`],
      ["暂停原因", status.pause_reason || "无"],
    ].map(([label, value]) => `<article class="metric-card"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${typeof value === "number" ? fmt(value) : escapeHtml(value ?? "-")}</div></article>`).join("");
    renderTaskTypes();
    renderRows();
    renderPagination();
  }

  async function loadGenerationHistory() {
    const [history, archiveStatus] = await Promise.all([
      fetchJson("/api/generation-history", params()),
      fetchJson("/api/archive/status"),
    ]);
    state.generationHistory = history;
    state.archiveStatus = archiveStatus;
    state.generationHistoryPage = state.generationHistory?.pagination?.page || 1;
    render();
  }

  function resetAndLoad() {
    state.generationHistoryPage = 1;
    loadGenerationHistory().catch(setError);
  }

  $("#generationHistoryTaskTypeSelect")?.addEventListener("change", resetAndLoad);
  $("#generationHistorySortSelect")?.addEventListener("change", resetAndLoad);
  ["#generationHistoryIdInput", "#generationHistoryTaskIdInput", "#generationHistoryUserIdInput", "#generationHistoryDateFromInput", "#generationHistoryDateToInput", "#generationHistoryArchiveSourceInput"].forEach((selector) => {
    $(selector)?.addEventListener("change", resetAndLoad);
  });
  ["#generationHistoryArchiveStatusSelect", "#generationHistoryAssetRoleSelect", "#generationHistoryLossOnly"].forEach((selector) => {
    $(selector)?.addEventListener("change", resetAndLoad);
  });
  $("#generationHistoryRows")?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-history-media]");
    if (!button) return;
    const historyId = button.dataset.historyMedia;
    try {
      const payload = await fetchJson(`/api/generation-history/${historyId}/media`);
      const dialog = $("#generationHistoryMediaDialog");
      $("#generationHistoryMediaTitle").textContent = `History #${historyId} · ${payload.assets.length} 个逻辑媒体`;
      $("#generationHistoryMediaBody").innerHTML = payload.assets.length ? payload.assets.map((asset) => {
        const contentUrl = asset.status === "archived_verified" ? `/api/archive/assets/${asset.id}/content` : "";
        const preview = contentUrl && (asset.mime_type || "").startsWith("image/")
          ? `<img loading="lazy" src="${contentUrl}" alt="${escapeHtml(asset.role)}" />`
          : contentUrl && (asset.mime_type || "").startsWith("video/")
            ? `<video controls preload="metadata" src="${contentUrl}"></video>` : "";
        return `<article class="archive-media-card">${preview}<strong>${escapeHtml(asset.role)} #${fmt(asset.ordinal)}</strong>
          <span class="archive-status archive-status-${escapeHtml(asset.status)}">${escapeHtml(asset.status)}</span>
          <div class="muted small">${escapeHtml(asset.original_ref)}</div>
          <div class="mono small">${asset.byte_size ? `${fmt(asset.byte_size)} bytes` : "-"} · ${escapeHtml(asset.sha256 || "无 SHA-256")}</div>
          <div class="small">来源：${escapeHtml(asset.found_source || "-")}</div>
          ${contentUrl ? `<a href="${contentUrl}" target="_blank" rel="noopener">打开原件</a>` : ""}</article>`;
      }).join("") : '<div class="empty">此 History 尚无目录资产，请先运行盘点。</div>';
      dialog.showModal();
    } catch (error) { setError(error); }
  });
  $("#generationHistoryMediaClose")?.addEventListener("click", () => $("#generationHistoryMediaDialog")?.close());
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
