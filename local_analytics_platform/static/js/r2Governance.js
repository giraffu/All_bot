export function createR2GovernanceLoader({ fetchJson, state, escapeHtml, fmt }) {
  const metric = (label, value, detail) => `<div class="metric-card"><div class="metric-label">${label}</div><div class="metric-value">${value}</div><div class="metric-detail">${detail}</div></div>`;
  const bytes = (value) => {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) return "-";
    const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
    let amount = numeric;
    let unit = 0;
    while (Math.abs(amount) >= 1024 && unit < units.length - 1) {
      amount /= 1024;
      unit += 1;
    }
    return `${amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 })} ${units[unit]}`;
  };
  return async function loadR2Governance() {
    state.r2Governance = await fetchJson("/api/r2-governance/status");
    const payload = state.r2Governance || {};
    const latest = payload.latest || {};
    const staging = payload.staging || {};
    const inventory = payload.inventory || {};
    const web = payload.web_uploads_report_only || {};
    const persistence = payload.persistence_failure_counts || {};
    const persistenceFailures = Object.values(persistence).reduce((sum, value) => sum + Number(value || 0), 0);
    document.querySelector("#r2GovernanceSummary").innerHTML = [
      metric("最近批次", escapeHtml(latest.batch_id || "-"), `${escapeHtml(latest.mode || "-")} / ${escapeHtml(latest.status || "-")}`),
      metric("候选 / 验证", `${fmt(latest.candidate_count)} / ${fmt(latest.verified_count)}`, `阻断 ${fmt(latest.referenced_blocked_count)}`),
      metric("计划/删除字节", bytes(latest.delete_bytes), `删除后复核 ${fmt(latest.post_delete_verified_count)}`),
      metric("Staging", bytes(staging.bytes), `${fmt(staging.object_count)} 对象，最老 ${fmt(staging.oldest_age_hours)} 小时`),
      metric("Inventory", bytes(inventory.bytes), `${fmt(inventory.object_count)} 对象，年龄 ${fmt(inventory.age_hours)} 小时`),
      metric("web_uploads（仅报告）", bytes(web.bytes), `${fmt(web.object_count)} 对象`),
      metric("持久化拒绝/失败", fmt(persistenceFailures), `旧 completion ${fmt(persistence.legacy_media_completion_rejected || 0)}`),
    ].join("");
    const rows = payload.batches || [];
    document.querySelector("#r2GovernanceRows").innerHTML = rows.length ? rows.map((row) => `<tr><td>${escapeHtml(row.generated_at || "-")}</td><td>${escapeHtml(row.batch_id || "-")}</td><td>${escapeHtml(row.mode || "-")} / ${escapeHtml(row.status || "-")}</td><td>${fmt(row.candidate_count)}</td><td>${fmt(row.verified_count)}</td><td>${fmt(row.delete_count)}</td><td>${fmt(row.referenced_blocked_count)}</td><td>${fmt(row.probe_failure_count)}</td></tr>`).join("") : '<tr><td colspan="8"><div class="empty compact">暂无治理 evidence</div></td></tr>';
  };
}
