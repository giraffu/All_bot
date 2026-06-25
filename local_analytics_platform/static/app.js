const state = {
  overview: null,
  finance: null,
  generation: null,
  prompts: null,
  media: null,
  selectedPrompt: null,
  activeTab: "overview",
};

const tabs = {
  overview: {
    kicker: "经营概览",
    title: "收入、用户、生成和媒体状态",
    subtitle: "本地 shadow 数据总览",
  },
  finance: {
    kicker: "充值分析",
    title: "支付渠道、首充和复购分层",
    subtitle: "RMB / TON / Stars / 内部订单分开统计",
  },
  generation: {
    kicker: "生成分析",
    title: "任务类型、消耗、输入输出和复用信号",
    subtitle: "按任务类型查看生成、成本和互动结果",
  },
  prompts: {
    kicker: "提示词洞察",
    title: "正向信号、结构标签和输入要求",
    subtitle: "机器候选评分用于人工筛选",
  },
  templates: {
    kicker: "模板候选",
    title: "可沉淀的场景样本",
    subtitle: "从高分 prompt 中挑选可复用模板",
  },
  media: {
    kicker: "媒体核验",
    title: "History 输入输出对象引用",
    subtitle: "基于数据库记录解析媒体 key",
  },
};

const $ = (selector) => document.querySelector(selector);
const nf = new Intl.NumberFormat("zh-CN");
const money = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmt(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? nf.format(numeric) : escapeHtml(value);
}

function fmtAmount(value, unit = "") {
  const numeric = Number(value || 0);
  return `${money.format(numeric)}${unit}`;
}

function fmtDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function metric(label, value, note = "") {
  return `
    <div class="metric-card">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${value}</div>
      ${note ? `<div class="metric-note">${escapeHtml(note)}</div>` : ""}
    </div>
  `;
}

async function fetchJson(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  const response = await fetch(url);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      detail = await response.text();
    }
    throw new Error(`${response.status} ${detail}`);
  }
  return response.json();
}

function renderSource() {
  const source = state.overview?.source;
  if (!source) return;
  const media = source.media_url_enabled ? "媒体 URL 已启用" : "媒体 URL 未配置";
  $("#sourceLine").textContent = `${source.database_url || "shadow database"} · ${source.media_bucket} · ${media}`;
  $("#sidebarStatus").textContent = `${state.overview?.metrics?.total_history ? fmt(state.overview.metrics.total_history) : "-"} 条 history · ${media}`;
}

function setActiveTab(tabName, syncHash = true) {
  const tab = tabs[tabName] ? tabName : "overview";
  state.activeTab = tab;
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.panel === tab);
  });
  $("#activeKicker").textContent = tabs[tab].kicker;
  $("#activeTitle").textContent = tabs[tab].title;
  $("#activeSubtitle").textContent = tabs[tab].subtitle;
  if (syncHash) {
    history.replaceState(null, "", `#${tab}`);
  }
}

function renderOverview() {
  const metrics = state.overview?.metrics || {};
  const finance = state.finance?.summary || {};
  const generation = state.generation?.summary || {};
  $("#metricGrid").innerHTML = [
    metric("总用户", fmt(metrics.total_users), `近 ${state.overview.days} 天新增 ${fmt(metrics.new_users)}`),
    metric("总生成记录", fmt(metrics.total_history), `近 ${state.overview.days} 天 ${fmt(metrics.recent_history)}`),
    metric("真实付费用户", fmt(metrics.paying_users), `成功订单 ${fmt(metrics.successful_orders)}`),
    metric("近周期 RMB", fmtAmount(metrics.recent_rmb_amount, " RMB"), `TON ${fmtAmount(metrics.recent_ton_amount)} · Stars ${fmt(metrics.recent_stars_amount)}`),
    metric("近周期活跃用户", fmt(metrics.active_users), "按 last_activity 统计"),
    metric("近周期创作者", fmt(generation.creators), `生成 ${fmt(generation.generations)}`),
    metric("Prompt 解锁", fmt(metrics.recent_prompt_unlocks), `Gallery ${fmt(metrics.active_gallery_posts)} 个活跃作品`),
    metric("内部/其他订单", fmt(finance.internal_success_orders), `最近订单 ${fmtDate(metrics.latest_order_at)}`),
  ].join("");

  renderSpark("#generationSpark", state.overview.daily || [], "generations");
  renderSpark("#rmbSpark", state.overview.daily || [], "rmb_amount");
}

function renderSpark(selector, rows, key) {
  const max = Math.max(1, ...rows.map((row) => Number(row[key] || 0)));
  $(selector).innerHTML = rows
    .map((row) => {
      const height = Math.max(4, Math.round((Number(row[key] || 0) / max) * 86));
      return `<div class="spark-bar" style="height:${height}px" title="${escapeHtml(row.day)}: ${fmt(row[key])}"></div>`;
    })
    .join("");
}

function renderFinance() {
  const summary = state.finance?.summary || {};
  const first = state.finance?.first_purchase || {};
  $("#financeSummary").innerHTML = [
    metric("RMB", fmtAmount(summary.rmb_amount, " RMB"), `均单 ${fmtAmount(summary.rmb_avg_order, " RMB")}`),
    metric("TON", fmtAmount(summary.ton_amount), "链上支付"),
    metric("Stars", fmt(summary.stars_amount), "Telegram Stars"),
    metric("真实付费人数", fmt(summary.real_payers), `成功订单 ${fmt(summary.success_orders)}`),
    metric("首充用户", fmt(first.first_purchase_users), `中位首充 ${fmtAmount(first.median_hours_to_first_purchase, " 小时")}`),
  ].join("");

  $("#financeChannels").innerHTML = tableRows(state.finance?.channels, (row) => `
    <tr>
      <td class="mono">${escapeHtml(row.channel)}</td>
      <td>${fmt(row.success_orders)}</td>
      <td>${fmt(row.payers)}</td>
      <td>${fmtAmount(row.amount)}</td>
      <td>${fmtAmount(row.avg_order_amount)}</td>
      <td>${fmt(row.plan_reward_credits)}</td>
    </tr>
  `);

  $("#financeSegments").innerHTML = tableRows(state.finance?.segments, (row) => `
    <tr>
      <td>${escapeHtml(row.segment)}</td>
      <td>${fmt(row.users)}</td>
      <td>${fmt(row.orders)}</td>
      <td>${fmtAmount(row.rmb_amount, " RMB")}</td>
      <td>${fmtAmount(row.avg_rmb_per_user, " RMB")}</td>
    </tr>
  `);
}

function renderGeneration() {
  const summary = state.generation?.summary || {};
  $("#generationSummary").innerHTML = [
    metric("生成总量", fmt(summary.generations), `Web ${fmt(summary.web_generations)} · Bot ${fmt(summary.bot_generations)}`),
    metric("生成用户", fmt(summary.creators), "去重 user_id"),
    metric("结果记录", fmt(summary.result_records), "含 output/extra outputs"),
    metric("收藏记录", fmt(summary.favorited_records), `公开 ${fmt(summary.public_records)}`),
    metric("平均尺寸", `${fmt(Math.round(summary.avg_width || 0))} x ${fmt(Math.round(summary.avg_height || 0))}`, `平均时长 ${fmtAmount(summary.avg_duration, " 秒")}`),
  ].join("");

  const existing = $("#taskTypeSelect").value;
  const options = ['<option value="">全部</option>'].concat(
    (state.generation?.by_type || []).map((row) => `<option value="${escapeHtml(row.task_type)}">${escapeHtml(row.task_type)}</option>`)
  );
  $("#taskTypeSelect").innerHTML = options.join("");
  $("#taskTypeSelect").value = existing;

  $("#generationTypes").innerHTML = tableRows(state.generation?.by_type, (row) => `
    <tr>
      <td class="mono">${escapeHtml(row.task_type)}</td>
      <td>${fmt(row.generations)}</td>
      <td>${fmt(row.creators)}</td>
      <td>${fmt(row.result_records)}</td>
      <td>${fmt(row.favorited_records)}</td>
      <td>${fmt(row.gallery_posts)}</td>
      <td>${fmt(row.applies)}</td>
    </tr>
  `);

  $("#generationCredits").innerHTML = tableRows(state.generation?.credits, (row) => `
    <tr>
      <td class="mono">${escapeHtml(row.task_type)}</td>
      <td>${fmt(row.debit_events)}</td>
      <td>${fmt(row.credits_spent)}</td>
      <td>${fmtAmount(row.avg_credits_per_event)}</td>
    </tr>
  `);

  renderHourly();
}

function renderHourly() {
  const rows = state.generation?.hourly || [];
  const byHour = new Map(rows.map((row) => [Number(row.hour), row]));
  const max = Math.max(1, ...rows.map((row) => Number(row.generations || 0)));
  $("#hourlyBars").innerHTML = Array.from({ length: 24 }, (_, hour) => {
    const row = byHour.get(hour) || { generations: 0, creators: 0 };
    const height = Math.max(5, Math.round((Number(row.generations || 0) / max) * 100));
    return `
      <div class="hour-slot">
        <div class="hourly-bar" style="height:${height}px" title="${hour}:00 ${fmt(row.generations)}"></div>
        <span>${hour}</span>
      </div>
    `;
  }).join("");
}

function renderPrompts() {
  const tags = state.prompts?.tag_summary || [];
  $("#tagSummary").innerHTML = tags.length
    ? tags.map((tag) => `<span class="pill">${escapeHtml(tag.tag)} ${fmt(tag.count)}</span>`).join("")
    : '<span class="muted">暂无标签</span>';

  const candidates = state.prompts?.candidates || [];
  if (!state.selectedPrompt || !candidates.some((item) => item.id === state.selectedPrompt.id)) {
    state.selectedPrompt = candidates[0] || null;
  }

  $("#promptRows").innerHTML = tableRows(candidates, (row) => `
    <tr data-prompt-id="${row.id}">
      <td><strong>${fmt(row.prompt_score)}</strong></td>
      <td class="mono">${escapeHtml(row.task_type)}</td>
      <td>
        <div class="prompt-preview">${escapeHtml(row.prompt_preview)}</div>
        <div class="pill-list">${(row.tags || []).map((tag) => `<span class="pill gray">${escapeHtml(tag)}</span>`).join("")}</div>
      </td>
      <td>
        <div>赞 ${fmt(row.likes)} · 应用 ${fmt(row.applies)}</div>
        <div>解锁 ${fmt(row.prompt_unlocks)} · 评论 ${fmt(row.comments)}</div>
      </td>
      <td>${fmt(row.media?.input?.total)} in / ${fmt(row.media?.output?.total)} out</td>
    </tr>
  `);

  document.querySelectorAll("#promptRows tr").forEach((row) => {
    row.addEventListener("click", () => {
      const id = Number(row.dataset.promptId);
      state.selectedPrompt = candidates.find((item) => item.id === id) || candidates[0] || null;
      renderPromptDetail();
    });
  });
  renderPromptDetail();
  renderTemplateCandidates();
}

function renderPromptDetail() {
  const item = state.selectedPrompt;
  if (!item) {
    $("#promptDetail").innerHTML = '<div class="empty">暂无候选</div>';
    return;
  }
  const refs = []
    .concat((item.input_refs || []).map((ref) => ({ type: "输入", ref })))
    .concat((item.output_refs || []).map((ref) => ({ type: "输出", ref })));
  $("#promptDetail").innerHTML = `
    <h3>${escapeHtml(item.task_type)} · 评分 ${fmt(item.prompt_score)}</h3>
    <p class="prompt-preview">${escapeHtml(item.prompt_preview)}</p>
    <dl>
      <dt>时间</dt><dd>${fmtDate(item.created_at)}</dd>
      <dt>信号</dt><dd>赞 ${fmt(item.likes)} / 应用 ${fmt(item.applies)} / 解锁 ${fmt(item.prompt_unlocks)}</dd>
      <dt>输入要求</dt><dd>${(item.input_requirements || []).map(escapeHtml).join(" · ")}</dd>
      <dt>标签</dt><dd>${(item.tags || []).map((tag) => `<span class="pill">${escapeHtml(tag)}</span>`).join(" ") || "-"}</dd>
      <dt>尺寸</dt><dd>${fmt(item.width)} x ${fmt(item.height)} · ${fmt(item.duration)} 秒</dd>
    </dl>
    <div class="table-title">媒体引用</div>
    <div class="ref-list">
      ${refs.slice(0, 10).map((entry) => `<div class="ref-item"><strong>${entry.type}</strong> ${escapeHtml(entry.ref)}</div>`).join("") || '<div class="muted">无媒体引用</div>'}
    </div>
  `;
}

function renderTemplateCandidates() {
  const candidates = (state.prompts?.candidates || [])
    .filter((item) => Number(item.prompt_score || 0) >= 20)
    .slice(0, 9);
  $("#templateCandidates").innerHTML = candidates.length
    ? candidates.map((item) => `
      <article class="candidate-card">
        <div class="candidate-title">
          <span class="mono">${escapeHtml(item.task_type)}</span>
          <span class="pill amber">${fmt(item.prompt_score)}</span>
        </div>
        <div class="candidate-prompt">${escapeHtml(item.prompt_preview)}</div>
        <div class="pill-list" style="margin-top:12px">
          ${(item.input_requirements || []).slice(0, 3).map((tag) => `<span class="pill gray">${escapeHtml(tag)}</span>`).join("")}
        </div>
      </article>
    `).join("")
    : '<div class="empty">暂无高分候选</div>';
}

function renderMedia() {
  const totals = state.media?.totals || {};
  $("#mediaSummary").innerHTML = [
    metric("采样记录", fmt((state.media?.records || []).length), `近 ${state.media?.days || "-"} 天`),
    metric("有输出记录", fmt(totals.with_output), "按 DB 引用统计"),
    metric("输入引用", fmt(totals.input_refs), "对象 key"),
    metric("输出引用", fmt(totals.output_refs), "对象 key"),
    metric("媒体类型", `${fmt(totals.images)} 图 / ${fmt(totals.videos)} 视频`, state.media?.media_url_enabled ? "可生成媒体 URL" : "仅展示 key"),
  ].join("");

  $("#mediaRows").innerHTML = tableRows(state.media?.records, (row) => `
    <tr>
      <td>${fmtDate(row.created_at)}</td>
      <td class="mono">${escapeHtml(row.task_type)}</td>
      <td>${renderRefs(row.input_refs)}</td>
      <td>${renderRefs(row.output_refs)}</td>
      <td>${fmt(row.width)} x ${fmt(row.height)}<br><span class="muted">${fmt(row.duration)} 秒</span></td>
    </tr>
  `);
}

function renderRefs(refs = []) {
  if (!refs.length) return '<span class="muted">-</span>';
  return `<div class="ref-list">${refs.slice(0, 3).map((ref) => `<div class="ref-item">${escapeHtml(ref)}</div>`).join("")}</div>`;
}

function tableRows(rows, renderer) {
  if (!rows || !rows.length) {
    return '<tr><td colspan="8" class="muted">暂无数据</td></tr>';
  }
  return rows.map(renderer).join("");
}

function setError(error) {
  const banner = $("#errorBanner");
  if (!error) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  banner.classList.remove("hidden");
  banner.textContent = error.message || String(error);
}

function setLoading(isLoading) {
  $("#refreshButton").disabled = isLoading;
  $("#refreshButton").textContent = isLoading ? "刷新中" : "刷新";
}

async function loadAll() {
  setLoading(true);
  setError(null);
  const days = Number($("#daysSelect").value || 30);
  const promptDays = Number($("#promptDaysSelect").value || 30);
  const taskType = $("#taskTypeSelect").value || "";
  try {
    const [overview, finance, generation, prompts, media] = await Promise.all([
      fetchJson("/api/overview", { days }),
      fetchJson("/api/finance", { days }),
      fetchJson("/api/generation", { days }),
      fetchJson("/api/prompts", { days: promptDays, task_type: taskType, limit: 80 }),
      fetchJson("/api/media-audit", { days, limit: 100 }),
    ]);
    Object.assign(state, { overview, finance, generation, prompts, media });
    renderSource();
    renderOverview();
    renderFinance();
    renderGeneration();
    renderPrompts();
    renderMedia();
    $("#lastUpdated").textContent = `更新于 ${new Date().toLocaleString("zh-CN", { hour12: false })}`;
    document.body.dataset.loaded = "true";
  } catch (error) {
    setError(error);
  } finally {
    setLoading(false);
  }
}

$("#refreshButton").addEventListener("click", loadAll);
$("#daysSelect").addEventListener("change", loadAll);
$("#promptDaysSelect").addEventListener("change", loadAll);
$("#taskTypeSelect").addEventListener("change", loadAll);
document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => setActiveTab(button.dataset.tab));
});
window.addEventListener("hashchange", () => setActiveTab(location.hash.replace("#", ""), false));

setActiveTab(location.hash.replace("#", "") || "overview", false);
loadAll();
