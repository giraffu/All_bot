const $ = (selector) => document.querySelector(selector);

const H3_MAIN_MODEL_LABELS = {
  official: "官方主模型",
  official_ref2v_turbo: "官方 Ref2V Turbo",
  "10eros_bf16": "10Eros H3 BF16",
  "10eros_int8": "10Eros H3 INT8",
};

function h3MainModelLabel(mainModel) {
  return H3_MAIN_MODEL_LABELS[mainModel] || mainModel;
}

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
      h3_main_model: $("#generationHistoryH3MainModelSelect")?.value || "",
      history_id: $("#generationHistoryIdInput")?.value || "",
      task_id: $("#generationHistoryTaskIdInput")?.value || "",
      user_id: $("#generationHistoryUserIdInput")?.value || "",
      date_from: $("#generationHistoryDateFromInput")?.value || "",
      date_to: $("#generationHistoryDateToInput")?.value || "",
      archive_status: $("#generationHistoryArchiveStatusSelect")?.value || "",
      snapshot_backup_status: $("#generationHistorySnapshotStatusSelect")?.value || "",
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

  function renderH3MainModels() {
    const select = $("#generationHistoryH3MainModelSelect");
    if (!select) return;
    const selected = state.generationHistory?.filters?.h3_main_model ?? select.value ?? "";
    const options = [
      '<option value="">全部 H3 主模型</option>',
      '<option value="__unrecorded__">未记录（旧 H3 历史）</option>',
      ...(state.generationHistory?.h3_main_models || []).map((row) => (
        `<option value="${escapeHtml(row.main_model)}">${escapeHtml(h3MainModelLabel(row.main_model))}（${fmt(row.generation_count)}）</option>`
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
    const renderMediaAddress = (row, roleGroup) => {
      const isInput = roleGroup === "input";
      const total = Number(row[isInput ? "input_asset_count" : "output_asset_count"] || 0);
      const verified = Number(row[isInput ? "input_verified_count" : "output_verified_count"] || 0);
      const snapshotTotal = Number(row[isInput ? "input_snapshot_count" : "output_snapshot_count"] || 0);
      const backedUp = Number(row[isInput ? "input_snapshot_backed_up_count" : "output_snapshot_backed_up_count"] || 0);
      const missing = Number(row[isInput ? "input_snapshot_missing_count" : "output_snapshot_missing_count"] || 0);
      if (!total && !snapshotTotal) return '<span class="muted">无媒体</span>';
      const summary = snapshotTotal
        ? `NAS 已备份 ${fmt(backedUp)} / ${fmt(snapshotTotal)}${missing ? ` · 文件缺失 ${fmt(missing)}` : ""}`
        : `未纳入快照 · 官方归档可用 ${fmt(verified)} / ${fmt(total)}`;
      const previewUrl = row[isInput ? "input_preview_url" : "output_preview_url"] || "";
      const previewKind = row[isInput ? "input_preview_kind" : "output_preview_kind"] || "";
      const preview = previewUrl && previewKind === "video"
        ? `<video class="generation-history-media-preview" muted playsinline preload="metadata" src="${escapeHtml(previewUrl)}"></video>`
        : previewUrl
          ? `<img class="generation-history-media-preview" loading="lazy" src="${escapeHtml(previewUrl)}" alt="${isInput ? "输入" : "输出"}预览" />`
          : '<span class="generation-history-media-placeholder">暂无预览</span>';
      return `<div class="generation-history-media-summary">${summary}</div>
        <button type="button" class="generation-history-media-button" data-history-media="${escapeHtml(row.id)}" data-role-group="${roleGroup}">
          ${preview}<span>查看${isInput ? "输入" : "输出"}</span>
        </button>`;
    };
    body.innerHTML = rows.map((row) => `
      <tr>
        <td class="mono generation-history-user-id">${escapeHtml(row.user_id ?? "-")}</td>
        <td>${escapeHtml(row.nickname || "-")}</td>
        <td>
          <strong>${escapeHtml(row.task_type || "unknown")}</strong>
          <div class="muted small">该类 ${fmt(taskTypeCounts.get(row.task_type) || 0)} 条</div>
        </td>
        <td>${escapeHtml(row.h3_main_model ? h3MainModelLabel(row.h3_main_model) : "-")}</td>
        <td>${escapeHtml(row.source || "-")}</td>
        <td class="generation-history-prompt"><div class="generation-history-prompt-text">${escapeHtml(row.prompt || "-")}</div></td>
        <td>${escapeHtml(row.billing_resolution || "-")}</td>
        <td>${fmt(row.duration)}</td>
        <td>${fmt(row.width)}</td>
        <td>${fmt(row.height)}</td>
        <td>${fmt(row.favorite_count)}</td>
        <td>${fmt(row.rating)}</td>
        <td class="generation-history-time">${fmtDate(row.created_at)}</td>
        <td class="generation-history-address">${renderMediaAddress(row, "input")}</td>
        <td class="generation-history-address">${renderMediaAddress(row, "output")}</td>
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
    const snapshot = status.snapshot_backup || {};
    const snapshotCounts = snapshot.status_counts || {};
    const summary = $("#archiveStatusSummary");
    if (summary) summary.innerHTML = [
      ["逻辑资产", status.logical_assets], ["已验收", status.verified_assets],
      ["归档字节", status.archived_bytes], ["待探测", status.pending_assets],
      ["来源离线", status.offline_assets], ["校验错误", status.checksum_errors],
      ["归档积压", status.outbox?.backlog ?? "未同步"],
      ["当前吞吐", status.throughput_bytes_per_second ? `${(Number(status.throughput_bytes_per_second) / 1024 / 1024).toFixed(2)} MiB/s` : "-"],
      ["容量使用", status.usage_ratio == null ? "未配置" : `${(Number(status.usage_ratio) * 100).toFixed(1)}%`],
      ["暂停原因", status.pause_reason || "无"],
      ["NAS 快照已备份", snapshotCounts.backed_up ?? "索引未就绪"],
      ["NAS 快照文件缺失", snapshotCounts.file_missing ?? "-"],
      ["NAS 快照未备份", snapshotCounts.not_backed_up ?? "-"],
    ].map(([label, value]) => `<article class="metric-card"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${typeof value === "number" ? fmt(value) : escapeHtml(value ?? "-")}</div></article>`).join("");
    renderTaskTypes();
    renderH3MainModels();
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
  $("#generationHistoryH3MainModelSelect")?.addEventListener("change", resetAndLoad);
  $("#generationHistorySortSelect")?.addEventListener("change", resetAndLoad);
  ["#generationHistoryIdInput", "#generationHistoryTaskIdInput", "#generationHistoryUserIdInput", "#generationHistoryDateFromInput", "#generationHistoryDateToInput", "#generationHistoryArchiveSourceInput"].forEach((selector) => {
    $(selector)?.addEventListener("change", resetAndLoad);
  });
  ["#generationHistoryArchiveStatusSelect", "#generationHistorySnapshotStatusSelect", "#generationHistoryAssetRoleSelect", "#generationHistoryLossOnly"].forEach((selector) => {
    $(selector)?.addEventListener("change", resetAndLoad);
  });
  $("#generationHistoryRows")?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-history-media]");
    if (!button) return;
    const historyId = button.dataset.historyMedia;
    const roleGroup = button.dataset.roleGroup || "all";
    try {
      const payload = await fetchJson(`/api/generation-history/${historyId}/media`, { role_group: roleGroup });
      const dialog = $("#generationHistoryMediaDialog");
      const roleLabel = { input: "输入", output: "输出", all: "全部" }[payload.role_group] || "全部";
      const sourceLabel = payload.media_source === "snapshot_backup" ? "NAS 快照备份" : "官方归档";
      $("#generationHistoryMediaTitle").textContent = `History #${historyId} · ${roleLabel} · ${sourceLabel} · ${payload.assets.length} 个逻辑媒体`;
      $("#generationHistoryMediaBody").innerHTML = payload.assets.length ? payload.assets.map((asset) => {
        const contentUrl = asset.content_url || "";
        const safeContentUrl = escapeHtml(contentUrl);
        const previewLabel = `${asset.role} #${fmt(asset.ordinal)}`;
        const preview = contentUrl && (asset.mime_type || "").startsWith("image/")
          ? `<button type="button" class="archive-media-preview-trigger" data-archive-image-preview="${safeContentUrl}" data-preview-label="${escapeHtml(previewLabel)}" aria-label="放大查看 ${escapeHtml(previewLabel)}">
              <img loading="lazy" src="${safeContentUrl}" alt="${escapeHtml(previewLabel)}" />
              <span>点击放大查看原图</span>
            </button>`
          : contentUrl && (asset.mime_type || "").startsWith("video/")
            ? `<video controls preload="metadata" src="${safeContentUrl}"></video>` : "";
        return `<article class="archive-media-card">${preview}<strong>${escapeHtml(asset.role)} #${fmt(asset.ordinal)}</strong>
          <span class="archive-status archive-status-${escapeHtml(asset.status)}">${escapeHtml({ backed_up: "已备份", file_missing: "文件缺失", not_backed_up: "未备份", backing_up: "备份中", backup_failed: "备份失败" }[asset.status] || asset.status)}</span>
          <div class="small"><span class="muted">原始引用：</span>${escapeHtml(asset.original_ref)}</div>
          <div class="mono small">${asset.byte_size ? `${fmt(asset.byte_size)} bytes` : "-"} · ${escapeHtml(asset.sha256 || "无 SHA-256")}</div>
          <div class="small">来源：${escapeHtml(asset.found_source || "-")}</div>
          ${contentUrl ? '<span class="muted small">原件已在当前页面提供预览</span>' : '<span class="muted small">本地原件尚不可用</span>'}</article>`;
      }).join("") : '<div class="empty">此 History 尚无目录资产，请先运行盘点。</div>';
      dialog.showModal();
    } catch (error) { setError(error); }
  });
  $("#generationHistoryMediaBody")?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-archive-image-preview]");
    if (!button) return;
    const previewImage = $("#generationHistoryPreviewImage");
    const previewDialog = $("#generationHistoryPreviewDialog");
    const previewLabel = button.dataset.previewLabel || "归档原图";
    previewImage.src = button.dataset.archiveImagePreview;
    previewImage.alt = previewLabel;
    $("#generationHistoryPreviewTitle").textContent = previewLabel;
    previewDialog.showModal();
  });
  $("#generationHistoryMediaClose")?.addEventListener("click", () => $("#generationHistoryMediaDialog")?.close());
  $("#generationHistoryPreviewClose")?.addEventListener("click", () => $("#generationHistoryPreviewDialog")?.close());
  $("#generationHistoryPreviewDialog")?.addEventListener("close", () => {
    const previewImage = $("#generationHistoryPreviewImage");
    previewImage.removeAttribute("src");
  });
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
