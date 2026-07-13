import { state, tabs } from "./state.js?v=20260710-template-review-low-quality-v1";
import { fetchJson, logoutLocalAnalytics } from "./api.js?v=20260709-prompt-decomposition-v1";
import { createCreditFlowLoader } from "./creditFlow.js?v=20260709-prompt-decomposition-v1";
import { createFinanceModule } from "./finance.js?v=20260709-prompt-decomposition-v1";
import { createGenerationModule } from "./generation.js?v=20260709-prompt-decomposition-v1";
import { createMediaLoader } from "./media.js?v=20260709-prompt-decomposition-v1";
import { createPromptSlimLoader } from "./promptSlim.js?v=20260709-prompt-decomposition-v1";
import { createPromptVectorsModule } from "./promptVectors.js?v=20260709-prompt-decomposition-v1";
import { createPromptsLoader } from "./prompts.js?v=20260709-prompt-decomposition-v1";
import { createTabController } from "./tabs.js?v=20260709-prompt-decomposition-v1";
import { createTemplatesLoader } from "./templates.js?v=20260709-prompt-decomposition-v1";
import { createUsersLoader } from "./users.js?v=20260709-prompt-decomposition-v1";

const $ = (selector) => document.querySelector(selector);
const nf = new Intl.NumberFormat("zh-CN");
const money = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const PROMPT_TOKEN_DEFAULT_MIN_PROMPT_COUNT = 5;
const PROMPT_TOKEN_MAX_MIN_PROMPT_COUNT = 100000;
const PROMPT_TOKEN_RULE_PAGE_SIZE = 25;
const PROMPT_TOKEN_UNCATEGORIZED_CATEGORY = "__uncategorized__";
const PROMPT_TEMPLATE_DEFAULT_MIN_PROMPTS = 20;
const PROMPT_TEMPLATE_MAX_MIN_PROMPTS = 100000;
const PROMPT_TEMPLATE_REVIEW_MARKS_LIMIT = 50;
const PROMPT_DECOMPOSITION_TASK_TYPE = "edit";
const PROMPT_DECOMPOSITION_SAVED_LIMIT = 20;
const PROMPT_TEMPLATE_SIMILARITY_BADGE_CLASSES = {
  "高度相似": "success",
  "较相似": "identity",
  "中等相似": "warn",
  "差异较大": "danger",
};
const PROMPT_TEMPLATE_SLOT_LABELS = {
  task_intent: "任务意图",
  preserve: "保持口径",
  subject: "主体人物",
  body_part: "身体部分",
  pose_action: "动作姿势",
  adult_theme: "成人主题",
  clothing: "服饰配件",
  scene: "场景",
  composition: "镜头构图",
  style_quality: "风格质量",
  expression: "表情情绪",
};

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

function fmtSigned(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric) || numeric === 0) return fmt(numeric);
  return `${numeric > 0 ? "+" : "-"}${fmt(Math.abs(numeric))}`;
}

function fmtPercent(value) {
  return `${fmtAmount(value)}%`;
}

function fmtPeriod(days) {
  const numeric = Number(days);
  if (numeric === 0) return "全量";
  if (!Number.isFinite(numeric)) return "近周期";
  return `近 ${fmt(numeric)} 天`;
}

function selectNumber(selector, fallback) {
  const value = $(selector)?.value;
  if (value === undefined || value === null || value === "") return fallback;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function toDateInputValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDateInputValue(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  if (!match) return null;
  const parsed = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function inclusiveDateDays(startValue, endValue) {
  const start = parseDateInputValue(startValue);
  const end = parseDateInputValue(endValue);
  if (!start || !end || start > end) return null;
  return Math.round((end - start) / 86400000) + 1;
}

function setUserDateRangeForDays(days = 30) {
  const normalizedDays = Math.max(1, Number(days) || 30);
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - normalizedDays + 1);
  state.userDateRange = {
    start: toDateInputValue(start),
    end: toDateInputValue(end),
  };
}

function ensureUserDateRange() {
  if (!state.userDateRange.start || !state.userDateRange.end) {
    setUserDateRangeForDays(state.tabDays.users || 30);
  }
  const startInput = $("#userStartDateInput");
  const endInput = $("#userEndDateInput");
  if (startInput && !startInput.value) startInput.value = state.userDateRange.start;
  if (endInput && !endInput.value) endInput.value = state.userDateRange.end;
  return state.userDateRange;
}

function currentUserDateRange() {
  ensureUserDateRange();
  const start = $("#userStartDateInput")?.value || state.userDateRange.start;
  const end = $("#userEndDateInput")?.value || state.userDateRange.end;
  const days = inclusiveDateDays(start, end) || Number(state.tabDays.users || 30);
  state.userDateRange = { start, end };
  state.tabDays.users = days;
  return { start, end, days };
}

function userPeriodParams() {
  const range = currentUserDateRange();
  return {
    days: range.days,
    start_date: range.start,
    end_date: range.end,
  };
}

function currentDays() {
  if (state.activeTab === "users") {
    return currentUserDateRange().days;
  }
  return Number(state.tabDays[state.activeTab] ?? 30);
}

function setCurrentDays(days) {
  if (state.activeTab === "users") {
    setUserDateRangeForDays(days);
    return;
  }
  state.tabDays[state.activeTab] = Number.isFinite(Number(days)) ? Number(days) : 30;
}

function syncDaysControl() {
  const select = $("#daysSelect");
  const daysControl = $("#daysSelectControl");
  const userDateRangeControls = $("#userDateRangeControls");
  if (!select) return;
  if (state.activeTab === "users") {
    ensureUserDateRange();
    if (daysControl) daysControl.classList.add("hidden");
    if (userDateRangeControls) userDateRangeControls.classList.remove("hidden");
    return;
  }
  if (daysControl) daysControl.classList.remove("hidden");
  if (userDateRangeControls) userDateRangeControls.classList.add("hidden");
  const lockedAllTimeTabs = new Set(["prompt-slim", "prompt-vectors", "prompt-tokens", "prompt-decomposition", "templates"]);
  const locked = lockedAllTimeTabs.has(state.activeTab);
  select.disabled = locked;
  select.value = String(locked ? 0 : currentDays());
}

function renderLastUpdated() {
  $("#lastUpdated").textContent = state.tabUpdatedAt[state.activeTab]
    ? `更新于 ${state.tabUpdatedAt[state.activeTab]}`
    : "";
}

function markTabLoaded(tab) {
  state.loadedTabs[tab] = true;
  state.tabUpdatedAt[tab] = new Date().toLocaleString("zh-CN", { hour12: false });
  if (state.activeTab === tab) {
    renderLastUpdated();
  }
  document.body.dataset.loaded = "true";
}

function markTabStale(tab) {
  state.loadedTabs[tab] = false;
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

const chartPalette = ["#2563eb", "#0f766e", "#b7791f", "#7c3aed", "#dc2626", "#0891b2", "#16a34a", "#ea580c", "#9333ea", "#475569"];
const tabChartIds = {
  users: ["userCoreTrendChart", "userTrustCompositionChart", "userConversionFunnelChart", "userDailyActivityChart", "userRechargeRateChart"],
  "credit-flow": ["creditFlowTrendChart", "creditDailyCategoryChart", "creditIncomeCategoryChart", "creditExpenseCategoryChart", "creditCompositionIdentityChart", "creditCompositionGroupChart", "creditCompositionChannelChart", "creditCompositionPayerChart", "creditRiskScatterChart"],
  finance: ["financeTrendChart", "financeStatusChart", "financeHourlyChart", "financeChannelChart", "financePlanChart"],
  generation: ["generationTrendChart", "generationQualityFunnelChart", "generationSourceMixChart", "generationWorkerChart", "generationTypeBubbleChart", "generationCompareChart"],
};

function numeric(value) {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function shortNumber(value) {
  const parsed = numeric(value);
  if (Math.abs(parsed) >= 1000000) return `${Math.round(parsed / 100000) / 10}M`;
  if (Math.abs(parsed) >= 1000) return `${Math.round(parsed / 100) / 10}k`;
  return `${parsed}`;
}

function cumulative(values) {
  let total = 0;
  return values.map((value) => {
    total += numeric(value);
    return Math.round(total * 100) / 100;
  });
}

function dateLabel(value) {
  const text = String(value || "");
  return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(5) : text || "-";
}

function defaultCompareDates(rows = []) {
  const dates = rows.map((row) => row.day || row.date).filter(Boolean).slice(-2);
  return dates.length ? dates : [new Date().toISOString().slice(0, 10)];
}

function ensureCompareInput(selector, rows = []) {
  const input = $(selector);
  if (input && !input.value) {
    input.value = defaultCompareDates(rows).join(",");
  }
}

function getCompareDates(selector, rows = []) {
  ensureCompareInput(selector, rows);
  const value = $(selector)?.value || "";
  return value.split(",").map((item) => item.trim()).filter(Boolean).slice(0, 3);
}

function chartEmptyOption(message = "暂无数据") {
  return {
    title: {
      text: message,
      left: "center",
      top: "middle",
      textStyle: { color: "#687083", fontSize: 14, fontWeight: 600 },
    },
  };
}

function renderChart(id, option) {
  const element = document.getElementById(id);
  if (!element) return;
  if (!window.echarts) {
    element.innerHTML = '<div class="empty">图表资源加载失败</div>';
    return;
  }
  if (!state.charts[id]) {
    state.charts[id] = window.echarts.init(element);
  }
  state.charts[id].setOption(option || chartEmptyOption(), true);
}

function disposeChartsForTab(tab) {
  (tabChartIds[tab] || []).forEach((id) => {
    if (state.charts[id]) {
      state.charts[id].dispose();
      delete state.charts[id];
    }
  });
}

function resizeCharts() {
  Object.values(state.charts).forEach((chart) => chart.resize());
}

function baseTooltip() {
  return {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    valueFormatter: (value) => fmtAmount(value),
  };
}

function buildLineBarOption({ dates, series, yAxis = [{ type: "value" }], legendBottom = true, legendSelected = null }) {
  if (!dates?.length || !series?.length) return chartEmptyOption();
  return {
    color: chartPalette,
    tooltip: baseTooltip(),
    legend: {
      type: "scroll",
      bottom: legendBottom ? 0 : undefined,
      top: legendBottom ? undefined : 0,
      selected: legendSelected || undefined,
    },
    grid: { left: 42, right: Array.isArray(yAxis) && yAxis.length > 1 ? 72 : 34, top: legendBottom ? 24 : 44, bottom: legendBottom ? 48 : 32, containLabel: true },
    xAxis: { type: "category", data: dates.map(dateLabel), axisTick: { alignWithLabel: true } },
    yAxis,
    series,
  };
}

function buildStackedBarOption({ dates, rows, categories, valueKey = "value", titleSuffix = "" }) {
  if (!dates?.length || !categories?.length) return chartEmptyOption();
  const series = categories.map((category) => ({
    name: `${category}${titleSuffix}`,
    type: "bar",
    stack: "total",
    emphasis: { focus: "series" },
    data: dates.map((day) => numeric(rows.find((row) => (row.day || row.date) === day && (row.category || row.label) === category)?.[valueKey])),
    barMaxWidth: 26,
  }));
  return buildLineBarOption({ dates, series });
}

function buildDonutOption(rows = [], valueKey = "count", labelKey = "label") {
  const data = rows
    .map((row) => ({ name: row[labelKey] || row.category || "-", value: numeric(row[valueKey]) }))
    .filter((item) => item.value > 0);
  if (!data.length) return chartEmptyOption();
  return {
    color: chartPalette,
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { type: "scroll", orient: "vertical", left: 0, top: "middle" },
    series: [{
      type: "pie",
      radius: ["42%", "68%"],
      center: ["62%", "50%"],
      data,
      label: { show: false },
      labelLine: { show: false },
      emphasis: { scale: true },
    }],
  };
}

function buildHorizontalBarOption(rows = [], valueKey = "count", labelKey = "label") {
  const data = rows
    .map((row) => ({ label: row[labelKey] || row.category || "-", value: numeric(row[valueKey]) }))
    .filter((item) => item.value > 0)
    .slice(0, 12)
    .reverse();
  if (!data.length) return chartEmptyOption();
  return {
    color: [chartPalette[1]],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 96, right: 28, top: 16, bottom: 22 },
    xAxis: { type: "value", axisLabel: { formatter: shortNumber }, splitLine: { lineStyle: { type: "dashed" } } },
    yAxis: { type: "category", data: data.map((item) => item.label), axisLabel: { width: 86, overflow: "truncate" } },
    series: [{ type: "bar", data: data.map((item) => item.value), barMaxWidth: 16, itemStyle: { borderRadius: [0, 5, 5, 0] } }],
  };
}

function buildFunnelOption(rows = [], valueKey = "count", labelKey = "label") {
  const data = rows.map((row) => ({ name: row[labelKey] || "-", value: numeric(row[valueKey]) })).filter((item) => item.value > 0);
  if (!data.length) return chartEmptyOption();
  return {
    color: chartPalette,
    tooltip: { trigger: "item", formatter: "{b}: {c}" },
    series: [{
      type: "funnel",
      left: "8%",
      top: 18,
      bottom: 18,
      width: "84%",
      minSize: "10%",
      maxSize: "100%",
      sort: "none",
      gap: 2,
      label: { formatter: "{b}: {c}" },
      data,
    }],
  };
}

function buildHourlyOption(rows = [], { dateKey = "date", metric = "generations", name = "分时" } = {}) {
  const hours = Array.from({ length: 24 }, (_, hour) => hour);
  const dates = Array.from(new Set(rows.map((row) => row[dateKey]).filter(Boolean)));
  if (dates.length) {
    return buildLineBarOption({
      dates: hours.map((hour) => `${String(hour).padStart(2, "0")}时`),
      series: dates.map((date) => ({
        name: dateLabel(date),
        type: "bar",
        data: hours.map((hour) => numeric(rows.find((row) => row[dateKey] === date && numeric(row.hour) === hour)?.[metric])),
        barMaxWidth: 18,
      })),
    });
  }
  return buildLineBarOption({
    dates: hours.map((hour) => `${String(hour).padStart(2, "0")}时`),
    series: [{
      name,
      type: "bar",
      data: hours.map((hour) => numeric(rows.find((row) => numeric(row.hour) === hour)?.[metric])),
      barMaxWidth: 20,
    }],
  });
}

function promptVectorResumeNote() {
  const resume = state.promptVectors?.resume || state.promptVectorResume?.resume || {};
  const summary = state.promptVectors?.summary || {};
  if (state.promptVectorResumeLoading) return "正在启动";
  if (resume.running) {
    const started = resume.started_at ? ` · ${fmtDate(resume.started_at)}` : "";
    return resume.pid ? `运行中 · PID ${fmt(resume.pid)}${started}` : "已有向量化在运行";
  }
  if (state.promptVectorResume?.status === "started") {
    return `已启动 · PID ${fmt(state.promptVectorResume.pid)}`;
  }
  if (resume.last_exit) {
    return `上次退出 ${fmtDate(resume.last_exit.finished_at)} · code ${fmt(resume.last_exit.returncode)}`;
  }
  const coverage = summary.embedding_coverage === undefined ? "" : `覆盖 ${fmtAmount(summary.embedding_coverage)}%`;
  return coverage ? `${coverage} · 可续跑缺失向量` : "可续跑缺失向量";
}

function renderPromptVectorResumeStatus() {
  const button = $("#promptVectorResumeButton");
  const status = $("#promptVectorResumeStatus");
  if (!button || !status) return;
  const resume = state.promptVectors?.resume || state.promptVectorResume?.resume || {};
  const running = Boolean(resume.running);
  button.disabled = state.promptVectorResumeLoading || running;
  button.textContent = state.promptVectorResumeLoading ? "启动中" : running ? "运行中" : "续跑向量化";
  status.textContent = promptVectorResumeNote();
}

function renderSource() {
  const source = state.overview?.source;
  if (!source) return;
  const media = source.media_url_enabled ? "媒体 URL 已启用" : "媒体 URL 未配置";
  $("#sourceLine").textContent = `${source.database_url || "shadow database"} · ${source.media_bucket} · ${media}`;
  $("#sidebarStatus").textContent = `${state.overview?.metrics?.total_history ? fmt(state.overview.metrics.total_history) : "-"} 条 history · ${media}`;
}

function setError(error) {
  const banner = $("#errorBanner");
  if (!banner) return;
  if (!error) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  banner.classList.remove("hidden");
  banner.textContent = error.message || String(error);
}

async function copyTextToClipboard(text) {
  const value = String(text || "");
  if (!value) return;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function downloadTextFile(filename, content, type = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function setLoading(isLoading) {
  const button = $("#refreshButton");
  if (!button) return;
  button.disabled = isLoading;
  button.textContent = isLoading ? "刷新中" : "刷新";
}

function renderUsers() {
  const summary = state.users?.summary || {};
  const visuals = state.users?.visualizations || {};
  const period = fmtPeriod(state.users?.days);
  const fixedMetrics = visuals.metrics || [];
  $("#userSummary").innerHTML = fixedMetrics.length ? fixedMetrics.map((item) => {
    const delta = item.delta || {};
    const deltaText = delta.value === null || delta.value === undefined
      ? "暂无上一快照"
      : `较上一快照 ${fmtSigned(delta.value)}${delta.percent === null || delta.percent === undefined ? "" : ` / ${fmtSigned(delta.percent)}%`}`;
    return metric(item.label, fmt(item.value), `占比 ${fmtPercent(item.share_percent)} · ${deltaText}`);
  }).join("") : [
    metric("总用户数", fmt(summary.total_users), `${period}新增 ${fmt(summary.new_users)}`),
    metric("周期活跃用户数", fmt(summary.active_users), "last_activity 或生成记录"),
    metric("从未活跃用户数", fmt(summary.never_active_users), "无活跃与生成记录"),
    metric("沉睡用户数", fmt(summary.dormant_users), "曾经活跃且周期未活跃"),
    metric("入宗门用户数", fmt(summary.channel_members), "is_channel_member"),
    metric("生成用户数", fmt(summary.generation_users), "generation_count > 0"),
    metric("真实付费用户数", fmt(summary.paying_users), "RMB / TON / Stars"),
    metric("低信任免费层用户数", fmt(summary.low_trust_free_tier_users), "签到高且未付费未豁免"),
    metric("豁免低信任用户数", fmt(summary.low_trust_exempt_users), "高质量邀请者豁免"),
    metric("投稿封禁用户数", fmt(summary.submission_banned_users), "is_submission_banned"),
  ].join("");
  $("#userRechargeRates").innerHTML = [
    metric("总用户充值率", fmtPercent(summary.recharge_rate_total_users), `充值 ${fmt(summary.paying_users)} / 总 ${fmt(summary.total_users)}`),
    metric("入宗门充值率", fmtPercent(summary.recharge_rate_channel_members), `充值 ${fmt(summary.paying_channel_members)} / 入宗门 ${fmt(summary.channel_members)}`),
    metric("生成用户充值率", fmtPercent(summary.recharge_rate_generation_users), `充值 ${fmt(summary.paying_generation_users)} / 生成 ${fmt(summary.generation_users)}`),
    metric("活跃用户充值率", fmtPercent(summary.recharge_rate_active_users), `充值 ${fmt(summary.active_paying_users)} / 活跃 ${fmt(summary.active_users)}`),
    metric("平均邀请充值率", fmtPercent(summary.avg_inviter_invitee_recharge_rate), `样本邀请人 ${fmt(summary.inviter_recharge_rate_sample_size)}`),
  ].join("");

  renderUserVisualCharts();
  renderUserGroups();
  renderUserProfileList();
}

function renderUserVisualCharts() {
  const visuals = state.users?.visualizations || {};
  const trend = visuals.trend || [];
  const snapshotRows = trend.filter((row) => row.total_users !== undefined && row.total_users !== null);
  const snapshotDates = snapshotRows.map((row) => row.day);
  if (snapshotRows.length) {
    renderChart("userCoreTrendChart", buildLineBarOption({
      dates: snapshotDates,
      series: [
        { name: "总用户", type: "line", yAxisIndex: 1, smooth: true, showSymbol: true, data: snapshotRows.map((row) => numeric(row.total_users)) },
        { name: "周期活跃", type: "line", smooth: true, showSymbol: true, data: snapshotRows.map((row) => numeric(row.period_active_users)) },
        { name: "沉睡用户", type: "line", yAxisIndex: 1, smooth: true, showSymbol: true, data: snapshotRows.map((row) => numeric(row.dormant_users)) },
        { name: "从未活跃", type: "line", smooth: true, showSymbol: true, data: snapshotRows.map((row) => numeric(row.never_active_users)) },
        { name: "入宗门", type: "line", smooth: true, showSymbol: true, data: snapshotRows.map((row) => numeric(row.channel_members)) },
        { name: "生成用户", type: "line", smooth: true, showSymbol: true, data: snapshotRows.map((row) => numeric(row.generation_users)) },
        { name: "真实付费", type: "line", smooth: true, showSymbol: true, data: snapshotRows.map((row) => numeric(row.real_payers)) },
        { name: "低信任", type: "line", smooth: true, showSymbol: true, data: snapshotRows.map((row) => numeric(row.low_trust_free_tier_users)) },
        { name: "豁免低信任", type: "line", smooth: true, showSymbol: true, data: snapshotRows.map((row) => numeric(row.low_trust_exempt_users)) },
      ],
      yAxis: [
        { type: "value", name: "人群指标", scale: true, axisLabel: { formatter: shortNumber } },
        { type: "value", name: "总量", scale: true, axisLabel: { formatter: shortNumber }, splitLine: { show: false } },
      ],
      legendSelected: { "总用户": false, "从未活跃": false, "低信任": false, "豁免低信任": false },
    }));
  } else {
    renderChart("userCoreTrendChart", chartEmptyOption("暂无快照趋势"));
  }

  renderChart("userTrustCompositionChart", buildDonutOption(visuals.trust_composition || []));
  renderChart("userConversionFunnelChart", buildFunnelOption(visuals.conversion_funnel || []));

  const dailyRows = trend.filter((row) => row.new_users !== undefined || row.active_users !== undefined || row.checkins !== undefined);
  renderChart("userDailyActivityChart", dailyRows.length ? buildLineBarOption({
    dates: dailyRows.map((row) => row.day),
    series: [
      { name: "新增用户", type: "bar", stack: "new", data: dailyRows.map((row) => numeric(row.new_users)), barMaxWidth: 22 },
      { name: "新增入宗门", type: "bar", stack: "new", data: dailyRows.map((row) => numeric(row.new_channel_members)), barMaxWidth: 22 },
      { name: "新增生成用户", type: "bar", stack: "new", data: dailyRows.map((row) => numeric(row.new_generation_users)), barMaxWidth: 22 },
      { name: "日生成活跃", type: "line", smooth: true, data: dailyRows.map((row) => numeric(row.active_users)) },
      { name: "签到数", type: "line", smooth: true, data: dailyRows.map((row) => numeric(row.checkins)) },
    ],
  }) : chartEmptyOption());

  renderChart("userRechargeRateChart", buildHorizontalBarOption(visuals.recharge_rates || [], "rate", "label"));
}

function renderUserGroups() {
  const payload = state.userGroups || {};
  const rows = payload.rows || [];
  const dimensionLabel = payload.dimension?.label || "人群";
  const filters = payload.filters || {};
  const segmentLabel = $("#userProfileSegmentSelect")?.selectedOptions?.[0]?.textContent || "全部用户";
  const dateLabel = filters.start_date && filters.end_date ? `${filters.start_date} 至 ${filters.end_date}` : fmtPeriod(payload.days);
  const searchLabel = filters.search ? ` · 搜索 ${filters.search}` : "";
  $("#userGroupStatus").textContent = `${dimensionLabel} · ${fmt(rows.length)} 个分桶 · 来自下方列表筛选范围（${dateLabel} · ${segmentLabel}${searchLabel}）`;
  $("#userGroupRows").innerHTML = tableRows(rows, (row) => {
    const isSelected = state.selectedUserGroup
      && state.selectedUserGroup.dimension === (payload.dimension?.key || "")
      && state.selectedUserGroup.group_key === row.group_key;
    return `
      <tr class="clickable-row user-group-row ${isSelected ? "selected" : ""}" data-group-key="${escapeHtml(row.group_key)}" data-group-label="${escapeHtml(row.group_label)}" tabindex="0">
        <td>
          <strong>${escapeHtml(row.group_label || row.group_key || "未分组")}</strong>
          <div class="muted small">${escapeHtml(dimensionLabel)} · ${escapeHtml(row.group_key || "-")}</div>
        </td>
        <td>
          <strong>${fmt(row.users)}</strong>
          <div class="muted small">占比 ${fmtPercent(row.share_percent)}</div>
        </td>
        <td>
          <strong>${fmt(row.active_users)} / ${fmt(row.channel_members)}</strong>
          <div class="muted small">活跃 ${fmtPercent(row.active_rate)} · 入宗门 ${fmtPercent(row.channel_member_rate)}</div>
        </td>
        <td>
          <strong>${fmtAmount(row.recharge_usdt, " USDT")}</strong>
          <div class="muted small">付费 ${fmt(row.real_payers)} · 付费率 ${fmtPercent(row.paying_rate)} · ${fmt(row.real_success_orders)} 单</div>
        </td>
        <td>
          <strong>${fmt(row.generation_count)} / ${fmt(row.period_checkins)}</strong>
          <div class="muted small">周期生成 ${fmt(row.period_generations)} · 签到用户 ${fmt(row.checkin_users)}</div>
        </td>
        <td>
          <strong>${fmtSigned(row.credit_net_change)}</strong>
          <div class="muted small">收入 ${fmt(row.credit_income)} / 支出 ${fmt(row.credit_expense)}</div>
        </td>
        <td>
          <strong>邀 ${fmt(row.referral_relations)} · 投稿 ${fmt(row.gallery_posts)}</strong>
          <div class="muted small">受邀充值 ${fmtPercent(row.invitee_recharge_rate)} · 信号 ${fmt(row.gallery_signal)}</div>
        </td>
        <td>
          <strong>解锁 ${fmt(row.prompt_unlocks)} · 粉 ${fmt(row.followers_count)}</strong>
          <div class="muted small">买 ${fmt(row.prompt_unlocks_bought)} / 卖 ${fmt(row.prompt_unlocks_sold)} · 关 ${fmt(row.following_count)}</div>
        </td>
      </tr>
    `;
  });
  document.querySelectorAll(".user-group-row").forEach((row) => {
    row.addEventListener("click", () => selectUserGroup(row.dataset.groupKey || "", row.dataset.groupLabel || ""));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectUserGroup(row.dataset.groupKey || "", row.dataset.groupLabel || "");
      }
    });
  });
}

function currentUserGroupDimensionMeta() {
  return state.userGroups?.dimension || {
    key: $("#userGroupDimensionSelect")?.value || "payer",
    label: $("#userGroupDimensionSelect")?.selectedOptions?.[0]?.textContent || "人群",
  };
}

function selectUserGroup(groupKey, groupLabel) {
  const dimension = currentUserGroupDimensionMeta();
  state.selectedUserGroup = {
    dimension: dimension.key,
    dimension_label: dimension.label,
    group_key: groupKey,
    group_label: groupLabel || groupKey,
  };
  state.userProfilePage = 1;
  markTabStale("users");
  if (state.activeTab === "users") {
    loadCurrentTab({ force: true });
  }
}

function clearUserGroupSelection({ reload = true } = {}) {
  state.selectedUserGroup = null;
  state.userProfilePage = 1;
  if (reload) {
    markTabStale("users");
    if (state.activeTab === "users") {
      loadCurrentTab({ force: true });
    }
  }
}

function renderUserProfileList() {
  const payload = state.userProfiles || {};
  const rows = payload.items || [];
  const pagination = payload.pagination || { page: 1, size: 20, total: 0 };
  const page = numeric(pagination.page) || 1;
  const size = numeric(pagination.size) || 20;
  const total = numeric(pagination.total);
  const start = total ? (page - 1) * size + 1 : 0;
  const end = Math.min(total, page * size);
  const selection = state.selectedUserGroup;
  $("#userGroupSelectionLabel").textContent = selection
    ? `${selection.dimension_label}: ${selection.group_label}`
    : "全部人群";
  $("#userGroupClearButton").disabled = !selection;
  $("#userProfilePagination").textContent = total ? `${fmt(start)}-${fmt(end)} / ${fmt(total)}` : "暂无用户";
  $("#userProfilePrevButton").disabled = page <= 1;
  $("#userProfileNextButton").disabled = page * size >= total;
  $("#userProfileRows").innerHTML = tableRows(rows, (row) => {
    const userId = Number(row.user_id || row.id || 0);
    return `
    <tr class="clickable-row user-profile-row" data-user-id="${userId}" tabindex="0">
      <td>${renderUserIdentity(row)}</td>
      <td>
        <div class="pill-list">
          ${renderUserBadge(row)}
          ${renderUserBadge(row, "user_group")}
          ${row.is_channel_member ? '<span class="status-badge success">入宗门</span>' : '<span class="status-badge neutral">未入宗门</span>'}
          ${Number(row.real_success_orders || 0) > 0 ? '<span class="status-badge success">真实付费</span>' : ""}
        </div>
        <div class="muted small">注册 ${fmtDate(row.created_at)}</div>
      </td>
      <td>
        <strong>${fmt(row.generation_count)}</strong> 次
        <div class="muted small">周期 ${fmt(row.period_generations)} · 活跃天 ${fmt(row.active_generation_days)} · 签到 ${fmt(row.checkin_count)}</div>
      </td>
      <td>
        <strong>${fmt(row.credits)}</strong>
        <div class="muted small">收入 ${fmt(row.credit_income)} / 支出 ${fmt(row.credit_expense)} / 净 ${fmtSigned(row.credit_net_change)}</div>
      </td>
      <td>
        <strong>${fmtAmount(row.recharge_usdt, " USDT")}</strong>
        <div class="muted small">${fmt(row.real_success_orders)} 单 · 最近 ${fmtDate(row.last_recharge_at)}</div>
      </td>
      <td>
        <strong>邀 ${fmt(row.referral_relations)} · 投稿 ${fmt(row.gallery_posts)}</strong>
        <div class="muted small">受邀生成 ${fmt(row.invitee_generation_users)} · 投稿信号 ${fmt(row.gallery_signal)}</div>
      </td>
      <td>
        <strong>粉 ${fmt(row.followers_count)} · 关 ${fmt(row.following_count)}</strong>
        <div class="muted small">买 ${fmt(row.prompt_unlocks_bought)} / 卖 ${fmt(row.prompt_unlocks_sold)}</div>
      </td>
      <td>
        <button class="table-action" type="button" data-open-user-profile="${userId}">画像</button>
      </td>
    </tr>
  `;
  });
  document.querySelectorAll("[data-open-user-profile]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openUserProfile(Number(button.dataset.openUserProfile));
    });
  });
  document.querySelectorAll(".user-profile-row").forEach((row) => {
    row.addEventListener("click", () => openUserProfile(Number(row.dataset.userId)));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openUserProfile(Number(row.dataset.userId));
      }
    });
  });
}

function renderCreditFlow() {
  const summary = state.creditFlow?.summary || {};
  const health = state.creditFlow?.health || {};
  $("#creditFlowSummary").innerHTML = [
    metric("收支净额", fmtSigned(summary.net_change), `收入 ${fmt(summary.gross_income)} / 支出 ${fmt(summary.gross_expense)}`),
    metric("支出覆盖", fmtPercent(health.expense_coverage_ratio), `日均支出 ${fmtAmount(summary.avg_daily_expense)}`),
    metric("付费充值占比", fmtPercent(health.paid_recharge_ratio), `充值 ${fmt(summary.paid_recharge_income)}`),
    metric("签到发放", fmt(summary.checkin_income), `免费 ${fmt(summary.free_checkin_income)} / 身份加成 ${fmt(summary.identity_checkin_bonus_income)}`),
    metric("非付费发放", fmtPercent(health.non_paid_grant_ratio), `签到/邀请等 ${fmt(summary.non_paid_grant_income)}`),
    metric("退款率", fmtPercent(health.refund_to_generation_ratio), `退款 ${fmt(summary.refund_income)} / 生成 ${fmt(summary.generation_expense)}`),
    metric("余额可消耗", fmtAmount(summary.balance_burn_days, " 天"), `当前余额 ${fmt(summary.current_total_credits)}`),
    metric("收入集中度", fmtPercent(health.top_income_user_share), `签到压力 ${fmtPercent(health.checkin_pressure_ratio)}`),
    metric("内部转移", fmt(summary.internal_transfer_income), `Gallery 支出 ${fmt(summary.internal_transfer_expense)}`),
  ].join("");

  renderCreditFlowCharts();
  renderHealthFlags(health.flags || []);
  renderCreditRiskUsers(state.creditFlow?.risk_users || []);
}

function renderCreditFlowCharts() {
  const daily = state.creditFlow?.daily || [];
  const dates = daily.map((row) => row.day);
  const income = daily.map((row) => numeric(row.income));
  const expense = daily.map((row) => numeric(row.expense));
  const net = daily.map((row) => numeric(row.net_change));
  const mode = state.creditFlowMode;
  const dailySeries = [
    { name: mode === "cumulative" ? "累计收入" : "收入", type: "bar", data: mode === "cumulative" ? cumulative(income) : income, barMaxWidth: 22 },
    { name: mode === "cumulative" ? "累计支出" : "支出", type: "bar", data: mode === "cumulative" ? cumulative(expense) : expense, barMaxWidth: 22 },
    { name: mode === "cumulative" ? "累计净变化" : "净变化", type: "line", smooth: true, data: mode === "cumulative" ? cumulative(net) : net },
  ];
  renderChart("creditFlowTrendChart", buildLineBarOption({ dates, series: dailySeries }));

  const dailyCategories = state.creditFlow?.daily_categories || [];
  const categoryRows = dailyCategories.map((row) => ({
    ...row,
    value: row.direction === "expense" ? -numeric(row.expense) : numeric(row.income),
  }));
  const categories = Array.from(new Set(categoryRows.map((row) => row.category)));
  renderChart("creditDailyCategoryChart", buildStackedBarOption({ dates, rows: categoryRows, categories }));

  const categoriesTotal = state.creditFlow?.categories || [];
  const incomeRows = categoriesTotal.filter((row) => row.direction === "income" && numeric(row.income) > 0);
  const expenseRows = categoriesTotal.filter((row) => row.direction === "expense" && numeric(row.expense) > 0);
  renderChart("creditIncomeCategoryChart", buildDonutOption(incomeRows, "income", "category"));
  renderChart("creditExpenseCategoryChart", buildDonutOption(expenseRows, "expense", "category"));

  const composition = state.creditFlow?.composition || {};
  renderChart("creditCompositionIdentityChart", buildHorizontalBarOption(composition.identity || [], "income"));
  renderChart("creditCompositionGroupChart", buildHorizontalBarOption(composition.user_group || [], "income"));
  renderChart("creditCompositionChannelChart", buildDonutOption(composition.channel_member || [], "income"));
  renderChart("creditCompositionPayerChart", buildDonutOption(composition.payer || [], "income"));

  const riskUsers = state.creditFlow?.risk_users || [];
  const scatterData = riskUsers.map((row) => [
    numeric(row.income),
    numeric(row.expense),
    numeric(row.current_balance),
    numeric(row.risk_score),
    row.full_name || row.username || `ID ${row.id}`,
  ]);
  renderChart("creditRiskScatterChart", scatterData.length ? {
    color: ["#b42318"],
    tooltip: {
      trigger: "item",
      formatter: (params) => {
        const [incomeValue, expenseValue, balance, riskScore, name] = params.value;
        return `${escapeHtml(name)}<br/>收入 ${fmt(incomeValue)}<br/>支出 ${fmt(expenseValue)}<br/>余额 ${fmt(balance)}<br/>风险分 ${fmt(riskScore)}`;
      },
    },
    grid: { left: 52, right: 36, top: 24, bottom: 36, containLabel: true },
    xAxis: { type: "value", name: "收入", axisLabel: { formatter: shortNumber }, splitLine: { lineStyle: { type: "dashed" } } },
    yAxis: { type: "value", name: "支出", axisLabel: { formatter: shortNumber }, splitLine: { lineStyle: { type: "dashed" } } },
    series: [{
      name: "风险用户",
      type: "scatter",
      data: scatterData,
      symbolSize: (value) => Math.max(8, Math.min(42, Math.sqrt(numeric(value[2])) * 1.2 + numeric(value[3]) / 8)),
    }],
  } : chartEmptyOption("暂无风险用户"));
}

function renderDistribution(selector, rows = []) {
  if (!rows.length) {
    $(selector).innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  const total = rows.reduce((sum, row) => sum + Number(row.count || 0), 0);
  const max = Math.max(1, ...rows.map((row) => Number(row.count || 0)));
  $(selector).innerHTML = rows
    .map((row) => {
      const count = Number(row.count || 0);
      const width = Math.max(2, Math.round((count / max) * 100));
      const share = total ? `${Math.round((count / total) * 1000) / 10}%` : "0%";
      return `
        <div class="distribution-row">
          <div class="distribution-meta">
            <span>${escapeHtml(row.label)}</span>
            <strong>${fmt(count)}</strong>
          </div>
          <div class="distribution-track">
            <div class="distribution-fill" style="width:${width}%"></div>
          </div>
          <div class="distribution-share">${share}</div>
        </div>
      `;
    })
    .join("");
}

function tableRows(rows = [], renderer) {
  const safeRows = Array.isArray(rows) ? rows : [];
  if (!safeRows.length) {
    return '<tr><td colspan="20"><div class="empty compact">暂无数据</div></td></tr>';
  }
  return safeRows.map(renderer).join("");
}

function renderHealthFlags(flags = [], selector = "#creditHealthFlags") {
  $(selector).innerHTML = flags.length
    ? flags.map((flag) => `<span class="pill ${flag.includes("未触发") ? "gray" : "amber"}">${escapeHtml(flag)}</span>`).join("")
    : '<span class="muted">暂无风险标记</span>';
}

function renderUserIdentity(row) {
  const userId = row.user_id || row.id;
  return `
    <div class="user-cell">
      <strong>${escapeHtml(row.full_name || "未知用户")}</strong>
      <span>ID ${fmt(userId)} · @${escapeHtml(row.username || "n/a")}</span>
      ${row.is_submission_banned ? '<span class="status-badge danger">投稿封禁</span>' : ""}
      ${row.is_low_trust_free_tier ? '<span class="status-badge warn">低信任免费层</span>' : ""}
    </div>
  `;
}

function renderUserBadge(row, key = "current_identity") {
  const value = row[key] || (key === "user_group" ? "凡人" : "外门弟子");
  const badgeClass = key === "user_group" ? "group" : "identity";
  return `<span class="status-badge ${badgeClass}">${escapeHtml(value)}</span>`;
}

function renderProfileMetric(label, value, note = "") {
  return `
    <div class="profile-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${value}</strong>
      ${note ? `<small>${escapeHtml(note)}</small>` : ""}
    </div>
  `;
}

function renderProfileMetricGrid(items = []) {
  return `<div class="profile-metric-grid">${items.map((item) => renderProfileMetric(item.label, item.value, item.note)).join("")}</div>`;
}

function renderProfileSection(title, content) {
  return `
    <section class="profile-section">
      <h4>${escapeHtml(title)}</h4>
      ${content}
    </section>
  `;
}

function renderCompactList(rows = [], renderer) {
  if (!rows.length) return '<div class="empty compact">暂无数据</div>';
  return `<div class="compact-list">${rows.map(renderer).join("")}</div>`;
}

function renderCompactItem(title, meta = "", value = "") {
  return `
    <div class="compact-item">
      <div>
        <strong>${escapeHtml(title || "-")}</strong>
        ${meta ? `<span>${escapeHtml(meta)}</span>` : ""}
      </div>
      ${value ? `<em>${value}</em>` : ""}
    </div>
  `;
}

function openUserProfileDrawer() {
  $("#userProfileDrawerBackdrop").classList.remove("hidden");
  $("#userProfileDrawer").classList.add("open");
  $("#userProfileDrawer").setAttribute("aria-hidden", "false");
  document.body.classList.add("profile-drawer-open");
}

function closeUserProfileDrawer() {
  $("#userProfileDrawerBackdrop").classList.add("hidden");
  $("#userProfileDrawer").classList.remove("open");
  $("#userProfileDrawer").setAttribute("aria-hidden", "true");
  document.body.classList.remove("profile-drawer-open");
}

async function openUserProfile(userId) {
  if (!userId) return;
  openUserProfileDrawer();
  $("#userProfileDrawerTitle").textContent = `ID ${fmt(userId)}`;
  $("#userProfileDrawerContent").innerHTML = '<div class="empty">加载中</div>';
  try {
    const payload = await fetchJson(`/api/user-analytics/users/${userId}`, { days: userPeriodParams().days });
    state.userProfileDetail = payload;
    renderUserProfileDetail(payload);
  } catch (error) {
    $("#userProfileDrawerContent").innerHTML = `<div class="error-panel">${escapeHtml(error.message || String(error))}</div>`;
  }
}

function renderUserProfileDetail(payload = {}) {
  const profile = payload.profile || {};
  const displayName = profile.full_name || profile.username || `ID ${profile.id}`;
  $("#userProfileDrawerTitle").textContent = displayName;

  const credit = payload.credit_flow || {};
  const recharge = payload.recharge || {};
  const invitation = payload.invitation || {};
  const generation = payload.generation || {};
  const checkin = payload.checkin || {};
  const community = payload.community || {};
  const unlock = payload.prompt_unlock || {};
  const social = payload.social || {};

  const creditSummary = credit.summary || {};
  const rechargeSummary = recharge.summary || {};
  const invitationSummary = invitation.summary || {};
  const generationSummary = generation.summary || {};
  const checkinSummary = checkin.summary || {};
  const communitySummary = community.summary || {};
  const unlockSummary = unlock.summary || {};
  const socialSummary = social.summary || {};

  const profileHeader = `
    <div class="profile-head">
      ${renderUserIdentity(profile)}
      <div class="pill-list">
        ${renderUserBadge(profile)}
        ${renderUserBadge(profile, "user_group")}
        ${profile.is_channel_member ? '<span class="status-badge success">入宗门</span>' : '<span class="status-badge neutral">未入宗门</span>'}
        ${profile.is_real_payer ? '<span class="status-badge success">真实付费</span>' : '<span class="status-badge neutral">未付费</span>'}
        ${profile.is_low_trust_free_tier ? '<span class="status-badge warn">低信任免费层</span>' : ""}
      </div>
    </div>
  `;

  const baseMetrics = renderProfileMetricGrid([
    { label: "灵石", value: fmt(profile.credits), note: `收入 ${fmt(creditSummary.gross_income)} / 支出 ${fmt(creditSummary.gross_expense)}` },
    { label: "生成", value: fmt(profile.generation_count), note: `周期 ${fmt(generationSummary.period_generations)} / 活跃天 ${fmt(generationSummary.active_days)}` },
    { label: "签到", value: fmt(profile.checkin_count), note: `连续 ${fmt(checkinSummary.current_streak)} / 最长 ${fmt(checkinSummary.longest_streak)}` },
    { label: "充值", value: fmtAmount(rechargeSummary.real_success_usdt, " USDT"), note: `${fmt(rechargeSummary.real_success_orders)} 个真实成功订单` },
    { label: "邀请", value: fmt(invitationSummary.referral_relations), note: `受邀充值率 ${fmtPercent(invitationSummary.invitee_recharge_rate)}` },
    { label: "社区", value: fmt(communitySummary.gallery_posts), note: `信号 ${fmt(communitySummary.gallery_signal)} / 粉丝 ${fmt(socialSummary.followers_count)}` },
  ]);

  const creditSection = renderProfileSection("灵石收支", `
    ${renderProfileMetricGrid([
      { label: "收入", value: fmt(creditSummary.gross_income) },
      { label: "支出", value: fmt(creditSummary.gross_expense) },
      { label: "净变化", value: fmtSigned(creditSummary.net_change) },
      { label: "生成支出", value: fmt(creditSummary.generation_expense) },
      { label: "解锁收入", value: fmt(creditSummary.prompt_unlock_income) },
      { label: "解锁支出", value: fmt(creditSummary.prompt_unlock_expense) },
    ])}
    ${renderCompactList(credit.categories || [], (row) => renderCompactItem(row.category, row.direction, `${fmt(row.income || row.expense || row.net_change)} 灵石`))}
    ${renderCompactList(credit.recent_logs || [], (row) => renderCompactItem(row.operation_type, fmtDate(row.created_at), `${fmtSigned(row.credit_change)} / ${fmt(row.current_balance)}`))}
  `);

  const rechargeSection = renderProfileSection("充值情况", `
    ${renderProfileMetricGrid([
      { label: "真实成功", value: fmt(rechargeSummary.real_success_orders), note: fmtAmount(rechargeSummary.real_success_usdt, " USDT") },
      { label: "内部/赠送", value: fmt(rechargeSummary.internal_success_orders) },
      { label: "RMB", value: fmtAmount(rechargeSummary.real_success_rmb) },
      { label: "TON", value: fmtAmount(rechargeSummary.real_success_ton) },
      { label: "Stars", value: fmt(rechargeSummary.real_success_stars) },
      { label: "最近充值", value: fmtDate(rechargeSummary.last_recharge_at) },
    ])}
    ${renderCompactList(recharge.recent_orders || [], (row) => renderCompactItem(`${row.status || "-"} · ${channelLabel(row.payment_channel)}`, row.plan_name || fmtDate(row.occurred_at), fmtAmount(row.final_price)))}
  `);

  const invitationSection = renderProfileSection("邀请和返佣", `
    ${renderProfileMetricGrid([
      { label: "邀请关系", value: fmt(invitationSummary.referral_relations) },
      { label: "受邀入宗门", value: fmt(invitationSummary.invitee_channel_members) },
      { label: "受邀生成", value: fmt(invitationSummary.invitee_generation_users) },
      { label: "受邀充值", value: fmt(invitationSummary.recharged_invitees_count), note: fmtPercent(invitationSummary.invitee_recharge_rate) },
      { label: "邀请奖励", value: fmt(invitationSummary.referral_reward_credits) },
      { label: "可兑返佣", value: fmtAmount(invitationSummary.affiliate_available_balance_usdt, " USDT") },
    ])}
    ${renderCompactList(invitation.recent_invitees || [], (row) => renderCompactItem(row.full_name || row.username || `ID ${row.id}`, `${row.is_channel_member ? "入宗门" : "未入宗门"} · 生成 ${fmt(row.generation_count)}`, row.is_real_payer ? "已充值" : "未充值"))}
  `);

  const generationSection = renderProfileSection("生成情况", `
    ${renderProfileMetricGrid([
      { label: "历史生成", value: fmt(generationSummary.all_generations) },
      { label: "周期生成", value: fmt(generationSummary.period_generations) },
      { label: "活跃天", value: fmt(generationSummary.active_days) },
      { label: "Web", value: fmt(generationSummary.web_generations) },
      { label: "Bot", value: fmt(generationSummary.bot_generations) },
      { label: "公开", value: fmt(generationSummary.public_generations) },
    ])}
    ${renderCompactList(generation.type_distribution || [], (row) => renderCompactItem(row.task_type, fmtDate(row.last_generation_at), `${fmt(row.generations)} 次`))}
    ${renderCompactList(generation.source_distribution || [], (row) => renderCompactItem(row.source, "来源", `${fmt(row.generations)} 次`))}
    ${renderCompactList(generation.hour_distribution || [], (row) => renderCompactItem(`${fmt(row.hour)} 时`, "生成时段", `${fmt(row.generations)} 次`))}
    ${renderCompactList(generation.weekday_distribution || [], (row) => renderCompactItem(`星期 ${fmt(row.weekday)}`, "生成星期", `${fmt(row.generations)} 次`))}
    ${renderCompactList(generation.recent_generations || [], (row) => renderCompactItem(row.type || "unknown", `${row.task_id || "-"} · ${fmtDate(row.created_at)}`, `评分 ${fmt(row.rating)}`))}
  `);

  const checkinSection = renderProfileSection("签到情况", `
    ${renderProfileMetricGrid([
      { label: "历史签到", value: fmt(checkinSummary.total_checkins) },
      { label: "周期签到", value: fmt(checkinSummary.period_checkins) },
      { label: "当前连续", value: fmt(checkinSummary.current_streak) },
      { label: "最长连续", value: fmt(checkinSummary.longest_streak) },
      { label: "最近签到", value: fmtDate(checkinSummary.last_checkin_date) },
    ])}
    ${renderCompactList(checkin.recent_checkins || [], (row) => renderCompactItem(row.checkin_date, fmtDate(row.created_at)))}
  `);

  const communitySection = renderProfileSection("投稿和社区", `
    ${renderProfileMetricGrid([
      { label: "投稿", value: fmt(communitySummary.gallery_posts) },
      { label: "赞", value: fmt(communitySummary.likes) },
      { label: "踩", value: fmt(communitySummary.dislikes) },
      { label: "应用", value: fmt(communitySummary.applies) },
      { label: "评论", value: fmt(communitySummary.comments) },
      { label: "信号", value: fmt(communitySummary.gallery_signal) },
    ])}
    ${renderCompactList(community.samples || [], (row) => renderCompactItem(row.task_type || row.media_type || "投稿", `${row.task_id || "-"} · ${fmtDate(row.created_at)}`, `赞 ${fmt(row.likes_count)} / 应用 ${fmt(row.applied_count)}`))}
  `);

  const unlockSection = renderProfileSection("提示词解锁", `
    ${renderProfileMetricGrid([
      { label: "购买解锁", value: fmt(unlockSummary.purchased_unlocks), note: `花费 ${fmt(unlockSummary.spent_credits)} 灵石` },
      { label: "被解锁", value: fmt(unlockSummary.sold_unlocks), note: `收入 ${fmt(unlockSummary.earned_credits)} 灵石` },
      { label: "最近购买", value: fmtDate(unlockSummary.latest_purchase_at) },
      { label: "最近售出", value: fmtDate(unlockSummary.latest_sale_at) },
    ])}
    ${renderCompactList(unlock.recent_purchases || [], (row) => renderCompactItem(`Post ${fmt(row.post_id)}`, `${row.task_type || "-"} · 作者 ${fmt(row.author_id)}`, `${fmt(row.cost_credits)} 灵石`))}
    ${renderCompactList(unlock.recent_sales || [], (row) => renderCompactItem(`Post ${fmt(row.post_id)}`, `${row.task_type || "-"} · 买家 ${row.buyer_username || fmt(row.buyer_id)}`, `${fmt(row.cost_credits)} 灵石`))}
  `);

  const socialSection = renderProfileSection("关注关系", `
    ${renderProfileMetricGrid([
      { label: "粉丝", value: fmt(socialSummary.followers_count) },
      { label: "关注", value: fmt(socialSummary.following_count) },
      { label: "互关", value: fmt(socialSummary.mutual_follow_count) },
    ])}
    ${renderCompactList(social.recent_followers || [], (row) => renderCompactItem(row.full_name || row.username || `ID ${row.id}`, `${row.user_group || "凡人"} · ${fmtDate(row.followed_at)}`, "粉丝"))}
    ${renderCompactList(social.recent_following || [], (row) => renderCompactItem(row.full_name || row.username || `ID ${row.id}`, `${row.user_group || "凡人"} · ${fmtDate(row.followed_at)}`, "关注"))}
  `);

  $("#userProfileDrawerContent").innerHTML = [
    profileHeader,
    baseMetrics,
    creditSection,
    rechargeSection,
    invitationSection,
    generationSection,
    checkinSection,
    communitySection,
    unlockSection,
    socialSection,
  ].join("");
}

function asList(value) {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  return String(value).split(",").map((item) => item.trim()).filter(Boolean);
}

function renderCreditRiskUsers(rows = []) {
  $("#creditRiskUsers").innerHTML = tableRows(rows, (row) => {
    const reasons = asList(row.risk_reasons);
    return `
      <tr>
        <td>
          ${renderUserIdentity(row)}
          <div class="risk-user-badges">
            ${renderUserBadge(row)}
            ${renderUserBadge(row, "user_group")}
          </div>
        </td>
        <td>
          <strong class="risk-score">${fmt(row.risk_score)}</strong>
          <div class="risk-tags">
            ${reasons.map((reason) => `<span class="pill amber">${escapeHtml(reason)}</span>`).join("") || '<span class="muted">-</span>'}
          </div>
        </td>
        <td>
          <div class="amount-positive">+${fmt(row.income)}</div>
          <div class="amount-negative">-${fmt(row.expense)}</div>
          <div class="muted small">净 ${fmtSigned(row.net_change)}</div>
        </td>
        <td>
          <div>免费签到 ${fmt(row.free_checkin_income)} · 加成 ${fmt(row.identity_checkin_bonus_income)}</div>
          <div>邀请 ${fmt(row.referral_income)} · 退款 ${fmt(row.refund_income)}</div>
          <div class="muted small">充值 ${fmt(row.recharge_income)}</div>
          <div class="muted small">生成消耗 ${fmt(row.generation_expense)}</div>
        </td>
        <td>
          <strong>${fmt(row.current_balance)}</strong>
          <div class="muted small">${row.is_channel_member ? "入宗门" : "未入宗门"}</div>
        </td>
      </tr>
    `;
  });
}

function channelLabel(channel) {
  if (channel === "XTR") return "Stars";
  if (channel === "INTERNAL" || !channel) return "内部/赠送";
  return channel;
}

function formatChannelAmount(row) {
  const parts = [];
  if (Number(row.rmb_amount || 0)) parts.push(`${fmtAmount(row.rmb_amount, " RMB")}`);
  if (Number(row.ton_amount || 0)) parts.push(`${fmtAmount(row.ton_amount, " TON")}`);
  if (Number(row.stars_amount || 0)) parts.push(`${fmt(row.stars_amount)} Stars`);
  if (Number(row.amount || 0) && !parts.length) parts.push(fmtAmount(row.amount));
  return parts.join(" · ") || "-";
}

function renderOrderStatusBadge(status, isInternal = false) {
  const normalized = String(status || "").toLowerCase();
  const label = status || "-";
  const badgeClass = normalized === "success" ? "success" : normalized === "failed" ? "danger" : "warn";
  return `
    <span class="status-badge ${badgeClass}">${escapeHtml(label)}</span>
    ${isInternal ? '<span class="status-badge neutral">内部/赠送</span>' : ""}
  `;
}

function renderFinanceInvitation(invitation = {}) {
  $("#financeInvitationSummary").innerHTML = `
    <div class="finance-stat-row"><span>受邀付费人数</span><strong>${fmt(invitation.invitee_payers)}</strong></div>
    <div class="finance-stat-row"><span>受邀成功订单</span><strong>${fmt(invitation.orders)}</strong></div>
    <div class="finance-stat-row"><span>USDT 估算</span><strong>${fmtAmount(invitation.usdt_amount, " USDT")}</strong></div>
    <div class="finance-stat-row"><span>渠道金额</span><strong>${formatChannelAmount(invitation)}</strong></div>
  `;
}

function renderFinance() {
  const summary = state.finance?.summary || {};
  const first = state.finance?.first_purchase || {};
  const health = state.finance?.health || {};
  $("#financeSummary").innerHTML = [
    metric("USDT 估算", fmtAmount(summary.usdt_amount, " USDT"), `ARPPU ${fmtAmount(summary.arppu_usdt, " USDT")}`),
    metric("RMB", fmtAmount(summary.rmb_amount, " RMB"), `均单 ${fmtAmount(summary.rmb_avg_order, " RMB")}`),
    metric("TON", fmtAmount(summary.ton_amount, " TON"), "固定汇率 1.4 USDT"),
    metric("Stars", `${fmt(summary.stars_amount)} Stars`, "固定汇率 0.013 USDT"),
    metric("发放灵石", fmt(summary.plan_reward_credits), `每 USDT ${fmtAmount(health.credits_per_usdt)}`),
    metric("真实付费人数", fmt(summary.real_payers), `成功订单 ${fmt(summary.success_orders)}`),
    metric("新付费 / 复购", `${fmt(summary.new_payers)} / ${fmt(summary.repeat_payers)}`, `首充用户 ${fmt(first.first_purchase_users)}`),
    metric("成功率", fmtPercent(summary.success_rate), `失败 ${fmt(summary.failed_orders)} · 处理中 ${fmt(summary.pending_orders)}`),
    metric("内部/赠送订单", fmt(summary.internal_success_orders), `占比 ${fmtPercent(health.internal_success_ratio)}`),
    metric("最近成功订单", fmtDate(summary.latest_success_at), `首日付费 ${fmt(first.first_day_payers)}`),
  ].join("");

  const daily = state.finance?.daily || [];
  ensureCompareInput("#financeCompareDatesInput", daily);
  renderFinanceCharts();
  renderFinanceInvitation(state.finance?.invitation || {});
  renderHealthFlags(health.flags || [], "#financeHealthFlags");

  $("#financeChannels").innerHTML = tableRows(state.finance?.channels, (row) => `
    <tr>
      <td class="mono">${escapeHtml(channelLabel(row.channel))}</td>
      <td>${fmt(row.success_orders)} / ${fmt(row.pending_orders)} / ${fmt(row.failed_orders)}</td>
      <td>${fmt(row.payers)}</td>
      <td>${formatChannelAmount(row)}</td>
      <td>${fmtAmount(row.usdt_amount, " USDT")}</td>
      <td>${fmtAmount(row.avg_order_amount)}</td>
      <td>${fmt(row.plan_reward_credits)}</td>
    </tr>
  `);

  $("#financePlans").innerHTML = tableRows(state.finance?.plans, (row) => `
    <tr>
      <td>
        <strong>${escapeHtml(row.plan_name || "未知套餐")}</strong>
        <div class="muted small">${fmt(row.duration_days)} 天 · 配置 ${fmt(row.configured_reward_credits)} 灵石</div>
      </td>
      <td>${escapeHtml(row.identity_name || "未知身份")}</td>
      <td>${fmt(row.success_orders)} / ${fmt(row.all_orders)}</td>
      <td>${fmt(row.payers)}</td>
      <td>${fmtAmount(row.usdt_amount, " USDT")}</td>
      <td>${fmt(row.plan_reward_credits)}</td>
      <td>${fmtPercent(row.success_rate)}</td>
    </tr>
  `);

  $("#financeSegments").innerHTML = tableRows(state.finance?.segments, (row) => `
    <tr>
      <td>${escapeHtml(row.segment)}</td>
      <td>${fmt(row.users)}</td>
      <td>${fmt(row.orders)}</td>
      <td>${fmtAmount(row.usdt_amount, " USDT")}</td>
      <td>${fmtAmount(row.avg_usdt_per_user, " USDT")}</td>
      <td>${fmtDate(row.latest_paid_at)}</td>
    </tr>
  `);

  $("#financeTopPayers").innerHTML = tableRows(state.finance?.top_payers, (row) => `
    <tr>
      <td>
        ${renderUserIdentity(row)}
        <div class="risk-user-badges">
          ${renderUserBadge(row)}
          ${renderUserBadge(row, "user_group")}
        </div>
      </td>
      <td>${fmt(row.orders)}</td>
      <td><strong>${fmtAmount(row.usdt_amount, " USDT")}</strong></td>
      <td>${formatChannelAmount(row)}</td>
      <td>${fmt(row.plan_reward_credits)}</td>
      <td>${fmtDate(row.latest_paid_at)}</td>
    </tr>
  `);

  $("#financeRecentOrders").innerHTML = tableRows(state.finance?.recent_orders, (row) => `
    <tr>
      <td>
        <strong class="mono">${escapeHtml(row.order_id || row.business_order_id || row.id)}</strong>
        <div class="muted small">#${fmt(row.id)}</div>
      </td>
      <td>${renderUserIdentity({ id: row.internal_user_id, username: row.username, full_name: row.full_name })}</td>
      <td>
        <strong>${escapeHtml(row.plan_name || "未知套餐")}</strong>
        <div class="muted small">${escapeHtml(row.identity_name || "未知身份")} · ${fmt(row.reward_credits)} 灵石</div>
      </td>
      <td>
        <div>${escapeHtml(channelLabel(row.is_internal_order ? "INTERNAL" : row.payment_channel))}</div>
        <div class="pill-list">${renderOrderStatusBadge(row.status, row.is_internal_order)}</div>
      </td>
      <td>${fmtAmount(row.final_price)}</td>
      <td>${fmtDate(row.order_time || row.paid_at || row.created_at)}</td>
    </tr>
  `);
}

const financeMetricLabels = {
  usdt_amount: "USDT",
  plan_reward_credits: "发放灵石",
  success_orders: "成功订单",
  payers: "付费人数",
};

function renderFinanceCharts(hourlyRows = null, hourlyLabel = "近周期累计") {
  const daily = state.finance?.daily || [];
  const dates = daily.map((row) => row.day);
  const metric = $("#financeMetricSelect")?.value || state.financeMetric || "usdt_amount";
  state.financeMetric = metric;
  const metricLabel = financeMetricLabels[metric] || metric;
  let trendSeries;
  if (metric === "usdt_amount") {
    trendSeries = [
      { name: "RMB 折 USDT", type: "bar", stack: "revenue", data: daily.map((row) => numeric(row.rmb_usdt_amount)), barMaxWidth: 22 },
      { name: "TON 折 USDT", type: "bar", stack: "revenue", data: daily.map((row) => numeric(row.ton_usdt_amount)), barMaxWidth: 22 },
      { name: "Stars 折 USDT", type: "bar", stack: "revenue", data: daily.map((row) => numeric(row.stars_usdt_amount)), barMaxWidth: 22 },
      { name: "累计 USDT", type: "line", smooth: true, data: cumulative(daily.map((row) => numeric(row.usdt_amount))) },
    ];
  } else {
    const values = daily.map((row) => numeric(row[metric]));
    trendSeries = [
      { name: `每日${metricLabel}`, type: "bar", data: values, barMaxWidth: 22 },
      { name: `累计${metricLabel}`, type: "line", smooth: true, data: cumulative(values) },
    ];
  }
  renderChart("financeTrendChart", buildLineBarOption({ dates, series: trendSeries }));

  const summary = state.finance?.summary || {};
  renderChart("financeStatusChart", buildFunnelOption([
    { label: "全部订单", count: numeric(summary.success_orders) + numeric(summary.pending_orders) + numeric(summary.failed_orders) },
    { label: "成功", count: summary.success_orders },
    { label: "处理中", count: summary.pending_orders },
    { label: "失败", count: summary.failed_orders },
    { label: "内部/赠送成功", count: summary.internal_success_orders },
  ]));

  renderChart("financeHourlyChart", buildHourlyOption(hourlyRows || (state.finance?.hourly || []), {
    metric: "plan_reward_credits",
    name: hourlyLabel,
  }));

  renderChart("financeChannelChart", buildDonutOption(
    (state.finance?.channels || []).map((row) => ({ label: channelLabel(row.channel), value: row.usdt_amount })),
    "value"
  ));
  renderChart("financePlanChart", buildDonutOption(
    (state.finance?.plans || []).map((row) => ({ label: row.plan_name, value: row.usdt_amount })),
    "value"
  ));
}

function generationHealthFlags(summary = {}) {
  const flags = [];
  if (Number(summary.worker_failure_rate || 0) >= 5) flags.push("Worker 失败率偏高");
  if (Number(summary.result_rate || 0) < 90) flags.push("输出结果率偏低");
  if (Number(summary.avg_credits_per_generation || 0) >= 20) flags.push("单次生成灵石消耗偏高");
  if (Number(summary.gallery_rate || 0) < 1 && Number(summary.generations || 0) > 100) flags.push("Gallery 转化偏低");
  return flags.length ? flags : ["生成健康暂未触发高风险规则"];
}

function interactionText(row = {}) {
  return `赞 ${fmt(row.likes)} · 应用 ${fmt(row.applies)} · 评论 ${fmt(row.comments)} · 踩 ${fmt(row.dislikes)}`;
}

function renderGeneration() {
  const summary = state.generation?.summary || {};
  $("#generationSummary").innerHTML = [
    metric("总生成", fmt(summary.total_generations), `${fmtPeriod(state.generation?.days)} ${fmt(summary.generations)}`),
    metric("生成用户", fmt(summary.creators), `Web ${fmt(summary.web_generations)} · Bot ${fmt(summary.bot_generations)}`),
    metric("输出结果率", fmtPercent(summary.result_rate), `结果 ${fmt(summary.result_records)} / 输入 ${fmt(summary.with_input_records)}`),
    metric("内容转化", fmtPercent(summary.gallery_rate), `公开 ${fmt(summary.public_records)} · 收藏 ${fmt(summary.favorited_records)}`),
    metric("Gallery 互动", fmt(summary.gallery_posts), `赞 ${fmt(summary.likes)} · 应用 ${fmt(summary.applies)}`),
    metric("Prompt 解锁", fmt(summary.prompt_unlocks), `评论 ${fmt(summary.comments)} · 踩 ${fmt(summary.dislikes)}`),
    metric("灵石消耗", fmt(summary.credits_spent), `均次 ${fmtAmount(summary.avg_credits_per_generation)}`),
    metric("Worker 失败率", fmtPercent(summary.worker_failure_rate), `成功 ${fmt(summary.worker_successes)} · 失败 ${fmt(summary.worker_failures)}`),
    metric("执行耗时", fmtAmount(summary.avg_worker_duration, " 秒"), `P95 ${fmtAmount(summary.p95_worker_duration, " 秒")}`),
    metric("最近生成", fmtDate(summary.latest_generation_at), `${fmt(Math.round(summary.avg_width || 0))} x ${fmt(Math.round(summary.avg_height || 0))}`),
  ].join("");

  ensureCompareInput("#generationCompareDatesInput", state.generation?.daily || []);
  renderGenerationCharts();
  renderHealthFlags(generationHealthFlags(summary), "#generationHealthFlags");

  $("#generationTypes").innerHTML = tableRows(state.generation?.by_type, (row) => `
    <tr>
      <td class="mono">${escapeHtml(row.task_type)}</td>
      <td>
        <strong>${fmt(row.generations)}</strong>
        <div class="muted small">${fmt(row.creators)} 用户</div>
      </td>
      <td>
        <strong>${fmtPercent(row.result_rate)}</strong>
        <div class="muted small">输入 ${fmtPercent(row.input_rate)}</div>
      </td>
      <td>
        <strong>${fmt(row.gallery_posts)}</strong>
        <div class="muted small">${interactionText(row)}</div>
      </td>
      <td>
        <strong>${fmt(row.credits_spent)}</strong>
        <div class="muted small">均次 ${fmtAmount(row.avg_credits_per_generation)}</div>
      </td>
      <td>
        <strong>${fmtPercent(row.worker_failure_rate)}</strong>
        <div class="muted small">${fmtAmount(row.avg_worker_duration, " 秒")}</div>
      </td>
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

  const leaderboards = state.generation?.leaderboards || {};
  $("#generationUserLeaderboard").innerHTML = tableRows(leaderboards.generation, (row) => `
    <tr>
      <td>
        ${renderUserIdentity(row)}
        <div class="risk-user-badges">
          ${renderUserBadge(row)}
          ${renderUserBadge(row, "user_group")}
        </div>
      </td>
      <td><strong>${fmt(row.generations)}</strong></td>
      <td>${fmt(row.result_records)}</td>
      <td>${fmt(row.gallery_posts)}</td>
      <td>${fmtDate(row.last_generation_at)}</td>
    </tr>
  `);

  $("#generationCreditLeaderboard").innerHTML = tableRows(leaderboards.credits, (row) => `
    <tr>
      <td>
        ${renderUserIdentity(row)}
        <div class="risk-user-badges">
          ${renderUserBadge(row)}
          ${renderUserBadge(row, "user_group")}
        </div>
      </td>
      <td><strong>${fmt(row.credits_spent)}</strong></td>
      <td>${fmt(row.debit_events)}</td>
      <td>${fmtAmount(row.avg_credits_per_event)}</td>
      <td>${fmt(row.current_balance)}</td>
    </tr>
  `);

  $("#generationGalleryLeaderboard").innerHTML = tableRows(leaderboards.gallery, (row) => `
    <tr>
      <td>
        ${renderUserIdentity(row)}
        <div class="risk-user-badges">
          ${renderUserBadge(row)}
          ${renderUserBadge(row, "user_group")}
        </div>
      </td>
      <td>${fmt(row.gallery_posts)}</td>
      <td>${interactionText(row)}</td>
      <td><strong>${fmt(row.signal_score)}</strong></td>
      <td>${fmtDate(row.latest_post_at)}</td>
    </tr>
  `);

  $("#generationRecentHighSignal").innerHTML = tableRows(state.generation?.recent_high_signal, (row) => `
    <tr>
      <td>
        <strong class="mono">${escapeHtml(row.task_type)}</strong>
        <div class="muted small">${escapeHtml(row.media_type || "unknown")} · ${escapeHtml(row.task_id || "-")}</div>
      </td>
      <td>${renderUserIdentity(row)}</td>
      <td>${interactionText(row)}</td>
      <td>
        <strong class="signal-score">${fmt(row.signal_score)}</strong>
        <div class="pill-list">
          ${row.is_public ? '<span class="pill">公开</span>' : ""}
          ${row.is_favorited ? '<span class="pill amber">收藏</span>' : ""}
        </div>
      </td>
      <td>${fmtDate(row.created_at)}</td>
    </tr>
  `);
}

function renderGenerationCharts(compareRows = null, compareKind = "hourly-period") {
  const daily = state.generation?.daily || [];
  const dates = daily.map((row) => row.day);
  renderChart("generationTrendChart", buildLineBarOption({
    dates,
    series: [
      { name: "生成量", type: "line", smooth: true, data: daily.map((row) => numeric(row.generations)), areaStyle: { opacity: 0.08 } },
      { name: "创作者", type: "line", smooth: true, data: daily.map((row) => numeric(row.creators)) },
      { name: "Web", type: "bar", stack: "source", data: daily.map((row) => numeric(row.web_generations)), barMaxWidth: 22 },
      { name: "Bot", type: "bar", stack: "source", data: daily.map((row) => numeric(row.bot_generations)), barMaxWidth: 22 },
      { name: "灵石消耗", type: "line", yAxisIndex: 1, smooth: true, data: daily.map((row) => numeric(row.credits_spent)) },
    ],
    yAxis: [
      { type: "value", name: "生成", axisLabel: { formatter: shortNumber } },
      { type: "value", name: "灵石", axisLabel: { formatter: shortNumber }, splitLine: { show: false } },
    ],
  }));

  renderChart("generationQualityFunnelChart", buildFunnelOption(state.generation?.quality_segments || []));
  renderChart("generationSourceMixChart", buildDonutOption(state.generation?.source_mix || [], "count"));

  renderChart("generationWorkerChart", buildLineBarOption({
    dates,
    series: [
      { name: "Worker 成功", type: "bar", stack: "worker", data: daily.map((row) => numeric(row.worker_successes)), barMaxWidth: 18 },
      { name: "Worker 失败", type: "bar", stack: "worker", data: daily.map((row) => numeric(row.worker_failures)), barMaxWidth: 18 },
      {
        name: "失败率",
        type: "line",
        yAxisIndex: 1,
        data: daily.map((row) => {
          const total = numeric(row.worker_successes) + numeric(row.worker_failures);
          return total ? Math.round((numeric(row.worker_failures) / total) * 10000) / 100 : 0;
        }),
      },
    ],
    yAxis: [
      { type: "value", name: "事件", axisLabel: { formatter: shortNumber } },
      { type: "value", name: "失败率%", min: 0, max: 100, splitLine: { show: false } },
    ],
  }));

  const bubbleRows = state.generation?.by_type || [];
  renderChart("generationTypeBubbleChart", bubbleRows.length ? {
    color: chartPalette,
    tooltip: {
      trigger: "item",
      formatter: (params) => {
        const row = bubbleRows[params.dataIndex] || {};
        return `${escapeHtml(row.task_type)}<br/>生成 ${fmt(row.generations)}<br/>输出率 ${fmtPercent(row.result_rate)}<br/>失败率 ${fmtPercent(row.worker_failure_rate)}<br/>灵石 ${fmt(row.credits_spent)}`;
      },
    },
    grid: { left: 54, right: 34, top: 22, bottom: 42, containLabel: true },
    xAxis: { type: "value", name: "生成量", axisLabel: { formatter: shortNumber }, splitLine: { lineStyle: { type: "dashed" } } },
    yAxis: { type: "value", name: "输出率%", min: 0, max: 100, splitLine: { lineStyle: { type: "dashed" } } },
    series: [{
      name: "任务类型",
      type: "scatter",
      data: bubbleRows.map((row) => [numeric(row.generations), numeric(row.result_rate), numeric(row.credits_spent), row.task_type]),
      symbolSize: (value) => Math.max(10, Math.min(54, Math.sqrt(numeric(value[2])) * 1.4)),
    }],
  } : chartEmptyOption());

  if (compareKind === "types") {
    const rows = compareRows || [];
    const compareDates = Array.from(new Set(rows.map((row) => row.date)));
    const taskTypes = Array.from(new Set(rows.map((row) => row.task_type))).slice(0, 12);
    renderChart("generationCompareChart", buildStackedBarOption({
      dates: compareDates,
      rows: rows.map((row) => ({ ...row, category: row.task_type, value: row.generations })),
      categories: taskTypes,
    }));
    return;
  }

  renderChart("generationCompareChart", buildHourlyOption(compareRows || (state.generation?.hourly || []), {
    metric: "generations",
    name: compareKind === "hourly-cumulative" ? "累计生成量" : "分时生成量",
  }));
}

function renderPromptMetricSummary() {
  const summary = state.prompts?.summary || {};
  const mart = state.prompts?.mart || {};
  $("#promptSummary").innerHTML = [
    metric("提示词记录", fmt(summary.prompt_records), `归一化 ${fmt(summary.distinct_prompts)} 条 · Mart ${fmtDate(mart.stats_updated_at)}`),
    metric("重复提示词", fmt(summary.repeated_prompts), `多人复用 ${fmt(summary.multi_user_prompts)}`),
    metric("平均字数", fmtAmount(summary.avg_chars), `中位 ${fmtAmount(summary.median_chars)} 字`),
    metric("高价值提示词", fmt(summary.high_value_prompts), "多人复用且信号较高"),
    metric("已排除模板", fmt(summary.builtin_template_records_excluded), `衍生 ${fmt(summary.derived_records_excluded)}`),
  ].join("");
}

function renderPromptDistributions() {
  const distributions = state.prompts?.distributions || {};
  renderDistribution("#promptLengthDistribution", distributions.length || []);
  renderDistribution("#promptReuseDistribution", distributions.reuse || []);
  renderDistribution("#promptTaskTypeDistribution", distributions.task_type || []);
  renderDistribution("#promptScopeDistribution", distributions.template_scope || []);
}

function renderPromptTaskTypeOptions() {
  const select = $("#taskTypeSelect");
  if (!select) return;
  const existing = select.value || "";
  const seen = new Set([""]);
  const options = ['<option value="">全部</option>'];
  (state.promptTaskTypes || []).forEach((row) => {
    const value = row.task_type || row.label || "";
    if (!value || seen.has(value)) return;
    seen.add(value);
    const count = row.generations ?? row.count;
    const label = count === undefined ? value : `${value} (${fmt(count)})`;
    options.push(`<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`);
  });
  if (existing && !seen.has(existing)) {
    options.push(`<option value="${escapeHtml(existing)}">${escapeHtml(existing)}</option>`);
  }
  select.innerHTML = options.join("");
  select.value = seen.has(existing) ? existing : "";
}

function promptInteractionText(row = {}) {
  return `
    <div>赞 ${fmt(row.likes)} · 踩 ${fmt(row.dislikes)}</div>
    <div>应用 ${fmt(row.applies)} · 解锁 ${fmt(row.prompt_unlocks)}</div>
    <div class="muted small">收藏 ${fmt(row.favorite_records)} · 评论 ${fmt(row.comments)}</div>
  `;
}

function promptScopePills(row = {}) {
  const scope = row.scope_label || "自然输入";
  const scopeClass = scope === "一键应用衍生" || scope === "内置模板" ? "amber" : scope === "源模板" ? "" : "gray";
  return `
    <div class="pill-list">
      <span class="pill ${scopeClass}">${escapeHtml(scope)}</span>
      ${Number(row.gallery_posts || 0) ? `<span class="pill">Gallery ${fmt(row.gallery_posts)}</span>` : ""}
    </div>
  `;
}

function promptVariantKey(item) {
  const params = getPromptParams();
  return [
    item?.prompt_hash || "",
    params.days,
    params.task_type || "",
    params.template_scope || "natural",
  ].join("|");
}

function renderPromptVariantRows(payload) {
  const variants = payload?.variants || [];
  if (!variants.length) {
    return '<div class="empty compact">暂无原文变体</div>';
  }
  return variants.map((variant) => `
    <article class="prompt-variant-item">
      <div class="prompt-variant-meta">
        <strong>${fmt(variant.uses)} 次 / ${fmt(variant.users)} 人</strong>
        <span>${(variant.task_types || []).slice(0, 3).map(escapeHtml).join(" / ") || "-"} · ${fmtDate(variant.last_seen)}</span>
      </div>
      <div class="prompt-variant-text">${escapeHtml(variant.raw_prompt || variant.raw_preview || "")}</div>
    </article>
  `).join("");
}

function renderPromptVariantContent(item) {
  const container = $("#promptVariantList");
  if (!container || !item) return;
  const key = promptVariantKey(item);
  const cached = state.promptVariantCache[key];
  if (cached) {
    container.innerHTML = renderPromptVariantRows(cached);
    return;
  }
  container.innerHTML = '<div class="muted small">点击查看当前筛选范围内被合并的原文写法</div>';
}

async function loadPromptVariants(item) {
  if (!item?.prompt_hash) return;
  const key = promptVariantKey(item);
  const button = $("#promptVariantButton");
  const container = $("#promptVariantList");
  if (state.promptVariantCache[key]) {
    renderPromptVariantContent(item);
    return;
  }
  if (button) {
    button.disabled = true;
    button.textContent = "加载中";
  }
  if (container) {
    container.innerHTML = '<div class="muted small">正在加载原文变体...</div>';
  }
  try {
    const params = getPromptParams();
    const payload = await fetchJson(`/api/prompts/${encodeURIComponent(item.prompt_hash)}/variants`, {
      days: params.days,
      task_type: params.task_type,
      template_scope: params.template_scope,
      limit: 20,
    });
    state.promptVariantCache[key] = payload;
    if (state.selectedPrompt?.prompt_hash === item.prompt_hash) {
      renderPromptVariantContent(item);
    }
  } catch (error) {
    if (container) {
      container.innerHTML = `<div class="error-inline">${escapeHtml(error.message || String(error))}</div>`;
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "查看变体";
    }
  }
}

function renderPrompts() {
  renderPromptMetricSummary();
  renderPromptDistributions();

  const groups = state.prompts?.prompt_groups || [];
  if (!state.selectedPrompt || !groups.some((item) => item.prompt_hash === state.selectedPrompt.prompt_hash)) {
    state.selectedPrompt = groups[0] || null;
  }

  $("#promptRows").innerHTML = tableRows(groups, (row) => `
    <tr data-prompt-hash="${escapeHtml(row.prompt_hash)}">
      <td>
        <strong class="signal-score">${fmt(row.value_score)}</strong>
        <div class="muted small">字数 ${fmt(row.char_count)}</div>
      </td>
      <td>
        <div class="prompt-preview">${escapeHtml(row.prompt_preview)}</div>
        ${Number(row.variant_count || 1) > 1 ? `<div class="muted small">归一化 ${fmt(row.variant_count)} 种</div>` : ""}
      </td>
      <td>
        <strong>${fmt(row.uses)}</strong> 次
        <div class="muted small">${fmt(row.users)} 人 · ${(row.task_types || []).slice(0, 3).map(escapeHtml).join(" / ") || "-"}</div>
      </td>
      <td>${promptInteractionText(row)}</td>
      <td>${promptScopePills(row)}</td>
      <td>${fmtDate(row.last_seen)}</td>
    </tr>
  `);

  document.querySelectorAll("#promptRows tr").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedPrompt = groups.find((item) => item.prompt_hash === row.dataset.promptHash) || groups[0] || null;
      renderPromptDetail();
    });
  });

  const pagination = state.prompts?.pagination || {};
  const total = Number(pagination.total_groups || 0);
  $("#promptPageInfo").textContent = `第 ${fmt(pagination.page || 1)} 页 · 共 ${fmt(total)} 组`;
  $("#promptPrevButton").disabled = Number(pagination.page || 1) <= 1;
  $("#promptNextButton").disabled = !pagination.has_next;

  renderPromptDetail();
}

function renderPromptDetail() {
  const item = state.selectedPrompt;
  if (!item) {
    $("#promptDetail").innerHTML = '<div class="empty">暂无提示词</div>';
    return;
  }
  $("#promptDetail").innerHTML = `
    <h3>价值 ${fmt(item.value_score)}</h3>
    <p class="prompt-fulltext">${escapeHtml(item.prompt || item.prompt_preview)}</p>
    <dl>
      <dt>Hash</dt><dd class="mono">${escapeHtml(item.prompt_hash)}</dd>
      <dt>复用</dt><dd>${fmt(item.uses)} 次 / ${fmt(item.users)} 人</dd>
      <dt>变体</dt><dd>归一化 ${fmt(item.variant_count || 1)} 种</dd>
      <dt>时间</dt><dd>${fmtDate(item.first_seen)} - ${fmtDate(item.last_seen)}</dd>
      <dt>任务</dt><dd>${(item.task_types || []).map(escapeHtml).join(" / ") || "-"}</dd>
      <dt>互动</dt><dd>赞 ${fmt(item.likes)} / 踩 ${fmt(item.dislikes)} / 应用 ${fmt(item.applies)} / 解锁 ${fmt(item.prompt_unlocks)}</dd>
      <dt>收藏</dt><dd>${fmt(item.favorite_records)} 条 · 公开 ${fmt(item.public_records)} 条 · Gallery ${fmt(item.gallery_posts)} 条</dd>
      <dt>来源</dt><dd>${promptScopePills(item)}</dd>
    </dl>
    <section class="prompt-variants">
      <div class="prompt-variant-header">
        <strong>归一化变体</strong>
        <button id="promptVariantButton" type="button">查看变体</button>
      </div>
      <div id="promptVariantList" class="prompt-variant-list"></div>
    </section>
  `;
  renderPromptVariantContent(item);
  $("#promptVariantButton")?.addEventListener("click", () => loadPromptVariants(item));
}

function templateRefreshNote(summary = {}) {
  const refresh = summary.refresh || {};
  if (state.templateCandidateRefreshing) return "正在提交刷新";
  if (refresh.running) {
    return refresh.pid ? `刷新运行中 · PID ${fmt(refresh.pid)}` : "刷新运行中";
  }
  if (refresh.last_exit) {
    return `上次刷新退出码 ${fmt(refresh.last_exit.returncode)}`;
  }
  return summary.refreshed_at ? `刷新于 ${fmtDate(summary.refreshed_at)}` : "等待首次刷新";
}

function currentTemplateMinPrompts() {
  const raw = $("#templateMinPromptsInput")?.value;
  const fallback = state.templateCandidateMinPrompts || PROMPT_TEMPLATE_DEFAULT_MIN_PROMPTS;
  const numeric = Number(raw || fallback);
  const safeValue = Number.isFinite(numeric) ? numeric : fallback;
  const clamped = Math.min(Math.max(1, Math.trunc(safeValue)), PROMPT_TEMPLATE_MAX_MIN_PROMPTS);
  state.templateCandidateMinPrompts = clamped;
  return clamped;
}

function syncTemplateMinPromptsInput() {
  const input = $("#templateMinPromptsInput");
  if (!input) return;
  const value = String(state.templateCandidateMinPrompts || PROMPT_TEMPLATE_DEFAULT_MIN_PROMPTS);
  if (input.value !== value) input.value = value;
}

function renderTemplateFilterOptions() {
  const filters = state.templates?.filters || {};
  renderPromptTokenOptionSet(
    "#templateTaskTypeSelect",
    filters.tasks || [],
    [{ value: "", label: "全部任务" }]
  );
  const selectedTask = $("#templateTaskTypeSelect")?.value || "";
  const modelRows = selectedTask ? filters.models || [] : [];
  renderPromptTokenOptionSet(
    "#templateModelSelect",
    modelRows,
    [{ value: "", label: selectedTask ? "全部附加模型" : "先选择任务类型" }]
  );
  const modelSelect = $("#templateModelSelect");
  if (modelSelect) {
    modelSelect.disabled = !selectedTask || modelRows.length === 0;
  }
}

function renderTemplateSlotGroups(tokenSlots = {}, { maxGroups = 8, maxTokensPerGroup = 8 } = {}) {
  const slots = parseObject(tokenSlots);
  const groups = Object.entries(slots)
    .map(([slotKey, values]) => ({
      slotKey,
      label: PROMPT_TEMPLATE_SLOT_LABELS[slotKey] || slotKey,
      values: (Array.isArray(values) ? values : []).filter(Boolean),
    }))
    .filter((group) => group.values.length);
  if (!groups.length) return '<span class="muted">-</span>';
  const visible = groups.slice(0, maxGroups).map((group) => {
    const tokens = group.values.slice(0, maxTokensPerGroup).map((token) => (
      `<span class="pill">${escapeHtml(token)}</span>`
    ));
    const hidden = Math.max(0, group.values.length - maxTokensPerGroup);
    if (hidden) tokens.push(`<span class="pill neutral">另 ${fmt(hidden)} 个</span>`);
    return `
      <div class="template-slot-group">
        <span class="template-slot-label">${escapeHtml(group.label)}</span>
        <span class="template-slot-token-list">${tokens.join("")}</span>
      </div>
    `;
  });
  const hiddenGroups = Math.max(0, groups.length - visible.length);
  if (hiddenGroups) {
    visible.push(`<div class="template-slot-more muted small">另 ${fmt(hiddenGroups)} 个槽位</div>`);
  }
  return `<div class="template-slot-groups">${visible.join("")}</div>`;
}

function renderTemplateSimilarityBadge(row = {}) {
  const bucket = row.similarity_bucket || "";
  if (!bucket) return '<span class="status-badge neutral">未计算</span>';
  const className = PROMPT_TEMPLATE_SIMILARITY_BADGE_CLASSES[bucket] || "neutral";
  const score = row.similarity_score === null || row.similarity_score === undefined || row.similarity_score === ""
    ? ""
    : ` · ${fmtAmount(row.similarity_score)}`;
  return `<span class="status-badge ${className}">${escapeHtml(bucket)}${escapeHtml(score)}</span>`;
}

function renderTemplateReviewBadges(row = {}) {
  const badges = [];
  const markedCount = Number(row.marked_prompt_count || 0);
  if (row.low_quality) {
    badges.push('<span class="status-badge danger">低质量</span>');
  }
  if (markedCount > 0) {
    badges.push(`<span class="status-badge success">已暂存 · ${fmt(markedCount)}</span>`);
  }
  if (!row.low_quality && markedCount <= 0) {
    badges.push('<span class="status-badge neutral">未处理</span>');
  }
  return badges.join("");
}

function currentTemplateFilterLabel() {
  const parts = [];
  const search = $("#templateSearchInput")?.value?.trim();
  const similarity = $("#templateSimilaritySelect")?.value || "";
  const reviewStatus = $("#templateReviewStatusSelect")?.value || "all";
  if (search) parts.push(search);
  if (similarity) parts.push(similarity);
  if (reviewStatus === "processed") parts.push("已处理");
  if (reviewStatus === "unprocessed") parts.push("未处理");
  if (reviewStatus === "low_quality") parts.push("低质量");
  return parts.join(" · ") || "全部模板";
}

function renderTemplateCandidates(payload) {
  if (!$("#templateSummary")) return;
  const summary = payload?.summary || {};
  const rows = payload?.rows || [];
  const pagination = payload?.pagination || {};
  const scope = payload?.scope || {};
  state.templateCandidateMinPrompts = Number(payload?.min_prompts || state.templateCandidateMinPrompts || PROMPT_TEMPLATE_DEFAULT_MIN_PROMPTS);
  syncTemplateMinPromptsInput();
  if (payload?.filters_included !== false) {
    renderTemplateFilterOptions();
  }
  $("#templateSummary").innerHTML = [
    metric("模板候选", fmt(summary.template_count), "词元槽位组合"),
    metric("候选提示词", fmt(summary.prompt_links), "模板明细累计"),
    metric("当前筛选", fmt(pagination.total), currentTemplateFilterLabel()),
    metric("最低提示词数", fmt(state.templateCandidateMinPrompts), "只读筛选阈值"),
    metric("刷新", fmtDate(summary.refreshed_at), templateRefreshNote(summary)),
  ].join("");
  const status = $("#templateCandidateStatus");
  if (status) {
    status.textContent = payload?.ready === false
      ? (payload.message || "模板候选尚未构建")
      : `第 ${fmt(pagination.page || 1)} 页 · 共 ${fmt(pagination.total || 0)} 个模板 · ${scope.label || "全部任务"}`;
  }
  const refreshButton = $("#templateRefreshButton");
  if (refreshButton) {
    const running = Boolean(summary.refresh?.running || state.templateCandidateRefreshing);
    refreshButton.disabled = running;
    refreshButton.textContent = running ? "刷新中" : "刷新候选";
  }
  $("#templateCandidateRows").innerHTML = tableRows(rows, (row) => `
    <tr>
      <td>
        <strong>${escapeHtml(row.template_title || "-")}</strong>
        <div class="template-candidate-badges">
          ${renderTemplateSimilarityBadge(row)}
          ${renderTemplateReviewBadges(row)}
        </div>
        <div class="muted small mono">${escapeHtml(row.template_key || "-")}</div>
      </td>
      <td>${renderTemplateSlotGroups(row.token_slots)}</td>
      <td>
        <strong>${fmt(row.prompt_count)} 条提示词</strong>
        <div class="muted small">使用 ${fmt(row.use_count)} 次 · ${fmt(row.user_count)} 人 · 分 ${fmtAmount(row.quality_score)}</div>
      </td>
      <td>
        <strong>${escapeHtml(row.scope_label || "-")}</strong>
        <div class="muted small">${escapeHtml(row.model_label || row.model_key || row.parent_task_type || "-")}</div>
        <div class="muted small">${fmtDate(row.refreshed_at)}</div>
      </td>
      <td>
        <div class="template-candidate-actions">
          <label class="template-low-quality-check">
            <input
              type="checkbox"
              data-template-low-quality-template="${encodeURIComponent(row.template_key || "")}"
              ${row.low_quality ? "checked" : ""}
              ${state.templateCandidateLowQualitySaving?.[row.template_key] ? "disabled" : ""}
            />
            <span>低质量</span>
          </label>
          <button type="button" data-template-key="${encodeURIComponent(row.template_key || "")}">查看</button>
        </div>
      </td>
    </tr>
  `);
  renderPageControl("#templateCandidatePagination", pagination, "templateCandidatePageJumpInput");
}

function renderTemplateCandidateDrawer() {
  const payload = state.templateCandidatePrompts || {};
  const summary = payload.summary || state.selectedTemplateCandidate || {};
  const rows = payload.rows || [];
  const pagination = payload.pagination || {};
  $("#templateCandidateDrawerTitle").textContent = summary?.template_title || "模板候选";
  $("#templateCandidateDrawerSummary").innerHTML = [
    metric("对应提示词", fmt(summary?.prompt_count), "模板候选明细"),
    metric("使用次数", fmt(summary?.use_count), "候选提示词累计"),
    metric("使用用户", fmt(summary?.user_count), "候选提示词累计"),
    metric("质量分", fmtAmount(summary?.quality_score), summary?.scope_label || "-"),
    metric("相似度", summary?.similarity_bucket || "未计算", `分 ${fmtAmount(summary?.similarity_score)}`),
    metric(
      "已暂存",
      fmt(summary?.marked_prompt_count || 0),
      summary?.low_quality ? "低质量" : (summary?.processed ? "已处理" : "未处理")
    ),
    metric("刷新", fmtDate(summary?.refreshed_at), fmtDate(summary?.latest_prompt_at)),
  ].join("");
  $("#templateCandidatePromptPageInfo").textContent = `第 ${fmt(pagination.page || 1)} 页 · 共 ${fmt(pagination.total || 0)} 条提示词`;
  $("#templateCandidatePromptRows").innerHTML = tableRows(rows, (row) => `
    <tr>
      <td>
        <div class="template-candidate-prompt-text">${escapeHtml(row.prompt_preview || row.prompt || "-")}</div>
        <div class="muted small mono">${escapeHtml(row.prompt_hash || "-")}</div>
      </td>
      <td>
        <strong>${(row.task_types || []).map(escapeHtml).join(" / ") || "-"}</strong>
        <div class="muted small">${fmt(row.uses)} 次 · ${fmt(row.users)} 人 · 分 ${fmtAmount(row.quality_score)}</div>
        <div class="muted small">${fmtDate(row.last_seen)}</div>
      </td>
      <td>${renderTemplateSlotGroups(row.token_slots || summary?.token_slots, { maxGroups: 10, maxTokensPerGroup: 10 })}</td>
      <td class="template-review-cell">
        <label class="template-review-check">
          <input
            type="checkbox"
            data-template-review-prompt="${encodeURIComponent(row.prompt_hash || "")}"
            ${row.review_checked ? "checked" : ""}
            ${state.templateCandidateReviewSaving?.[row.prompt_hash] ? "disabled" : ""}
          />
          <span>暂存</span>
        </label>
        <div class="muted small">${row.review_checked ? fmtDate(row.review_marked_at) : ""}</div>
      </td>
    </tr>
  `);
  renderPageControl("#templateCandidatePromptPagination", pagination, "templateCandidatePromptPageJumpInput");
}

function currentTemplateReviewMarksFilterLabel(payload = state.templateReviewMarks || {}) {
  const parts = [];
  const scope = payload.scope || {};
  const search = $("#templateReviewMarksSearchInput")?.value?.trim();
  const similarity = $("#templateReviewMarksSimilaritySelect")?.value || "";
  const processed = $("#templateReviewMarksProcessedSelect")?.value || "all";
  if (scope.label && scope.key !== "all") parts.push(scope.label);
  if (similarity) parts.push(similarity);
  if (processed === "processed") parts.push("已处理");
  if (processed === "unprocessed") parts.push("未处理");
  if (search) parts.push(search);
  return parts.join(" · ") || "全部暂存";
}

function templateReviewMarkPromptText(row = {}) {
  return String(row.prompt || "").trim();
}

function templateReviewMarkRowKey(row = {}) {
  return `${row.template_key || ""}::${row.prompt_hash || ""}`;
}

function templateReviewMarksCopyText(rows = []) {
  return rows.map(templateReviewMarkPromptText).filter(Boolean).join("\n\n");
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function templateReviewMarksCsv(rows = []) {
  const header = ["模板", "相似度", "相似分", "处理状态", "处理时间", "质量分", "使用次数", "使用用户", "暂存时间", "Prompt"];
  const lines = rows.map((row) => [
    row.template_title || "",
    row.similarity_bucket || "",
    row.similarity_score ?? "",
    row.review_processed ? "已处理" : "未处理",
    row.review_processed_at || "",
    row.quality_score ?? "",
    row.uses ?? "",
    row.users ?? "",
    row.marked_at || "",
    row.prompt || "",
  ].map(csvCell).join(","));
  return [`\ufeff${header.map(csvCell).join(",")}`, ...lines].join("\n");
}

function renderTemplateReviewMarksDrawer() {
  if (!$("#templateReviewMarksDrawer")) return;
  const payload = state.templateReviewMarks || {};
  const summary = payload.summary || {};
  const rows = payload.rows || [];
  const pagination = payload.pagination || {};
  const total = Number(pagination.total || 0);
  const loaded = rows.length;
  $("#templateReviewMarksSummary").innerHTML = [
    metric("当前筛选", fmt(total), "候选审核暂存"),
    metric("已处理", fmt(summary.processed_prompt_count || 0), "暂存提示词"),
    metric("未处理", fmt(summary.unprocessed_prompt_count || 0), "暂存提示词"),
    metric("筛选", currentTemplateReviewMarksFilterLabel(payload), `当前页 ${fmt(loaded)} 条`),
  ].join("");
  const status = $("#templateReviewMarksStatus");
  if (status) {
    status.textContent = state.templateReviewMarksLoading
      ? "加载中"
      : `第 ${fmt(pagination.page || 1)} 页 · 共 ${fmt(total)} 条暂存`;
  }
  const copyStatus = $("#templateReviewMarksCopyStatus");
  if (copyStatus) copyStatus.textContent = state.templateReviewMarksCopyStatus || "";
  const copyAllButton = $("#templateReviewMarksCopyAllButton");
  if (copyAllButton) copyAllButton.disabled = state.templateReviewMarksLoading || rows.length === 0;
  const exportButton = $("#templateReviewMarksExportButton");
  if (exportButton) exportButton.disabled = state.templateReviewMarksLoading || rows.length === 0;
  const body = $("#templateReviewMarksRows");
  if (!body) return;
  if (state.templateReviewMarksLoading) {
    body.innerHTML = '<tr><td colspan="4" class="empty">加载中</td></tr>';
    renderPageControl("#templateReviewMarksPagination", pagination, "templateReviewMarksPageJumpInput");
    return;
  }
  body.innerHTML = tableRows(rows, (row) => `
    <tr>
      <td>
        <strong>${escapeHtml(row.template_title || "-")}</strong>
        <div class="template-candidate-badges">
          ${renderTemplateSimilarityBadge(row)}
          <span class="status-badge success">已暂存</span>
          ${row.review_processed ? '<span class="status-badge identity">已处理</span>' : '<span class="status-badge warn">未处理</span>'}
        </div>
        <div class="muted small mono">${escapeHtml(row.template_key || "-")}</div>
      </td>
      <td>
        <div class="template-review-mark-prompt-text">${escapeHtml(row.prompt || "-")}</div>
        <div class="muted small mono">${escapeHtml(row.prompt_hash || "-")}</div>
      </td>
      <td>
        <strong>${escapeHtml((row.task_types || []).join(" / ") || row.scope_label || "-")}</strong>
        <div class="muted small">${fmt(row.uses)} 次 · ${fmt(row.users)} 人 · 分 ${fmtAmount(row.quality_score)}</div>
        <div class="muted small">暂存 ${fmtDate(row.marked_at)}</div>
      </td>
      <td class="template-review-mark-actions">
        <label class="template-review-check">
          <input
            type="checkbox"
            data-template-review-processed-template="${encodeURIComponent(row.template_key || "")}"
            data-template-review-processed="${encodeURIComponent(row.prompt_hash || "")}"
            ${row.review_processed ? "checked" : ""}
            ${state.templateReviewMarksProcessingSaving?.[templateReviewMarkRowKey(row)] ? "disabled" : ""}
          />
          <span>已处理</span>
        </label>
        <div class="muted small">${row.review_processed ? fmtDate(row.review_processed_at) : ""}</div>
        <button
          type="button"
          data-template-review-copy-template="${encodeURIComponent(row.template_key || "")}"
          data-template-review-copy="${encodeURIComponent(row.prompt_hash || "")}"
        >复制</button>
      </td>
    </tr>
  `);
  renderPageControl("#templateReviewMarksPagination", pagination, "templateReviewMarksPageJumpInput");
}

function promptDecompositionTotalPages(pagination = state.promptDecomposition?.pagination || {}) {
  const limit = Math.max(1, Number(pagination.limit || 1));
  const total = Math.max(0, Number(pagination.total || 0));
  return Math.max(1, Math.ceil(total / limit));
}

function promptDecompositionSelectedTokens() {
  if (!Array.isArray(state.promptDecompositionSelectedTokens)) {
    state.promptDecompositionSelectedTokens = [];
  }
  return state.promptDecompositionSelectedTokens;
}

function renderPromptDecompositionGroupedTokens(groups = [], { highlightTokens = [] } = {}) {
  const normalizedGroups = Array.isArray(groups) ? groups : [];
  if (!normalizedGroups.length) return '<span class="muted">-</span>';
  const highlighted = new Set(Array.isArray(highlightTokens) ? highlightTokens : []);
  return `
    <div class="template-slot-groups">
      ${normalizedGroups.map((group) => `
        <div class="template-slot-group">
          <span class="template-slot-label">${escapeHtml(group.label || "-")}</span>
          <span class="template-slot-token-list">
            ${(Array.isArray(group.tokens) ? group.tokens : []).map((token) => (
              `<span class="pill ${highlighted.has(token) ? "active" : ""}">${escapeHtml(token)}</span>`
            )).join("") || '<span class="muted small">-</span>'}
          </span>
        </div>
      `).join("")}
    </div>
  `;
}

function renderPromptDecompositionSelectedTokenBar() {
  const container = $("#promptDecompositionSelectedTokenBar");
  if (!container) return;
  const selected = promptDecompositionSelectedTokens();
  if (!selected.length) {
    container.innerHTML = '<div class="muted small">已选标签：无。当前仅展示已分类且提示词数不少于 20 的自由P图标签。</div>';
    return;
  }
  container.innerHTML = `
    <div class="prompt-decomposition-selected-wrap">
      <div class="muted small">已选标签</div>
      <div class="prompt-decomposition-selected-chip-list">
        ${selected.map((token) => `
          <button class="prompt-decomposition-selected-chip" type="button" data-remove-token="${encodeURIComponent(token)}">
            <span>${escapeHtml(token)}</span>
            <span aria-hidden="true">×</span>
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function renderPromptDecompositionFacets() {
  const container = $("#promptDecompositionFacetGrid");
  if (!container) return;
  const groups = state.promptDecomposition?.filters?.groups || [];
  if (!groups.length) {
    container.innerHTML = '<div class="empty">当前没有可用的自由P图标签筛选</div>';
    return;
  }
  const selected = new Set(promptDecompositionSelectedTokens());
  container.innerHTML = groups.map((group) => {
    const subgroups = Array.isArray(group.subgroups) ? group.subgroups : [];
    const activeKey = state.promptDecompositionActiveSubgroups?.[group.key] || subgroups[0]?.key || "";
    const activeSubgroup = subgroups.find((item) => item.key === activeKey) || subgroups[0] || { tokens: [] };
    state.promptDecompositionActiveSubgroups[group.key] = activeSubgroup.key || "";
    return `
      <section class="prompt-decomposition-facet-card" data-group-key="${escapeHtml(group.key || "")}">
        <div class="prompt-decomposition-facet-head">
          <div>
            <div class="table-title">${escapeHtml(group.label || "-")}</div>
            <div class="muted small">${escapeHtml(group.note || "")}</div>
          </div>
          <div class="muted small">${fmt(group.token_count || 0)} 个标签</div>
        </div>
        <div class="prompt-decomposition-subgroup-tabs">
          ${subgroups.map((subgroup) => `
            <button
              type="button"
              class="rule-category-tab ${subgroup.key === activeSubgroup.key ? "active" : ""}"
              data-group-key="${escapeHtml(group.key || "")}"
              data-subgroup-key="${escapeHtml(subgroup.key || "")}"
            >
              ${escapeHtml(subgroup.label || "-")}
              <strong>${fmt(subgroup.token_count || 0)}</strong>
            </button>
          `).join("")}
        </div>
        <div class="prompt-decomposition-token-cloud">
          ${(Array.isArray(activeSubgroup.tokens) ? activeSubgroup.tokens : []).map((item) => `
            <button
              type="button"
              class="prompt-decomposition-token-pill ${selected.has(item.token) ? "active" : ""}"
              data-toggle-token="${encodeURIComponent(item.token || "")}"
              title="提示词 ${fmt(item.prompt_count)} 条 · 使用 ${fmt(item.use_count)} 次 · ${fmt(item.user_count)} 人"
            >
              <span>${escapeHtml(item.token || "-")}</span>
              <strong>${fmt(item.prompt_count || 0)}</strong>
            </button>
          `).join("") || '<span class="muted small">该二级项暂无可筛词元</span>'}
        </div>
      </section>
    `;
  }).join("");
}

function renderPromptDecompositionRows() {
  const payload = state.promptDecomposition || {};
  const rows = payload.rows || [];
  const pagination = payload.pagination || {};
  $("#promptDecompositionPageInfo").textContent = `第 ${fmt(pagination.page || 1)} 页 · 共 ${fmt(pagination.total || 0)} 条提示词`;
  $("#promptDecompositionRows").innerHTML = tableRows(rows, (row) => `
    <tr class="${state.selectedPromptDecomposition?.prompt_hash === row.prompt_hash ? "selected-row" : ""}">
      <td>
        <div class="prompt-token-prompt-text">${escapeHtml(row.prompt_preview || row.prompt || "-")}</div>
        <div class="muted small mono">${escapeHtml(row.prompt_hash || "-")}</div>
      </td>
      <td>${renderPromptDecompositionGroupedTokens(row.grouped_tokens || [], { highlightTokens: row.matched_tokens || [] })}</td>
      <td>
        <strong>${fmt(row.uses)} 次 · ${fmt(row.users)} 人</strong>
        <div class="muted small">分 ${fmtAmount(row.quality_score)} · ${fmtDate(row.last_seen)}</div>
      </td>
      <td>
        <button type="button" data-open-decomposition="${encodeURIComponent(row.prompt_hash || "")}" data-source="live">查看</button>
      </td>
    </tr>
  `);
  renderPageControl("#promptDecompositionPagination", pagination, "promptDecompositionPageJumpInput");
}

function renderPromptDecompositionSaved() {
  const payload = state.promptDecompositionSaved || { rows: [], total: 0 };
  const rows = payload.rows || [];
  const status = $("#promptDecompositionSavedStatus");
  if (status) {
    status.textContent = state.promptDecompositionSavedLoading
      ? "正在加载优秀模板沉淀"
      : `已保存 ${fmt(payload.total || 0)} 条优秀模板，当前展示最近 ${fmt(Math.min(rows.length, PROMPT_DECOMPOSITION_SAVED_LIMIT))} 条`;
  }
  $("#promptDecompositionSavedRows").innerHTML = tableRows(rows, (row) => `
    <tr class="${state.selectedPromptDecomposition?.prompt_hash === row.prompt_hash ? "selected-row" : ""}">
      <td>
        <strong>${escapeHtml(row.title || "-")}</strong>
        <div class="muted small mono">${escapeHtml(row.prompt_hash || "-")}</div>
      </td>
      <td>${renderTokenPills(row.selected_tokens || [], { limit: 18 })}</td>
      <td>
        <div class="prompt-token-prompt-text">${escapeHtml(row.prompt_preview || row.prompt || "-")}</div>
        <div class="muted small">${fmt(row.uses)} 次 · ${fmt(row.users)} 人 · 分 ${fmtAmount(row.quality_score)}</div>
      </td>
      <td>
        <strong>${fmtDate(row.updated_at)}</strong>
        <div class="muted small">${fmtDate(row.last_seen)}</div>
      </td>
      <td>
        <div class="inline-actions prompt-token-row-actions">
          <button type="button" data-open-decomposition="${encodeURIComponent(row.prompt_hash || "")}" data-source="saved">查看</button>
          <button type="button" data-delete-saved-template="${row.id}">删除</button>
        </div>
      </td>
    </tr>
  `);
}

function renderPromptDecompositionDrawer() {
  const row = state.selectedPromptDecomposition || {};
  $("#promptDecompositionDrawerTitle").textContent = row.title || "自由P图提示词拆解";
  $("#promptDecompositionDrawerSummary").innerHTML = [
    metric("使用次数", fmt(row.uses), "该提示词累计使用"),
    metric("使用用户", fmt(row.users), "触达用户数"),
    metric("质量分", fmtAmount(row.quality_score), fmtDate(row.last_seen)),
    metric("当前筛选", fmt((row.matched_tokens || []).length), (row.matched_tokens || []).join(" / ") || "无标签筛选"),
    metric("已拆分标签", fmt((row.tokens || []).length), "基于当前规则体系"),
  ].join("");
  const input = $("#promptDecompositionSaveTitleInput");
  if (input) {
    const currentValue = state.promptDecompositionSaveTitle || row.title || "";
    if (input.value !== currentValue) input.value = currentValue;
    input.disabled = state.promptDecompositionSaving;
  }
  const saveButton = $("#promptDecompositionSaveButton");
  if (saveButton) {
    saveButton.disabled = !row.prompt_hash || state.promptDecompositionSaving;
    saveButton.textContent = state.promptDecompositionSaving ? "保存中" : "保存优秀模板";
  }
  $("#promptDecompositionDrawerPrompt").textContent = row.prompt || row.prompt_preview || "-";
  $("#promptDecompositionDrawerGroups").innerHTML = renderPromptDecompositionGroupedTokens(
    row.grouped_tokens || [],
    { highlightTokens: row.matched_tokens || [] }
  );
}

function renderPromptDecomposition() {
  const payload = state.promptDecomposition || {};
  const summary = payload.summary || {};
  $("#promptDecompositionSummary").innerHTML = [
    metric("自由P图候选提示词", fmt(summary.candidate_count), "quality_stage = candidate"),
    metric("当前命中", fmt(summary.matched_prompt_count), promptDecompositionSelectedTokens().length ? "多标签交集结果" : "全部自由P图"),
    metric("已选标签", fmt(summary.token_filter_count), `仅展示词元表中 prompt_count >= ${fmt(summary.min_token_prompt_count || 20)} 的分类标签`),
    metric("优秀模板沉淀", fmt(summary.saved_template_count), "人工保存的高质量提示词"),
    metric("刷新", fmtDate(summary.refreshed_at), payload.scope?.label || "自由P图"),
  ].join("");
  const status = $("#promptDecompositionFilterStatus");
  if (status) {
    status.textContent = payload.ready === false
      ? (payload.message || "提示词拆解尚未准备好")
      : "仅展示已分类标签；未分类词元不进入该页筛选器。";
  }
  renderPromptDecompositionSelectedTokenBar();
  renderPromptDecompositionFacets();
  renderPromptDecompositionRows();
  renderPromptDecompositionSaved();
  if ($("#promptDecompositionDrawer")?.classList.contains("open")) {
    renderPromptDecompositionDrawer();
  }
}

function renderMediaRefs(refs = []) {
  const items = Array.isArray(refs) ? refs.filter(Boolean).slice(0, 3) : [];
  if (!items.length) return '<span class="muted">-</span>';
  return items.map((ref) => `<div class="mono small">${escapeHtml(ref)}</div>`).join("");
}

function renderMedia() {
  const totals = state.media?.totals || {};
  $("#mediaSummary").innerHTML = [
    metric("输入引用", fmt(totals.input_refs), `输出 ${fmt(totals.output_refs)}`),
    metric("图片", fmt(totals.images), "输入输出合计"),
    metric("视频", fmt(totals.videos), "输入输出合计"),
    metric("有输出", fmt(totals.with_output), escapeHtml(state.media?.media_bucket || "-")),
  ].join("");

  $("#mediaRows").innerHTML = tableRows(state.media?.records, (row) => `
    <tr>
      <td>${fmtDate(row.created_at)}</td>
      <td>
        <strong class="mono">${escapeHtml(row.task_type || "-")}</strong>
        <div class="muted small">${escapeHtml(row.source || "-")}</div>
      </td>
      <td>${renderMediaRefs(row.input_refs)}</td>
      <td>
        ${renderMediaRefs(row.output_refs)}
        ${row.primary_output_url ? `<a class="muted small" href="${escapeHtml(row.primary_output_url)}" target="_blank" rel="noreferrer">打开输出</a>` : ""}
      </td>
      <td>
        <strong>${fmt(row.width)} × ${fmt(row.height)}</strong>
        <div class="muted small">${row.duration ? `${fmtAmount(row.duration, " 秒")}` : "-"}</div>
      </td>
    </tr>
  `);
}

const promptSlimStageLabels = {
  auto_rejected: "自动剔除",
  candidate: "候选",
  manual_keep: "人工保留",
  manual_reject: "人工剔除",
  excellent: "优秀",
  archived: "归档",
};

const promptSlimSourceLabels = {
  natural: "自然输入",
  source_template: "源模板",
};

function parseObject(value) {
  if (!value) return {};
  if (typeof value === "object" && !Array.isArray(value)) return value;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch (_) {
      return {};
    }
  }
  return {};
}

function promptSlimStageLabel(stage) {
  return promptSlimStageLabels[stage] || stage || "-";
}

function promptSlimStageClass(stage) {
  if (stage === "candidate" || stage === "manual_keep" || stage === "excellent") return "success";
  if (stage === "auto_rejected" || stage === "manual_reject") return "danger";
  return "neutral";
}

function promptSlimSourceLabel(source) {
  return promptSlimSourceLabels[source] || source || "-";
}

function renderPromptSlimOptionSet(selector, rows = [], staticOptions = []) {
  const select = $(selector);
  if (!select) return;
  const existing = select.value;
  const seen = new Set();
  const options = [];
  staticOptions.concat(rows.map((row) => ({ value: row.label, label: row.label }))).forEach((option) => {
    if (option.value === undefined || option.value === null || seen.has(option.value)) return;
    seen.add(option.value);
    options.push(`<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`);
  });
  if (existing && !seen.has(existing)) {
    options.push(`<option value="${escapeHtml(existing)}">${escapeHtml(existing)}</option>`);
  }
  select.innerHTML = options.join("");
  select.value = existing && Array.from(select.options).some((option) => option.value === existing)
    ? existing
    : staticOptions[0]?.value || "";
}

function renderPromptSlimFilterOptions() {
  const distributions = state.promptSlim?.distributions || {};
  renderPromptSlimOptionSet(
    "#promptSlimTaskTypeSelect",
    distributions.task_type || [],
    [{ value: "", label: "全部" }]
  );
  renderPromptSlimOptionSet(
    "#promptSlimReasonSelect",
    (distributions.reason || []).filter((row) => row.label !== "无"),
    [
      { value: "all", label: "全部" },
      { value: "too_short", label: "too_short" },
      { value: "short_oneoff", label: "short_oneoff" },
      { value: "symbol_or_digit_only", label: "symbol_or_digit_only" },
      { value: "known_junk", label: "known_junk" },
    ]
  );
}

function renderPromptSlimSummary() {
  const summary = state.promptSlim?.summary || {};
  $("#promptSlimSummary").innerHTML = [
    metric("瘦身表提示词", fmt(summary.slim_prompts), `候选 ${fmt(summary.candidate_prompts)} · 自动剔除 ${fmt(summary.auto_rejected_prompts)}`),
    metric("使用信号", fmt(summary.uses), `用户引用 ${fmt(summary.user_refs)}`),
    metric("字数", fmtAmount(summary.avg_chars), `中位 ${fmtAmount(summary.median_chars)} 字`),
    metric("生成反馈", `${fmt(summary.result_likes)} / ${fmt(summary.result_dislikes)}`, "点赞 / 点踩"),
    metric("Gallery 信号", fmt(summary.gallery_applies), `赞 ${fmt(summary.gallery_likes)} · 踩 ${fmt(summary.gallery_dislikes)}`),
    metric("Prompt 解锁", fmt(summary.prompt_unlocks), `刷新 ${fmtDate(summary.latest_refreshed_at)}`),
  ].join("");
}

function renderPromptSlimDistributions() {
  const distributions = state.promptSlim?.distributions || {};
  renderDistribution("#promptSlimStageDistribution", (distributions.stage || []).map((row) => ({
    ...row,
    label: promptSlimStageLabel(row.label),
  })));
  renderDistribution("#promptSlimReasonDistribution", distributions.reason || []);
  renderDistribution("#promptSlimTaskTypeDistribution", distributions.task_type || []);
  renderDistribution("#promptSlimSourceDistribution", (distributions.source_scope || []).map((row) => ({
    ...row,
    label: promptSlimSourceLabel(row.label),
  })));
  renderDistribution("#promptSlimLengthDistribution", distributions.length || []);
}

function renderCountPills(value, labelMap = {}) {
  const entries = Object.entries(parseObject(value)).sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));
  if (!entries.length) return '<span class="muted">-</span>';
  return `<div class="pill-list">${entries.slice(0, 6).map(([key, count]) => `
    <span class="pill gray">${escapeHtml(labelMap[key] || key)} ${fmt(count)}</span>
  `).join("")}</div>`;
}

function renderReasonPills(row = {}) {
  const reasons = row.low_quality_reasons || [];
  if (!reasons.length) return '<span class="pill gray">无</span>';
  return reasons.slice(0, 4).map((reason) => `<span class="pill amber">${escapeHtml(reason)}</span>`).join("");
}

function renderUserIdSample(ids = [], count = 0) {
  const total = Number(count || 0);
  if (!total) return "-";
  const sample = (ids || []).slice(0, 10).map((id) => `<span class="mono">${escapeHtml(id)}</span>`).join(" ");
  return `${fmt(total)} 人${sample ? `<div class="muted small user-id-sample">${sample}</div>` : ""}`;
}

function renderPromptSlimSignalText(row = {}) {
  return `
    <div>结果赞 ${fmt(row.result_likes)} · 踩 ${fmt(row.result_dislikes)}</div>
    <div class="muted small">点赞用户 ${fmt(row.result_like_user_count)} · 点踩用户 ${fmt(row.result_dislike_user_count)}</div>
  `;
}

function renderPromptSlimGalleryText(row = {}) {
  return `
    <div>应用 ${fmt(row.gallery_applies)} · 解锁 ${fmt(row.prompt_unlocks)}</div>
    <div class="muted small">赞 ${fmt(row.gallery_likes)} · 踩 ${fmt(row.gallery_dislikes)} · 评 ${fmt(row.gallery_comments)}</div>
  `;
}

function renderPromptSlim() {
  renderPromptSlimFilterOptions();
  renderPromptSlimSummary();
  renderPromptSlimDistributions();

  const rows = state.promptSlim?.rows || [];
  if (!state.selectedPromptSlim || !rows.some((item) => item.prompt_hash === state.selectedPromptSlim.prompt_hash)) {
    state.selectedPromptSlim = rows[0] || null;
  }

  $("#promptSlimRows").innerHTML = tableRows(rows, (row) => `
    <tr data-prompt-hash="${escapeHtml(row.prompt_hash)}">
      <td>
        <span class="status-badge ${promptSlimStageClass(row.quality_stage)}">${escapeHtml(promptSlimStageLabel(row.quality_stage))}</span>
        <div><strong class="signal-score">${fmtAmount(row.quality_score)}</strong></div>
        <div class="muted small">正 ${fmtAmount(row.positive_signal_score)} · 负 ${fmtAmount(row.negative_signal_score)}</div>
      </td>
      <td>
        <div class="prompt-preview">${escapeHtml(row.prompt_preview)}</div>
        <div class="muted small">代表原文：${escapeHtml(row.raw_prompt_preview || "-")}</div>
        <div class="pill-list">
          ${(row.source_scopes || []).slice(0, 2).map((source) => `<span class="pill gray">${escapeHtml(promptSlimSourceLabel(source))}</span>`).join("")}
          ${Number(row.variant_count || 1) > 1 ? `<span class="pill">变体 ${fmt(row.variant_count)}</span>` : ""}
        </div>
      </td>
      <td>
        <strong>${fmt(row.uses)}</strong> 次
        <div class="muted small">${fmt(row.users)} 人 · ${(row.task_types || []).slice(0, 3).map(escapeHtml).join(" / ") || "-"}</div>
      </td>
      <td>${renderPromptSlimSignalText(row)}</td>
      <td>${renderPromptSlimGalleryText(row)}</td>
      <td>
        <div class="pill-list">${renderReasonPills(row)}</div>
        <div class="muted small">${fmtDate(row.last_seen)}</div>
      </td>
    </tr>
  `);

  document.querySelectorAll("#promptSlimRows tr").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedPromptSlim = rows.find((item) => item.prompt_hash === row.dataset.promptHash) || rows[0] || null;
      renderPromptSlimDetail();
    });
  });

  const pagination = state.promptSlim?.pagination || {};
  const total = Number(pagination.total || 0);
  $("#promptSlimPageInfo").textContent = `第 ${fmt(pagination.page || 1)} 页 · 共 ${fmt(total)} 组`;
  $("#promptSlimPrevButton").disabled = Number(pagination.page || 1) <= 1;
  $("#promptSlimNextButton").disabled = !pagination.has_next;

  renderPromptSlimDetail();
}

function renderPromptSlimDetail() {
  const item = state.selectedPromptSlim;
  if (!item) {
    $("#promptSlimDetail").innerHTML = '<div class="empty">暂无提示词</div>';
    return;
  }
  $("#promptSlimDetail").innerHTML = `
    <h3>${escapeHtml(promptSlimStageLabel(item.quality_stage))} · 质量 ${fmtAmount(item.quality_score)}</h3>
    <p class="prompt-fulltext">${escapeHtml(item.prompt || item.prompt_preview)}</p>
    <dl>
      <dt>Hash</dt><dd class="mono">${escapeHtml(item.prompt_hash)}</dd>
      <dt>代表原文</dt><dd>${escapeHtml(item.raw_prompt_representative || "-")}</dd>
      <dt>版本</dt><dd>${escapeHtml(item.normalization_version || "-")} · ${escapeHtml(item.rule_version || "-")}</dd>
      <dt>变体</dt><dd>${fmt(item.variant_count || 1)} 种 · 字数 ${fmt(item.char_count)}</dd>
      <dt>复用</dt><dd>${fmt(item.uses)} 次 / ${fmt(item.users)} 人</dd>
      <dt>任务</dt><dd>${renderCountPills(item.task_type_counts)}</dd>
      <dt>来源</dt><dd>${renderCountPills(item.source_counts, promptSlimSourceLabels)}</dd>
      <dt>规则原因</dt><dd><div class="pill-list">${renderReasonPills(item)}</div></dd>
      <dt>生成反馈</dt><dd>赞 ${fmt(item.result_likes)} / 踩 ${fmt(item.result_dislikes)}</dd>
      <dt>Gallery</dt><dd>投稿 ${fmt(item.gallery_posts)} · 应用 ${fmt(item.gallery_applies)} · 赞 ${fmt(item.gallery_likes)} · 踩 ${fmt(item.gallery_dislikes)} · 评论 ${fmt(item.gallery_comments)}</dd>
      <dt>解锁</dt><dd>${fmt(item.prompt_unlocks)}</dd>
      <dt>使用用户</dt><dd>${renderUserIdSample(item.using_user_ids_sample, item.using_user_count)}</dd>
      <dt>结果点赞</dt><dd>${renderUserIdSample(item.result_like_user_ids_sample, item.result_like_user_count)}</dd>
      <dt>结果点踩</dt><dd>${renderUserIdSample(item.result_dislike_user_ids_sample, item.result_dislike_user_count)}</dd>
      <dt>应用用户</dt><dd>${renderUserIdSample(item.gallery_apply_user_ids_sample, item.gallery_apply_user_count)}</dd>
      <dt>解锁用户</dt><dd>${renderUserIdSample(item.prompt_unlock_user_ids_sample, item.prompt_unlock_user_count)}</dd>
      <dt>时间</dt><dd>${fmtDate(item.first_seen)} - ${fmtDate(item.last_seen)}</dd>
      <dt>人工备注</dt><dd>${escapeHtml(item.review_note || "-")}</dd>
      <dt>刷新</dt><dd>${fmtDate(item.refreshed_at)}</dd>
    </dl>
  `;
}

function renderPromptVectorSummary() {
  const summary = state.promptVectors?.summary || {};
  const model = state.promptVectors?.model || {};
  if (state.promptVectors && state.promptVectors.ready === false) {
    $("#promptVectorSummary").innerHTML = [
      metric("向量表状态", "未构建", state.promptVectors.message || "等待刷新命令"),
      metric("模型", escapeHtml(model.model_id || "-"), escapeHtml(model.model_key || "-")),
      metric("候选覆盖", "0%", "先运行 pilot 或全量向量化"),
      metric("待向量化", "0", "等待基础表"),
    ].join("");
    return;
  }
  $("#promptVectorSummary").innerHTML = [
    metric("候选提示词", fmt(summary.candidate_count), "quality_stage = candidate"),
    metric("已向量化", fmt(summary.embedded_count), `覆盖 ${fmtAmount(summary.embedding_coverage)}%`),
    metric("待向量化", fmt(summary.pending_count), `失败 ${fmt(summary.failed_count)}`),
    metric("模型", escapeHtml(model.model_id || "-"), `维度 ${fmt(model.embedding_dim)}`),
    metric(
      "刷新",
      fmtDate(summary.latest_embedded_at || model.last_success_at),
      model.last_error ? `错误 ${model.last_error}` : "仅保留基础向量",
    ),
  ].join("");
}

function renderPromptVectorDistributions() {
  const distributions = state.promptVectors?.distributions || {};
  renderDistribution("#promptVectorTaskTypeDistribution", distributions.task_type || []);
  renderDistribution("#promptVectorStatusDistribution", distributions.status || []);
}

function renderPromptVectors() {
  renderPromptVectorSummary();
  renderPromptVectorResumeStatus();
  renderPromptVectorDistributions();
}

function tokenKindLabel(kind) {
  if (kind === "cjk") return "中文";
  if (kind === "mixed") return "混合";
  if (kind === "unicode") return "多语言";
  return "英文";
}

function renderTokenPills(tokens = [], { selectedToken = "", limit = 28 } = {}) {
  const visible = (Array.isArray(tokens) ? tokens : []).filter(Boolean).slice(0, limit);
  if (!visible.length) return '<span class="muted">-</span>';
  const pills = visible.map((token) => {
    const active = token === selectedToken ? " active" : "";
    return `<span class="pill${active}">${escapeHtml(token)}</span>`;
  });
  const hiddenCount = Math.max(0, (tokens || []).length - visible.length);
  if (hiddenCount) {
    pills.push(`<span class="pill neutral">另 ${fmt(hiddenCount)} 个</span>`);
  }
  return `<div class="pill-list prompt-token-pill-list">${pills.join("")}</div>`;
}

function promptTokenCustomTermRows() {
  if (!state.promptTokenCustomTerms) {
    state.promptTokenCustomTerms = { rows: [], status: {} };
  }
  if (!Array.isArray(state.promptTokenCustomTerms.rows)) {
    state.promptTokenCustomTerms.rows = [];
  }
  return state.promptTokenCustomTerms.rows;
}

function promptTokenRuleCategoryLabel(row = {}) {
  return row.category_label || row.category_key || "-";
}

function promptTokenRuleSubcategoryLabel(row = {}) {
  return row.subcategory_label || row.subcategory_key || "-";
}

function promptTokenRuleCategoryValue(row = {}) {
  return row.category_label || row.category_key || PROMPT_TOKEN_UNCATEGORIZED_CATEGORY;
}

function promptTokenRuleCategoryText(row = {}) {
  return row.category_label || row.category_key || "未分类";
}

function promptTokenRuleSubcategoryValue(row = {}) {
  return row.subcategory_label || row.subcategory_key || PROMPT_TOKEN_UNCATEGORIZED_CATEGORY;
}

function promptTokenRuleSubcategoryText(row = {}) {
  return row.subcategory_label || row.subcategory_key || "未分类";
}

function promptTokenRuleCategories(rows = []) {
  const categories = [];
  const seen = new Set();
  rows.forEach((row) => {
    const value = promptTokenRuleCategoryValue(row);
    const label = promptTokenRuleCategoryText(row);
    if (!seen.has(value)) {
      seen.add(value);
      categories.push({
        value,
        label,
        count: 0,
        category_key: row.category_key || "",
        category_label: row.category_label || "",
      });
    }
    const item = categories.find((category) => category.value === value);
    if (item) item.count += 1;
  });
  categories.sort((a, b) => {
    if (a.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY) return 1;
    if (b.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY) return -1;
    return a.label.localeCompare(b.label, "zh-CN");
  });
  return [
    { value: "", label: "全部", count: rows.length, category_key: "", category_label: "" },
    ...categories,
  ];
}

function promptTokenRuleSubcategories(rows = []) {
  const subcategories = [];
  const seen = new Set();
  rows.forEach((row) => {
    const value = promptTokenRuleSubcategoryValue(row);
    const label = promptTokenRuleSubcategoryText(row);
    if (!seen.has(value)) {
      seen.add(value);
      subcategories.push({
        value,
        label,
        count: 0,
        subcategory_key: row.subcategory_key || "",
        subcategory_label: row.subcategory_label || "",
      });
    }
    const item = subcategories.find((subcategory) => subcategory.value === value);
    if (item) item.count += 1;
  });
  subcategories.sort((a, b) => {
    if (a.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY) return 1;
    if (b.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY) return -1;
    return a.label.localeCompare(b.label, "zh-CN");
  });
  return [
    { value: "", label: "全部子分类", count: rows.length, subcategory_key: "", subcategory_label: "" },
    ...subcategories,
  ];
}

function promptTokenRuleCategoryExists(rows = [], value = "") {
  if (!value) return true;
  return rows.some((row) => promptTokenRuleCategoryValue(row) === value);
}

function promptTokenRuleCategoryForValue(rows = [], value = "") {
  return promptTokenRuleCategories(rows).find((category) => category.value === value) || null;
}

function promptTokenRuleSubcategoryExists(rows = [], value = "") {
  if (!value) return true;
  return rows.some((row) => promptTokenRuleSubcategoryValue(row) === value);
}

function promptTokenRuleSubcategoryForValue(rows = [], value = "") {
  return promptTokenRuleSubcategories(rows).find((subcategory) => subcategory.value === value) || null;
}

function renderPromptTokenRuleCategoryTabs(selector, rows, activeValue) {
  const container = $(selector);
  if (!container) return "";
  const safeActive = promptTokenRuleCategoryExists(rows, activeValue) ? activeValue : "";
  const tabs = promptTokenRuleCategories(rows);
  container.innerHTML = tabs.map((tab) => {
    const active = tab.value === safeActive;
    return `
      <button
        class="rule-category-tab ${active ? "active" : ""}"
        type="button"
        role="tab"
        aria-selected="${active ? "true" : "false"}"
        data-category="${escapeHtml(tab.value)}"
        title="${escapeHtml(tab.label)}"
      >
        <span>${escapeHtml(tab.label)}</span>
        <strong>${fmt(tab.count)}</strong>
      </button>
    `;
  }).join("");
  return safeActive;
}

function renderPromptTokenRuleSubcategoryTabs(selector, rows, activeValue, visible = true) {
  const container = $(selector);
  if (!container) return "";
  if (!visible) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return "";
  }
  container.classList.remove("hidden");
  const safeActive = promptTokenRuleSubcategoryExists(rows, activeValue) ? activeValue : "";
  const tabs = promptTokenRuleSubcategories(rows);
  container.innerHTML = tabs.map((tab) => {
    const active = tab.value === safeActive;
    return `
      <button
        class="rule-category-tab rule-subcategory-tab ${active ? "active" : ""}"
        type="button"
        role="tab"
        aria-selected="${active ? "true" : "false"}"
        data-subcategory="${escapeHtml(tab.value)}"
        title="${escapeHtml(tab.label)}"
      >
        <span>${escapeHtml(tab.label)}</span>
        <strong>${fmt(tab.count)}</strong>
      </button>
    `;
  }).join("");
  return safeActive;
}

function filteredPromptTokenCustomTermRows() {
  const allRows = promptTokenCustomTermRows();
  const categoryFilter = state.promptTokenCustomTermCategoryFilter || "";
  const subcategoryFilter = state.promptTokenCustomTermSubcategoryFilter || "";
  return allRows
    .map((row, index) => ({ row, index }))
    .filter((item) => promptTokenCustomTermRowMatchesSearch(item.row))
    .filter((item) => !categoryFilter || promptTokenRuleCategoryValue(item.row) === categoryFilter)
    .filter((item) => !subcategoryFilter || promptTokenRuleSubcategoryValue(item.row) === subcategoryFilter);
}

function filteredPromptTokenAliasRows() {
  const allRows = promptTokenAliasRows();
  const categoryFilter = state.promptTokenAliasCategoryFilter || "";
  return allRows
    .map((row, index) => ({ row, index }))
    .filter((item) => promptTokenAliasRowMatchesSearch(item.row))
    .filter((item) => !categoryFilter || promptTokenRuleCategoryValue(item.row) === categoryFilter);
}

function promptTokenRuleSearchTerms(value = "") {
  return String(value || "")
    .trim()
    .toLocaleLowerCase()
    .split(/\s+/)
    .filter(Boolean);
}

function promptTokenRuleSearchText(parts = []) {
  return parts
    .flatMap((part) => Array.isArray(part) ? part : [part])
    .filter((part) => part !== null && part !== undefined)
    .map((part) => String(part))
    .join(" ")
    .toLocaleLowerCase();
}

function promptTokenRuleMatchesSearch(text, query) {
  const terms = promptTokenRuleSearchTerms(query);
  if (!terms.length) return true;
  return terms.every((term) => text.includes(term));
}

function promptTokenCustomTermRowMatchesSearch(row = {}) {
  const query = state.promptTokenCustomTermSearch || "";
  if (!promptTokenRuleSearchTerms(query).length) return true;
  return promptTokenRuleMatchesSearch(
    promptTokenRuleSearchText([
      row.term,
      row.category_label,
      row.category_key,
      row.subcategory_label,
      row.subcategory_key,
      row.notes,
      row.source,
      row.seed_batch,
    ]),
    query
  );
}

function promptTokenCustomTermRowsMatchingSearch(rows = []) {
  return rows.filter((row) => promptTokenCustomTermRowMatchesSearch(row));
}

function promptTokenAliasRowMatchesSearch(row = {}) {
  const query = state.promptTokenAliasSearch || "";
  if (!promptTokenRuleSearchTerms(query).length) return true;
  return promptTokenRuleMatchesSearch(
    promptTokenRuleSearchText([
      row.representative,
      row.aliases_text,
      row.aliases,
      row.category_label,
      row.category_key,
      row.subcategory_label,
      row.subcategory_key,
      row.source,
      row.seed_batch,
    ]),
    query
  );
}

function promptTokenAliasRowsMatchingSearch(rows = []) {
  return rows.filter((row) => promptTokenAliasRowMatchesSearch(row));
}

function renderPromptTokenRuleSeedStatus() {
  const report = state.promptTokenRuleSeedReport;
  const statusEl = $("#promptTokenRuleSeedStatus");
  if (!statusEl) return;
  if (state.promptTokenRuleSeedsOverwriting) {
    statusEl.textContent = "正在全量生成并覆盖词元规则";
    return;
  }
  if (!report) {
    statusEl.textContent = "可一键基于当前全部词元生成分类指定词元和同义映射";
    return;
  }
  const coverage = report.coverage || {};
  statusEl.textContent = `上次覆盖 ${fmt(report.custom_term_count)} 个指定词元 · ${fmt(report.alias_rule_count)} 组映射 · 拆解 ${fmt(coverage.decomposed || 0)} 个长词元 · 保留 ${fmt(coverage.retained_independent || 0)} 个独立词元`;
}

function renderPromptTokenCustomTermControls() {
  const payload = state.promptTokenCustomTerms || {};
  const rows = payload.rows || [];
  const status = payload.status || {};
  const resumeRunning = Boolean(status.resume?.running);
  let text = "暂无指定词元";
  const loaded = Boolean(state.promptTokenCustomTerms);
  if (state.promptTokenCustomTermsLoading) {
    text = "正在加载指定词元表";
  } else if (!loaded) {
    text = "正在准备指定词元表";
  } else if (state.promptTokenRuleSeedsOverwriting) {
    text = "正在覆盖规则";
  } else if (state.promptTokenCustomTermsSaving) {
    text = "保存中";
  } else if (state.promptTokenCustomTermsRebuilding) {
    text = "正在提交重建";
  } else if (state.promptTokenCustomTermsDirty) {
    text = "有未保存修改";
  } else if (resumeRunning) {
    text = "词元重建或向量化任务运行中";
  } else if (status.pending) {
    text = `指定词元已保存，待重建生效 · ${fmtDate(status.rules_updated_at)}`;
  } else if (status.last_applied_at) {
    text = `已生效 · ${fmtDate(status.last_applied_at)}`;
  } else if (rows.length) {
    text = "已保存，等待首次重建";
  }
  const statusEl = $("#promptTokenCustomTermStatus");
  if (statusEl) statusEl.textContent = text;
  const addButton = $("#promptTokenCustomTermAddButton");
  if (addButton) addButton.disabled = !loaded || state.promptTokenCustomTermsLoading || state.promptTokenRuleSeedsOverwriting;
  const saveButton = $("#promptTokenCustomTermSaveButton");
  if (saveButton) saveButton.disabled = !loaded || state.promptTokenCustomTermsSaving || state.promptTokenRuleSeedsOverwriting;
  const overwriteButton = $("#promptTokenRuleSeedOverwriteButton");
  if (overwriteButton) {
    overwriteButton.disabled = state.promptTokenRuleSeedsOverwriting || state.promptTokenCustomTermsSaving || state.promptTokenAliasesSaving || resumeRunning;
  }
  const rebuildButton = $("#promptTokenCustomTermRebuildButton");
  if (rebuildButton) {
    rebuildButton.disabled = !loaded || state.promptTokenRuleSeedsOverwriting || state.promptTokenCustomTermsSaving || state.promptTokenCustomTermsRebuilding || resumeRunning;
  }
  renderPromptTokenRuleSeedStatus();
  if (resumeRunning) {
    schedulePromptTokenCustomTermPoll();
  }
}

function renderPromptTokenCustomTerms() {
  if (!state.promptTokenCustomTerms) {
    renderPromptTokenRuleCategoryTabs("#promptTokenCustomTermCategoryTabs", [], "");
    renderPromptTokenRuleSubcategoryTabs("#promptTokenCustomTermSubcategoryTabs", [], "", false);
    $("#promptTokenCustomTermRows").innerHTML = `
      <tr><td colspan="3" class="empty">${state.promptTokenCustomTermsLoading ? "正在加载指定词元表" : "正在准备指定词元表"}</td></tr>
    `;
    renderPageControl("#promptTokenCustomTermPagination", { page: 1, limit: PROMPT_TOKEN_RULE_PAGE_SIZE, total: 0 }, "promptTokenCustomTermPageJumpInput");
    renderPromptTokenCustomTermControls();
    return;
  }
  const allRows = promptTokenCustomTermRows();
  const searchedRows = promptTokenCustomTermRowsMatchingSearch(allRows);
  state.promptTokenCustomTermCategoryFilter = renderPromptTokenRuleCategoryTabs(
    "#promptTokenCustomTermCategoryTabs",
    searchedRows,
    state.promptTokenCustomTermCategoryFilter || ""
  );
  const categoryRows = state.promptTokenCustomTermCategoryFilter
    ? searchedRows.filter((row) => promptTokenRuleCategoryValue(row) === state.promptTokenCustomTermCategoryFilter)
    : [];
  state.promptTokenCustomTermSubcategoryFilter = renderPromptTokenRuleSubcategoryTabs(
    "#promptTokenCustomTermSubcategoryTabs",
    categoryRows,
    state.promptTokenCustomTermSubcategoryFilter || "",
    Boolean(state.promptTokenCustomTermCategoryFilter)
  );
  const indexedRows = filteredPromptTokenCustomTermRows();
  const totalPages = Math.max(1, Math.ceil(indexedRows.length / PROMPT_TOKEN_RULE_PAGE_SIZE));
  state.promptTokenCustomTermPage = clampPage(state.promptTokenCustomTermPage || 1, totalPages);
  const start = (state.promptTokenCustomTermPage - 1) * PROMPT_TOKEN_RULE_PAGE_SIZE;
  const visibleRows = indexedRows.slice(start, start + PROMPT_TOKEN_RULE_PAGE_SIZE);
  $("#promptTokenCustomTermRows").innerHTML = tableRows(visibleRows, ({ row, index }) => `
    <tr data-index="${index}">
      <td>
        <input data-field="term" type="text" value="${escapeHtml(row.term || "")}" title="${escapeHtml(row.term || "")}" placeholder="高马尾，蓝紫渐变发色" />
      </td>
      <td>
        <input data-field="notes" type="text" value="${escapeHtml(row.notes || "")}" title="${escapeHtml(row.notes || "")}" placeholder="${escapeHtml(row.source || "")}" />
      </td>
      <td>
        <button type="button" data-action="delete-custom-term">删除</button>
      </td>
    </tr>
  `);
  renderPageControl(
    "#promptTokenCustomTermPagination",
    { page: state.promptTokenCustomTermPage, limit: PROMPT_TOKEN_RULE_PAGE_SIZE, total: indexedRows.length },
    "promptTokenCustomTermPageJumpInput"
  );
  renderPromptTokenCustomTermControls();
}

function markPromptTokenCustomTermsDirty() {
  state.promptTokenCustomTermsDirty = true;
  renderPromptTokenCustomTermControls();
}

function addPromptTokenCustomTermRow() {
  if (!state.promptTokenCustomTerms) return;
  state.promptTokenCustomTermSearch = "";
  const searchInput = $("#promptTokenCustomTermSearchInput");
  if (searchInput) searchInput.value = "";
  const category = promptTokenRuleCategoryForValue(
    promptTokenCustomTermRows(),
    state.promptTokenCustomTermCategoryFilter || ""
  );
  const subcategoryRows = category?.value
    ? promptTokenCustomTermRows().filter((row) => promptTokenRuleCategoryValue(row) === category.value)
    : [];
  const subcategory = promptTokenRuleSubcategoryForValue(
    subcategoryRows,
    state.promptTokenCustomTermSubcategoryFilter || ""
  );
  promptTokenCustomTermRows().push({
    term: "",
    category_key: category?.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY ? "" : category?.category_key || "",
    category_label: category?.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY ? "" : category?.category_label || "",
    subcategory_key: subcategory?.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY ? "" : subcategory?.subcategory_key || "",
    subcategory_label: subcategory?.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY ? "" : subcategory?.subcategory_label || "",
    notes: "",
    enabled: true,
  });
  state.promptTokenCustomTermPage = Number.MAX_SAFE_INTEGER;
  markPromptTokenCustomTermsDirty();
  renderPromptTokenCustomTerms();
}

async function savePromptTokenCustomTerms() {
  if (!state.promptTokenCustomTerms) return;
  state.promptTokenCustomTermsSaving = true;
  renderPromptTokenCustomTermControls();
  try {
    const rows = promptTokenCustomTermRows().map((row, index) => ({
      term: row.term || "",
      category_key: row.category_key || "",
      category_label: row.category_label || "",
      subcategory_key: row.subcategory_key || "",
      subcategory_label: row.subcategory_label || "",
      source: row.source || "",
      seed_batch: row.seed_batch || "",
      notes: row.notes || "",
      enabled: row.enabled !== false,
      sort_order: index,
    }));
    const payload = await fetchJson(
      "/api/prompt-token-custom-terms",
      {},
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows }),
      }
    );
    state.promptTokenCustomTerms = {
      rows: payload.rows || rows,
      status: payload.custom_term_status || {},
    };
    state.promptTokenCustomTermsDirty = false;
    renderPromptTokenCustomTerms();
  } finally {
    state.promptTokenCustomTermsSaving = false;
    renderPromptTokenCustomTermControls();
  }
}

async function rebuildPromptTokenCustomTerms() {
  if (!state.promptTokenCustomTerms) return;
  state.promptTokenCustomTermsRebuilding = true;
  renderPromptTokenCustomTermControls();
  try {
    const payload = await fetchJson("/api/prompt-token-custom-terms/rebuild", {}, { method: "POST" });
    state.promptTokenCustomTerms = {
      ...(state.promptTokenCustomTerms || { rows: [] }),
      status: payload.custom_term_status || state.promptTokenCustomTerms?.status || {},
    };
    state.promptTokenAliases = {
      ...(state.promptTokenAliases || { rows: [] }),
      status: payload.alias_status || state.promptTokenAliases?.status || {},
    };
    renderPromptTokenCustomTermControls();
    renderPromptTokenAliasControls();
    schedulePromptTokenCustomTermPoll();
  } finally {
    state.promptTokenCustomTermsRebuilding = false;
    renderPromptTokenCustomTermControls();
  }
}

function mergePromptTokenCustomTermPayload(payload) {
  if (!payload) return;
  if (state.promptTokenCustomTermsDirty) {
    state.promptTokenCustomTerms = {
      ...(state.promptTokenCustomTerms || { rows: [] }),
      status: payload.status || state.promptTokenCustomTerms?.status || {},
    };
    return;
  }
  state.promptTokenCustomTerms = payload;
}

async function pollPromptTokenCustomTermStatus() {
  state.promptTokenCustomTermPollTimer = null;
  const wasRunning = Boolean(state.promptTokenCustomTerms?.status?.resume?.running);
  const payload = await fetchJson("/api/prompt-token-custom-terms");
  mergePromptTokenCustomTermPayload(payload);
  state.promptTokenCustomTermsRebuilding = false;
  renderPromptTokenCustomTerms();
  const isRunning = Boolean(state.promptTokenCustomTerms?.status?.resume?.running);
  if (isRunning) {
    schedulePromptTokenCustomTermPoll();
    return;
  }
  if (wasRunning && state.activeTab === "prompt-tokens") {
    state.promptTokenPage = 1;
    await loadPromptTokens();
  }
}

async function loadPromptTokenCustomTerms() {
  if (state.promptTokenCustomTermsDirty) return;
  state.promptTokenCustomTermsLoading = true;
  renderPromptTokenCustomTerms();
  renderPromptTokenCustomTermControls();
  try {
    state.promptTokenCustomTerms = await fetchJson("/api/prompt-token-custom-terms");
    state.promptTokenCustomTermPage = 1;
    renderPromptTokenCustomTerms();
  } finally {
    state.promptTokenCustomTermsLoading = false;
    renderPromptTokenCustomTermControls();
  }
}

function schedulePromptTokenCustomTermPoll() {
  if (state.promptTokenCustomTermPollTimer) return;
  state.promptTokenCustomTermPollTimer = window.setTimeout(() => {
    pollPromptTokenCustomTermStatus().catch(setError);
  }, 5000);
}

function promptTokenAliasRows() {
  if (!state.promptTokenAliases) {
    state.promptTokenAliases = { rows: [], status: {} };
  }
  if (!Array.isArray(state.promptTokenAliases.rows)) {
    state.promptTokenAliases.rows = [];
  }
  return state.promptTokenAliases.rows;
}

function renderPromptTokenAliasControls() {
  const payload = state.promptTokenAliases || {};
  const rows = payload.rows || [];
  const status = payload.status || {};
  const resumeRunning = Boolean(status.resume?.running);
  let text = "暂无映射";
  const loaded = Boolean(state.promptTokenAliases);
  if (state.promptTokenAliasesLoading) {
    text = "正在加载词元映射表";
  } else if (!loaded) {
    text = "正在准备词元映射表";
  } else if (state.promptTokenRuleSeedsOverwriting) {
    text = "正在覆盖规则";
  } else if (state.promptTokenAliasesSaving) {
    text = "保存中";
  } else if (state.promptTokenAliasesRebuilding) {
    text = "正在提交重建";
  } else if (state.promptTokenAliasesDirty) {
    text = "有未保存修改";
  } else if (resumeRunning) {
    text = "词元重建或向量化任务运行中";
  } else if (status.pending) {
    text = `映射已保存，待重建生效 · ${fmtDate(status.rules_updated_at)}`;
  } else if (status.last_applied_at) {
    text = `已生效 · ${fmtDate(status.last_applied_at)}`;
  } else if (rows.length) {
    text = "已保存，等待首次重建";
  }
  const statusEl = $("#promptTokenAliasStatus");
  if (statusEl) statusEl.textContent = text;
  const addButton = $("#promptTokenAliasAddButton");
  if (addButton) addButton.disabled = !loaded || state.promptTokenAliasesLoading || state.promptTokenRuleSeedsOverwriting;
  const saveButton = $("#promptTokenAliasSaveButton");
  if (saveButton) saveButton.disabled = !loaded || state.promptTokenAliasesSaving || state.promptTokenRuleSeedsOverwriting;
  const rebuildButton = $("#promptTokenAliasRebuildButton");
  if (rebuildButton) rebuildButton.disabled = !loaded || state.promptTokenRuleSeedsOverwriting || state.promptTokenAliasesSaving || state.promptTokenAliasesRebuilding || resumeRunning;
  if (resumeRunning) {
    schedulePromptTokenAliasPoll();
  }
}

function renderPromptTokenAliases() {
  if (!state.promptTokenAliases) {
    renderPromptTokenRuleCategoryTabs("#promptTokenAliasCategoryTabs", [], "");
    $("#promptTokenAliasRows").innerHTML = `
      <tr><td colspan="5" class="empty">${state.promptTokenAliasesLoading ? "正在加载词元映射表" : "正在准备词元映射表"}</td></tr>
    `;
    renderPageControl("#promptTokenAliasPagination", { page: 1, limit: PROMPT_TOKEN_RULE_PAGE_SIZE, total: 0 }, "promptTokenAliasPageJumpInput");
    renderPromptTokenAliasControls();
    return;
  }
  const rows = promptTokenAliasRows();
  const searchedRows = promptTokenAliasRowsMatchingSearch(rows);
  state.promptTokenAliasCategoryFilter = renderPromptTokenRuleCategoryTabs(
    "#promptTokenAliasCategoryTabs",
    searchedRows,
    state.promptTokenAliasCategoryFilter || ""
  );
  const indexedRows = filteredPromptTokenAliasRows();
  const totalPages = Math.max(1, Math.ceil(indexedRows.length / PROMPT_TOKEN_RULE_PAGE_SIZE));
  state.promptTokenAliasPage = clampPage(state.promptTokenAliasPage || 1, totalPages);
  const start = (state.promptTokenAliasPage - 1) * PROMPT_TOKEN_RULE_PAGE_SIZE;
  const visibleRows = indexedRows.slice(start, start + PROMPT_TOKEN_RULE_PAGE_SIZE);
  $("#promptTokenAliasRows").innerHTML = tableRows(visibleRows, ({ row, index }) => `
    <tr data-index="${index}">
      <td>
        <input data-field="representative" type="text" value="${escapeHtml(row.representative || "")}" title="${escapeHtml(row.representative || "")}" placeholder="面部" />
      </td>
      <td>
        <textarea data-field="aliases_text" data-autoresize="true" rows="1" title="${escapeHtml(row.aliases_text || (row.aliases || []).join("，"))}" placeholder="脸部，面容">${escapeHtml(row.aliases_text || (row.aliases || []).join("，"))}</textarea>
      </td>
      <td>
        <input data-field="category_label" type="text" value="${escapeHtml(row.category_label || "")}" title="${escapeHtml(row.category_label || "")}" placeholder="身体部分" />
        <input data-field="category_key" type="hidden" value="${escapeHtml(row.category_key || "")}" />
      </td>
      <td>
        <input data-field="subcategory_label" type="text" value="${escapeHtml(row.subcategory_label || "")}" title="${escapeHtml(row.subcategory_label || "")}" placeholder="面部" />
        <input data-field="subcategory_key" type="hidden" value="${escapeHtml(row.subcategory_key || "")}" />
      </td>
      <td>
        <button type="button" data-action="delete-alias">删除</button>
      </td>
    </tr>
  `);
  resizePromptTokenAliasTextareas();
  renderPageControl(
    "#promptTokenAliasPagination",
    { page: state.promptTokenAliasPage, limit: PROMPT_TOKEN_RULE_PAGE_SIZE, total: indexedRows.length },
    "promptTokenAliasPageJumpInput"
  );
  renderPromptTokenAliasControls();
}

function resizePromptTokenAliasTextareas(root = document) {
  root.querySelectorAll(".prompt-token-alias-table textarea[data-autoresize]").forEach((textarea) => {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.max(38, textarea.scrollHeight)}px`;
  });
}

function renderPromptTokenDeletions() {
  if (!state.promptTokenDeletions) {
    const status = $("#promptTokenDeletionStatus");
    if (status) status.textContent = state.promptTokenDeletionsLoading ? "正在加载词元删除表" : "正在准备词元删除表";
    $("#promptTokenDeletionRows").innerHTML = `
      <tr><td colspan="4" class="empty">${state.promptTokenDeletionsLoading ? "正在加载词元删除表" : "正在准备词元删除表"}</td></tr>
    `;
    renderPageControl("#promptTokenDeletionPagination", { page: 1, limit: PROMPT_TOKEN_RULE_PAGE_SIZE, total: 0 }, "promptTokenDeletionPageJumpInput");
    return;
  }
  const rows = state.promptTokenDeletions?.rows || [];
  const status = $("#promptTokenDeletionStatus");
  if (status) {
    status.textContent = rows.length
      ? `已隐藏 ${fmt(rows.length)} 个词元，点击恢复后立即回到词元表`
      : "删除后立即从词元表和详情其它词元隐藏";
  }
  const totalPages = Math.max(1, Math.ceil(rows.length / PROMPT_TOKEN_RULE_PAGE_SIZE));
  state.promptTokenDeletionPage = clampPage(state.promptTokenDeletionPage || 1, totalPages);
  const start = (state.promptTokenDeletionPage - 1) * PROMPT_TOKEN_RULE_PAGE_SIZE;
  const visibleRows = rows.slice(start, start + PROMPT_TOKEN_RULE_PAGE_SIZE);
  $("#promptTokenDeletionRows").innerHTML = tableRows(visibleRows, (row) => `
    <tr>
      <td>
        <strong>${escapeHtml(row.token || "-")}</strong>
        <div class="muted small">${tokenKindLabel(row.token_kind)}</div>
      </td>
      <td>
        <strong>${fmt(row.prompt_count)} 条提示词</strong>
        <div class="muted small">使用 ${fmt(row.use_count)} 次 · ${fmt(row.user_count)} 人</div>
      </td>
      <td>
        <strong>${fmtDate(row.deleted_at)}</strong>
        <div class="muted small">更新 ${fmtDate(row.updated_at)}</div>
      </td>
      <td>
        <button type="button" data-restore-token="${encodeURIComponent(row.token || "")}">恢复</button>
      </td>
    </tr>
  `);
  renderPageControl(
    "#promptTokenDeletionPagination",
    { page: state.promptTokenDeletionPage, limit: PROMPT_TOKEN_RULE_PAGE_SIZE, total: rows.length },
    "promptTokenDeletionPageJumpInput"
  );
}

function markPromptTokenAliasesDirty() {
  state.promptTokenAliasesDirty = true;
  renderPromptTokenAliasControls();
}

function addPromptTokenAliasRow() {
  if (!state.promptTokenAliases) return;
  state.promptTokenAliasSearch = "";
  const searchInput = $("#promptTokenAliasSearchInput");
  if (searchInput) searchInput.value = "";
  const category = promptTokenRuleCategoryForValue(
    promptTokenAliasRows(),
    state.promptTokenAliasCategoryFilter || ""
  );
  promptTokenAliasRows().push({
    representative: "",
    aliases_text: "",
    category_key: category?.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY ? "" : category?.category_key || "",
    category_label: category?.value === PROMPT_TOKEN_UNCATEGORIZED_CATEGORY ? "" : category?.category_label || "",
    subcategory_key: "",
    subcategory_label: "",
    enabled: true,
  });
  state.promptTokenAliasPage = Number.MAX_SAFE_INTEGER;
  markPromptTokenAliasesDirty();
  renderPromptTokenAliases();
}

async function savePromptTokenAliases() {
  if (!state.promptTokenAliases) return;
  state.promptTokenAliasesSaving = true;
  renderPromptTokenAliasControls();
  try {
    const rows = promptTokenAliasRows().map((row, index) => ({
      representative: row.representative || "",
      aliases_text: row.aliases_text || (row.aliases || []).join("，"),
      category_key: row.category_key || "",
      category_label: row.category_label || "",
      subcategory_key: row.subcategory_key || "",
      subcategory_label: row.subcategory_label || "",
      source: row.source || "",
      seed_batch: row.seed_batch || "",
      enabled: row.enabled !== false,
      sort_order: index,
    }));
    const payload = await fetchJson(
      "/api/prompt-token-aliases",
      {},
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows }),
      }
    );
    state.promptTokenAliases = {
      rows: payload.rows || rows,
      status: payload.alias_status || {},
    };
    state.promptTokenAliasesDirty = false;
    renderPromptTokenAliases();
  } finally {
    state.promptTokenAliasesSaving = false;
    renderPromptTokenAliasControls();
  }
}

async function rebuildPromptTokenAliases() {
  if (!state.promptTokenAliases) return;
  state.promptTokenAliasesRebuilding = true;
  renderPromptTokenAliasControls();
  try {
    const payload = await fetchJson("/api/prompt-token-aliases/rebuild", {}, { method: "POST" });
    state.promptTokenAliases = {
      ...(state.promptTokenAliases || { rows: [] }),
      status: payload.alias_status || state.promptTokenAliases?.status || {},
    };
    renderPromptTokenAliasControls();
    schedulePromptTokenAliasPoll();
  } finally {
    state.promptTokenAliasesRebuilding = false;
    renderPromptTokenAliasControls();
  }
}

async function overwritePromptTokenGeneratedRules() {
  state.promptTokenRuleSeedsOverwriting = true;
  renderPromptTokenCustomTermControls();
  renderPromptTokenAliasControls();
  try {
    const payload = await fetchJson("/api/prompt-token-rules/overwrite-generated", {}, { method: "POST" });
    state.promptTokenRuleSeedReport = payload.report || null;
    state.promptTokenCustomTerms = payload.custom_terms || { rows: [], status: {} };
    state.promptTokenAliases = payload.aliases || { rows: [], status: {} };
    state.promptTokenDeletions = payload.deletions || { rows: [], total: 0 };
    state.promptTokenCustomTermsDirty = false;
    state.promptTokenAliasesDirty = false;
    state.promptTokenCustomTermCategoryFilter = "";
    state.promptTokenCustomTermSubcategoryFilter = "";
    state.promptTokenAliasCategoryFilter = "";
    state.promptTokenCustomTermPage = 1;
    state.promptTokenAliasPage = 1;
    state.promptTokenDeletionPage = 1;
    renderPromptTokenCustomTerms();
    renderPromptTokenAliases();
    renderPromptTokenDeletions();
  } finally {
    state.promptTokenRuleSeedsOverwriting = false;
    renderPromptTokenCustomTermControls();
    renderPromptTokenAliasControls();
  }
}

function mergePromptTokenAliasPayload(payload) {
  if (!payload) return;
  if (state.promptTokenAliasesDirty) {
    state.promptTokenAliases = {
      ...(state.promptTokenAliases || { rows: [] }),
      status: payload.status || state.promptTokenAliases?.status || {},
    };
    return;
  }
  state.promptTokenAliases = payload;
}

async function pollPromptTokenAliasStatus() {
  state.promptTokenAliasPollTimer = null;
  const wasRunning = Boolean(state.promptTokenAliases?.status?.resume?.running);
  const payload = await fetchJson("/api/prompt-token-aliases");
  mergePromptTokenAliasPayload(payload);
  state.promptTokenAliasesRebuilding = false;
  renderPromptTokenAliases();
  const isRunning = Boolean(state.promptTokenAliases?.status?.resume?.running);
  if (isRunning) {
    schedulePromptTokenAliasPoll();
    return;
  }
  if (wasRunning && state.activeTab === "prompt-tokens") {
    state.promptTokenPage = 1;
    await loadPromptTokens();
  }
}

async function loadPromptTokenAliases() {
  if (state.promptTokenAliasesDirty) return;
  state.promptTokenAliasesLoading = true;
  renderPromptTokenAliases();
  renderPromptTokenAliasControls();
  try {
    state.promptTokenAliases = await fetchJson("/api/prompt-token-aliases");
    state.promptTokenAliasPage = 1;
    renderPromptTokenAliases();
  } finally {
    state.promptTokenAliasesLoading = false;
    renderPromptTokenAliasControls();
  }
}

function schedulePromptTokenAliasPoll() {
  if (state.promptTokenAliasPollTimer) return;
  state.promptTokenAliasPollTimer = window.setTimeout(() => {
    pollPromptTokenAliasStatus().catch(setError);
  }, 5000);
}

function clampPage(page, totalPages = 1) {
  const parsed = Number(page);
  if (!Number.isFinite(parsed)) return 1;
  return Math.min(Math.max(1, Math.trunc(parsed)), Math.max(1, Number(totalPages) || 1));
}

function promptTokenTotalPages(pagination = state.promptTokens?.pagination || {}) {
  const limit = Math.max(1, Number(pagination.limit || 1));
  const total = Math.max(0, Number(pagination.total || 0));
  return Math.max(1, Math.ceil(total / limit));
}

function currentPromptTokenMinPromptCount() {
  const raw = $("#promptTokenMinPromptCountInput")?.value;
  const fallback = state.promptTokenMinPromptCount || PROMPT_TOKEN_DEFAULT_MIN_PROMPT_COUNT;
  const numeric = Number(raw || fallback);
  const safeValue = Number.isFinite(numeric) ? numeric : fallback;
  const clamped = Math.min(
    Math.max(1, Math.trunc(safeValue)),
    PROMPT_TOKEN_MAX_MIN_PROMPT_COUNT
  );
  state.promptTokenMinPromptCount = clamped;
  return clamped;
}

function syncPromptTokenMinPromptCountInput() {
  const input = $("#promptTokenMinPromptCountInput");
  if (!input) return;
  const value = String(state.promptTokenMinPromptCount || PROMPT_TOKEN_DEFAULT_MIN_PROMPT_COUNT);
  if (input.value !== value) input.value = value;
}

function paginationPages(currentPage, totalPages) {
  const current = clampPage(currentPage, totalPages);
  const total = Math.max(1, Number(totalPages) || 1);
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  if (current <= 4) return [1, 2, 3, 4, 5, "gap-end", total];
  if (current >= total - 3) return [1, "gap-start", total - 4, total - 3, total - 2, total - 1, total];
  return [1, "gap-start", current - 1, current, current + 1, "gap-end", total];
}

function renderPageControl(selector, pagination = {}, jumpInputId) {
  const container = $(selector);
  if (!container) return;
  const limit = Math.max(1, Number(pagination.limit || 1));
  const totalRows = Math.max(0, Number(pagination.total || 0));
  const totalPages = Math.max(1, Math.ceil(totalRows / limit));
  const current = clampPage(pagination.page || 1, totalPages);
  const pageButtons = paginationPages(current, totalPages).map((page) => {
    if (typeof page === "string") return '<span class="page-gap">...</span>';
    const active = page === current;
    return `
      <button class="page-button ${active ? "active" : ""}" type="button" data-page="${page}" ${active ? 'aria-current="page"' : ""}>
        ${fmt(page)}
      </button>
    `;
  }).join("");
  container.innerHTML = `
    <div class="page-button-list">${pageButtons}</div>
    <form class="page-jump-form">
      <label for="${jumpInputId}">跳至</label>
      <input id="${jumpInputId}" type="number" min="1" max="${totalPages}" value="${current}" inputmode="numeric" />
      <span>/ ${fmt(totalPages)}</span>
      <button type="submit">跳转</button>
    </form>
  `;
}

function renderPromptTokenOptionSet(selector, rows = [], staticOptions = []) {
  const select = $(selector);
  if (!select) return;
  const existing = select.value || "";
  const seen = new Set();
  const options = [];
  staticOptions.concat(rows).forEach((option) => {
    const value = option.value ?? "";
    const label = option.label ?? value;
    if (seen.has(value)) return;
    seen.add(value);
    options.push(`<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`);
  });
  if (existing && !seen.has(existing)) {
    options.push(`<option value="${escapeHtml(existing)}">${escapeHtml(existing)}</option>`);
  }
  select.innerHTML = options.join("");
  select.value = seen.has(existing) ? existing : staticOptions[0]?.value || "";
}

function renderPromptTokenFilterOptions() {
  const filters = state.promptTokens?.filters || {};
  renderPromptTokenOptionSet(
    "#promptTokenTaskTypeSelect",
    filters.tasks || [],
    [{ value: "", label: "全部任务" }]
  );
  const selectedTask = $("#promptTokenTaskTypeSelect")?.value || "";
  const modelRows = selectedTask ? filters.models || [] : [];
  renderPromptTokenOptionSet(
    "#promptTokenModelSelect",
    modelRows,
    [{ value: "", label: selectedTask ? "全部附加模型" : "先选择任务类型" }]
  );
  const modelSelect = $("#promptTokenModelSelect");
  if (modelSelect) {
    modelSelect.disabled = !selectedTask || modelRows.length === 0;
  }
}

function renderPromptTokens() {
  const summary = state.promptTokens?.summary || {};
  const rows = state.promptTokens?.rows || [];
  const pagination = state.promptTokens?.pagination || {};
  const scope = state.promptTokens?.scope || {};
  state.promptTokenMinPromptCount = Number(state.promptTokens?.min_prompt_count || state.promptTokenMinPromptCount || PROMPT_TOKEN_DEFAULT_MIN_PROMPT_COUNT);
  syncPromptTokenMinPromptCountInput();
  if (state.promptTokens?.filters_included !== false) {
    renderPromptTokenFilterOptions();
  }
  $("#promptTokenSummary").innerHTML = [
    metric("候选提示词", fmt(summary.candidate_count), "quality_stage = candidate"),
    metric("词元总数", fmt(summary.token_count), scope.label || "全部词元"),
    metric("当前筛选", fmt(pagination.total), $("#promptTokenSearchInput")?.value?.trim() || "全部词元"),
    metric("低频阈值", fmt(state.promptTokenMinPromptCount), `过滤后 ${fmt(summary.filtered_token_count ?? pagination.total)} 个词元`),
    metric("当前分类", scope.label || "全部词元", scope.model_key ? "二级附加模型" : scope.task_type ? "一级任务类型" : "全局"),
    metric("刷新", fmtDate(summary.refreshed_at), "来自 tokens-only 刷新"),
  ].join("");
  $("#promptTokenPageInfo").textContent = `第 ${fmt(pagination.page || 1)} 页 · 共 ${fmt(pagination.total || 0)} 个词元`;
  $("#promptTokenRows").innerHTML = tableRows(rows, (row) => `
    <tr>
      <td>
        <strong>${escapeHtml(row.token)}</strong>
        <div class="muted small">${tokenKindLabel(row.token_kind)}</div>
      </td>
      <td>
        <strong>${fmtAmount(row.prompt_share)}%</strong>
        <div class="muted small">${fmt(row.prompt_count)} / ${fmt(summary.candidate_count)}</div>
      </td>
      <td>
        <strong>${fmt(row.prompt_count)} 条提示词</strong>
        <div class="muted small">使用 ${fmt(row.use_count)} 次 · ${fmt(row.user_count)} 人</div>
      </td>
      <td>
        <strong>${tokenKindLabel(row.token_kind)}</strong>
        <div class="muted small">${fmtDate(row.refreshed_at)}</div>
      </td>
      <td>
        <div class="inline-actions prompt-token-row-actions">
          <button type="button" data-token="${encodeURIComponent(row.token)}">查看</button>
          <button type="button" data-delete-token="${encodeURIComponent(row.token)}">删除</button>
        </div>
      </td>
    </tr>
  `);
  renderPageControl("#promptTokenPagination", pagination, "promptTokenPageJumpInput");
}

function renderPromptTokenPromptDrawer() {
  const payload = state.promptTokenPrompts || {};
  const summary = payload.summary || {};
  const rows = payload.rows || [];
  const pagination = payload.pagination || {};
  const scope = payload.scope || state.promptTokens?.scope || {};
  const selected = state.selectedPromptToken || payload.token || summary.token || "";
  state.promptTokenMinPromptCount = Number(payload.min_prompt_count || state.promptTokenMinPromptCount || PROMPT_TOKEN_DEFAULT_MIN_PROMPT_COUNT);
  syncPromptTokenMinPromptCountInput();
  $("#promptTokenDrawerTitle").textContent = `词元：${selected || "-"}`;
  $("#promptTokenDrawerSummary").innerHTML = [
    metric("对应提示词", fmt(summary.prompt_count), "包含该词元"),
    metric("使用次数", fmt(summary.use_count), "候选提示词累计"),
    metric("使用用户", fmt(summary.user_count), "候选提示词累计"),
    metric("分类", scope.label || "全部词元", scope.model_key ? "附加模型" : scope.task_type ? "任务类型" : "全局"),
    metric("类型", tokenKindLabel(summary.token_kind), fmtDate(summary.refreshed_at)),
  ].join("");
  $("#promptTokenPromptPageInfo").textContent = `第 ${fmt(pagination.page || 1)} 页 · 共 ${fmt(pagination.total || 0)} 条提示词`;
  $("#promptTokenPromptRows").innerHTML = tableRows(rows, (row) => `
    <tr>
      <td>
        <div class="prompt-token-prompt-text">${escapeHtml(row.prompt_preview || row.prompt || "-")}</div>
        <div class="muted small mono">${escapeHtml(row.prompt_hash || "-")}</div>
      </td>
      <td>
        <strong>${(row.task_types || []).map(escapeHtml).join(" / ") || "-"}</strong>
        <div class="muted small">${fmt(row.uses)} 次 · ${fmt(row.users)} 人 · 分 ${fmtAmount(row.quality_score)}</div>
        <div class="muted small">${fmtDate(row.last_seen)}</div>
      </td>
      <td>${renderTokenPills(row.other_tokens || [], { selectedToken: selected })}</td>
    </tr>
  `);
  renderPageControl("#promptTokenPromptPagination", pagination, "promptTokenPromptPageJumpInput");
}

async function loadPromptTokens() {
  state.promptTokens = await fetchJson("/api/prompt-tokens", getPromptTokenParams({ includeFilters: true }));
  renderPromptTokens();
  renderPromptTokenCustomTerms();
  renderPromptTokenAliases();
  renderPromptTokenDeletions();
  ensurePromptTokenRuleTablesLoaded();
}

async function loadPromptTokenDeletions() {
  state.promptTokenDeletionsLoading = true;
  renderPromptTokenDeletions();
  try {
    state.promptTokenDeletions = await fetchJson("/api/prompt-token-deletions");
    state.promptTokenDeletionPage = 1;
    renderPromptTokenDeletions();
  } finally {
    state.promptTokenDeletionsLoading = false;
    renderPromptTokenDeletions();
  }
}

function ensurePromptTokenRuleTablesLoaded() {
  if (!state.promptTokenCustomTerms && !state.promptTokenCustomTermsLoading) {
    loadPromptTokenCustomTerms().catch(setError);
  }
  if (!state.promptTokenAliases && !state.promptTokenAliasesLoading) {
    loadPromptTokenAliases().catch(setError);
  }
  if (!state.promptTokenDeletions && !state.promptTokenDeletionsLoading) {
    loadPromptTokenDeletions().catch(setError);
  }
}

async function loadPromptTokenTableOnly({ includeFilters = false } = {}) {
  state.promptTokens = await fetchJson("/api/prompt-tokens", getPromptTokenParams({ includeFilters }));
  renderPromptTokens();
}

async function loadPromptTokenPrompts() {
  if (!state.selectedPromptToken) return;
  state.promptTokenPrompts = await fetchJson("/api/prompt-token-prompts", getPromptTokenPromptParams());
  renderPromptTokenPromptDrawer();
}

async function reloadPromptTokensPreservingPage() {
  const requestedPage = Math.max(1, Number(state.promptTokenPage || 1));
  state.promptTokenPage = requestedPage;
  await loadPromptTokenTableOnly({ includeFilters: false });
  const adjustedPage = clampPage(requestedPage, promptTokenTotalPages());
  if (adjustedPage !== requestedPage) {
    state.promptTokenPage = adjustedPage;
    await loadPromptTokenTableOnly({ includeFilters: false });
  }
  state.promptTokenDeletions = await fetchJson("/api/prompt-token-deletions");
  renderPromptTokenDeletions();
}

async function openPromptTokenDrawer(token) {
  state.selectedPromptToken = token;
  state.promptTokenPromptPage = 1;
  state.promptTokenPrompts = null;
  $("#promptTokenDrawerBackdrop")?.classList.remove("hidden");
  $("#promptTokenDrawer")?.classList.add("open");
  $("#promptTokenDrawer")?.setAttribute("aria-hidden", "false");
  $("#promptTokenPromptRows").innerHTML = '<tr><td colspan="3" class="empty">加载中</td></tr>';
  try {
    await loadPromptTokenPrompts();
  } catch (error) {
    setError(error);
  }
}

function closePromptTokenDrawer() {
  $("#promptTokenDrawerBackdrop")?.classList.add("hidden");
  $("#promptTokenDrawer")?.classList.remove("open");
  $("#promptTokenDrawer")?.setAttribute("aria-hidden", "true");
}

async function deletePromptToken(token) {
  const normalized = String(token || "").trim();
  if (!normalized) return;
  await fetchJson(
    "/api/prompt-token-deletions",
    {},
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: normalized }),
    }
  );
  if (state.selectedPromptToken === normalized) {
    state.selectedPromptToken = null;
    state.promptTokenPrompts = null;
    closePromptTokenDrawer();
  }
  await reloadPromptTokensPreservingPage();
}

async function restorePromptToken(token) {
  const normalized = String(token || "").trim();
  if (!normalized) return;
  await fetchJson(
    "/api/prompt-token-deletions/restore",
    {},
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: normalized }),
    }
  );
  await reloadPromptTokensPreservingPage();
}

function getPromptDecompositionParams({ includeFilters = true } = {}) {
  return {
    task_type: PROMPT_DECOMPOSITION_TASK_TYPE,
    q: $("#promptDecompositionSearchInput")?.value?.trim() || "",
    selected_tokens: promptDecompositionSelectedTokens().join(","),
    page: state.promptDecompositionPage || 1,
    limit: 20,
    include_filters: includeFilters ? "true" : "false",
  };
}

async function loadPromptDecompositionSaved() {
  state.promptDecompositionSavedLoading = true;
  renderPromptDecompositionSaved();
  try {
    state.promptDecompositionSaved = await fetchJson("/api/prompt-decomposition/saved", {
      task_type: PROMPT_DECOMPOSITION_TASK_TYPE,
      limit: PROMPT_DECOMPOSITION_SAVED_LIMIT,
    });
    if (state.promptDecomposition) {
      state.promptDecomposition.summary = {
        ...(state.promptDecomposition.summary || {}),
        saved_template_count: state.promptDecompositionSaved?.total || 0,
      };
    }
    renderPromptDecomposition();
    renderPromptDecompositionSaved();
  } finally {
    state.promptDecompositionSavedLoading = false;
    renderPromptDecompositionSaved();
  }
}

async function loadPromptDecomposition() {
  state.promptDecomposition = await fetchJson("/api/prompt-decomposition", getPromptDecompositionParams({ includeFilters: true }));
  state.promptDecompositionSelectedTokens = state.promptDecomposition?.selected_tokens || promptDecompositionSelectedTokens();
  renderPromptDecomposition();
  if (!state.promptDecompositionSaved && !state.promptDecompositionSavedLoading) {
    loadPromptDecompositionSaved().catch(setError);
  }
}

async function loadPromptDecompositionTableOnly({ includeFilters = false } = {}) {
  const existingFilters = state.promptDecomposition?.filters || { groups: [] };
  state.promptDecomposition = await fetchJson("/api/prompt-decomposition", getPromptDecompositionParams({ includeFilters }));
  if (state.promptDecomposition?.filters_included === false) {
    state.promptDecomposition.filters = existingFilters;
  }
  state.promptDecompositionSelectedTokens = state.promptDecomposition?.selected_tokens || promptDecompositionSelectedTokens();
  renderPromptDecomposition();
}

function openPromptDecompositionDrawer(promptHash, source = "live") {
  const normalized = decodeURIComponent(promptHash || "");
  const sourceRows = source === "saved"
    ? (state.promptDecompositionSaved?.rows || [])
    : (state.promptDecomposition?.rows || []);
  const row = sourceRows.find((item) => item.prompt_hash === normalized);
  if (!row) return;
  state.selectedPromptDecomposition = row;
  state.promptDecompositionSaveTitle = row.title || "";
  $("#promptDecompositionDrawerBackdrop")?.classList.remove("hidden");
  $("#promptDecompositionDrawer")?.classList.add("open");
  $("#promptDecompositionDrawer")?.setAttribute("aria-hidden", "false");
  renderPromptDecomposition();
}

function closePromptDecompositionDrawer() {
  $("#promptDecompositionDrawerBackdrop")?.classList.add("hidden");
  $("#promptDecompositionDrawer")?.classList.remove("open");
  $("#promptDecompositionDrawer")?.setAttribute("aria-hidden", "true");
}

async function savePromptDecompositionTemplate() {
  const row = state.selectedPromptDecomposition;
  if (!row?.prompt_hash) return;
  const title = $("#promptDecompositionSaveTitleInput")?.value?.trim() || "";
  if (!title) {
    throw new Error("请先填写模板标题");
  }
  state.promptDecompositionSaving = true;
  renderPromptDecompositionDrawer();
  try {
    await fetchJson(
      "/api/prompt-decomposition/saved",
      {},
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_type: PROMPT_DECOMPOSITION_TASK_TYPE,
          prompt_hash: row.prompt_hash,
          title,
          selected_tokens: promptDecompositionSelectedTokens(),
        }),
      }
    );
    state.promptDecompositionSaveTitle = title;
    await loadPromptDecompositionSaved();
    if (state.promptDecomposition) {
      state.promptDecomposition.summary = {
        ...(state.promptDecomposition.summary || {}),
        saved_template_count: state.promptDecompositionSaved?.total || 0,
      };
      renderPromptDecomposition();
    }
  } finally {
    state.promptDecompositionSaving = false;
    renderPromptDecompositionDrawer();
  }
}

async function deletePromptDecompositionTemplate(savedId) {
  const normalized = Number(savedId);
  if (!Number.isFinite(normalized)) return;
  await fetchJson(`/api/prompt-decomposition/saved/${normalized}`, {}, { method: "DELETE" });
  await loadPromptDecompositionSaved();
  if (state.promptDecomposition) {
    state.promptDecomposition.summary = {
      ...(state.promptDecomposition.summary || {}),
      saved_template_count: state.promptDecompositionSaved?.total || 0,
    };
    renderPromptDecomposition();
  }
}

function getPromptParams(days = currentDays()) {
  return {
    days,
    task_type: $("#taskTypeSelect").value || "",
    template_scope: $("#promptScopeSelect")?.value || "natural",
    q: $("#promptSearchInput")?.value?.trim() || "",
    min_users: Number($("#promptMinUsersInput")?.value || 1),
    min_uses: Number($("#promptMinUsesInput")?.value || 1),
    sort: $("#promptSortSelect")?.value || "value_score",
    page: state.promptPage,
    limit: 40,
  };
}

function getPromptSlimParams() {
  return {
    quality_stage: $("#promptSlimStageSelect")?.value || "all",
    task_type: $("#promptSlimTaskTypeSelect")?.value || "",
    source_scope: $("#promptSlimSourceSelect")?.value || "all",
    reason: $("#promptSlimReasonSelect")?.value || "all",
    q: $("#promptSlimSearchInput")?.value?.trim() || "",
    min_users: Number($("#promptSlimMinUsersInput")?.value || 1),
    min_uses: Number($("#promptSlimMinUsesInput")?.value || 1),
    sort: $("#promptSlimSortSelect")?.value || "quality_score",
    page: state.promptSlimPage,
    limit: 40,
  };
}

function getPromptVectorParams() {
  return {};
}

function getPromptTokenParams({ includeFilters = true } = {}) {
  return {
    q: $("#promptTokenSearchInput")?.value?.trim() || "",
    task_type: $("#promptTokenTaskTypeSelect")?.value || "",
    model_key: $("#promptTokenModelSelect")?.value || "",
    sort: $("#promptTokenSortSelect")?.value || "prompt_count",
    min_prompt_count: currentPromptTokenMinPromptCount(),
    page: state.promptTokenPage,
    limit: 15,
    include_filters: includeFilters,
  };
}

function getPromptTokenPromptParams() {
  return {
    token: state.selectedPromptToken || "",
    task_type: $("#promptTokenTaskTypeSelect")?.value || "",
    model_key: $("#promptTokenModelSelect")?.value || "",
    min_prompt_count: currentPromptTokenMinPromptCount(),
    page: state.promptTokenPromptPage,
    limit: 8,
  };
}

function getUserProfileParams() {
  const selectedGroup = state.selectedUserGroup;
  return {
    ...userPeriodParams(),
    page: state.userProfilePage,
    size: 20,
    search: $("#userProfileSearchInput")?.value?.trim() || "",
    segment: $("#userProfileSegmentSelect")?.value || "all",
    sort: $("#userProfileSortSelect")?.value || "last_activity",
    dimension: selectedGroup?.dimension || "",
    group_key: selectedGroup?.group_key || "",
  };
}

function getUserGroupParams() {
  return {
    ...userPeriodParams(),
    dimension: $("#userGroupDimensionSelect")?.value || "payer",
    search: $("#userProfileSearchInput")?.value?.trim() || "",
    segment: $("#userProfileSegmentSelect")?.value || "all",
    sort: $("#userGroupSortSelect")?.value || "users",
    limit: Number($("#userGroupLimitSelect")?.value || 20),
  };
}

function getTemplateCandidateParams({ includeFilters = false } = {}) {
  return {
    task_type: $("#templateTaskTypeSelect")?.value || "",
    model_key: $("#templateModelSelect")?.value || "",
    q: $("#templateSearchInput")?.value?.trim() || "",
    min_prompts: currentTemplateMinPrompts(),
    similarity_bucket: $("#templateSimilaritySelect")?.value || "",
    review_status: $("#templateReviewStatusSelect")?.value || "all",
    sort: $("#templateSortSelect")?.value || "score",
    page: state.templateCandidatePage || 1,
    limit: 20,
    include_filters: includeFilters ? "true" : "false",
  };
}

function templateCandidateTotalPages(pagination = state.templates?.pagination || {}) {
  const limit = Math.max(1, Number(pagination.limit || 1));
  const total = Math.max(0, Number(pagination.total || 0));
  return Math.max(1, Math.ceil(total / limit));
}

async function loadTemplateCandidateTableOnly({ includeFilters = false } = {}) {
  state.templates = await fetchJson("/api/prompt-template-candidates", getTemplateCandidateParams({ includeFilters }));
  renderTemplateCandidates(state.templates);
}

function getTemplateReviewMarksParams() {
  return {
    task_type: $("#templateTaskTypeSelect")?.value || "",
    model_key: $("#templateModelSelect")?.value || "",
    q: $("#templateReviewMarksSearchInput")?.value?.trim() || "",
    similarity_bucket: $("#templateReviewMarksSimilaritySelect")?.value || "",
    processed_status: $("#templateReviewMarksProcessedSelect")?.value || "all",
    page: state.templateReviewMarksPage || 1,
    limit: PROMPT_TEMPLATE_REVIEW_MARKS_LIMIT,
  };
}

async function loadTemplateReviewMarks() {
  state.templateReviewMarksLoading = true;
  state.templateReviewMarksCopyStatus = "";
  renderTemplateReviewMarksDrawer();
  try {
    state.templateReviewMarks = await fetchJson(
      "/api/prompt-template-candidates/review-marks",
      getTemplateReviewMarksParams()
    );
  } finally {
    state.templateReviewMarksLoading = false;
    renderTemplateReviewMarksDrawer();
  }
}

function resetTemplateReviewMarksPageAndLoad() {
  state.templateReviewMarksPage = 1;
  return loadTemplateReviewMarks();
}

async function loadTemplateCandidatePrompts() {
  const key = state.selectedTemplateCandidate?.template_key;
  if (!key) return;
  state.templateCandidatePrompts = await fetchJson(
    `/api/prompt-template-candidates/${encodeURIComponent(key)}/prompts`,
    {
      page: state.templateCandidatePromptPage || 1,
      limit: 20,
    }
  );
  renderTemplateCandidateDrawer();
}

async function toggleTemplateReviewMarkProcessed(templateKey, promptHash, processed) {
  if (!templateKey || !promptHash) return;
  const rowKey = `${templateKey}::${promptHash}`;
  state.templateReviewMarksProcessingSaving = {
    ...(state.templateReviewMarksProcessingSaving || {}),
    [rowKey]: true,
  };
  renderTemplateReviewMarksDrawer();
  try {
    await fetchJson(
      "/api/prompt-template-candidates/review-marks/processed",
      {},
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_key: templateKey,
          prompt_hash: promptHash,
          processed,
        }),
      }
    );
    await loadTemplateReviewMarks();
  } finally {
    delete state.templateReviewMarksProcessingSaving[rowKey];
    renderTemplateReviewMarksDrawer();
  }
}

async function toggleTemplateCandidateReviewMark(promptHash, checked) {
  const templateKey = state.selectedTemplateCandidate?.template_key;
  if (!templateKey || !promptHash) return;
  state.templateCandidateReviewSaving = {
    ...(state.templateCandidateReviewSaving || {}),
    [promptHash]: true,
  };
  renderTemplateCandidateDrawer();
  try {
    const payload = await fetchJson(
      "/api/prompt-template-candidates/review-marks",
      {},
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_key: templateKey,
          prompt_hash: promptHash,
          checked,
        }),
      }
    );
    const rows = state.templateCandidatePrompts?.rows || [];
    const row = rows.find((item) => item.prompt_hash === promptHash);
    if (row) {
      row.review_checked = Boolean(payload.review_checked);
      row.review_marked_at = payload.review_checked ? (payload.review_marked_at || new Date().toISOString()) : null;
    }
    const markedCount = Number(payload.marked_prompt_count || 0);
    const processed = Boolean(payload.processed);
    if (state.templateCandidatePrompts?.summary) {
      state.templateCandidatePrompts.summary.marked_prompt_count = markedCount;
      state.templateCandidatePrompts.summary.processed = processed;
    }
    if (state.selectedTemplateCandidate) {
      state.selectedTemplateCandidate.marked_prompt_count = markedCount;
      state.selectedTemplateCandidate.processed = processed;
    }
    const tableRow = (state.templates?.rows || []).find((item) => item.template_key === templateKey);
    if (tableRow) {
      tableRow.marked_prompt_count = markedCount;
      tableRow.processed = processed;
    }
    renderTemplateCandidateDrawer();
    renderTemplateCandidates(state.templates || {});
    await loadTemplateCandidateTableOnly({ includeFilters: false });
    if ($("#templateReviewMarksDrawer")?.classList.contains("open")) {
      await loadTemplateReviewMarks();
    }
  } finally {
    delete state.templateCandidateReviewSaving[promptHash];
    renderTemplateCandidateDrawer();
  }
}

async function toggleTemplateCandidateLowQuality(templateKey, lowQuality) {
  if (!templateKey) return;
  state.templateCandidateLowQualitySaving = {
    ...(state.templateCandidateLowQualitySaving || {}),
    [templateKey]: true,
  };
  renderTemplateCandidates(state.templates || {});
  try {
    const payload = await fetchJson(
      "/api/prompt-template-candidates/template-review-marks",
      {},
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_key: templateKey,
          low_quality: lowQuality,
        }),
      }
    );
    const tableRow = (state.templates?.rows || []).find((item) => item.template_key === templateKey);
    if (tableRow) {
      tableRow.low_quality = Boolean(payload.low_quality);
      tableRow.low_quality_marked_at = payload.low_quality_marked_at || null;
      tableRow.marked_prompt_count = Number(payload.marked_prompt_count || 0);
      tableRow.processed = Boolean(payload.processed);
    }
    if (state.selectedTemplateCandidate?.template_key === templateKey) {
      state.selectedTemplateCandidate.low_quality = Boolean(payload.low_quality);
      state.selectedTemplateCandidate.low_quality_marked_at = payload.low_quality_marked_at || null;
      state.selectedTemplateCandidate.marked_prompt_count = Number(payload.marked_prompt_count || 0);
      state.selectedTemplateCandidate.processed = Boolean(payload.processed);
    }
    if (state.templateCandidatePrompts?.summary?.template_key === templateKey) {
      state.templateCandidatePrompts.summary.low_quality = Boolean(payload.low_quality);
      state.templateCandidatePrompts.summary.low_quality_marked_at = payload.low_quality_marked_at || null;
      state.templateCandidatePrompts.summary.marked_prompt_count = Number(payload.marked_prompt_count || 0);
      state.templateCandidatePrompts.summary.processed = Boolean(payload.processed);
    }
    renderTemplateCandidates(state.templates || {});
    renderTemplateCandidateDrawer();
    await loadTemplateCandidateTableOnly({ includeFilters: false });
  } finally {
    delete state.templateCandidateLowQualitySaving[templateKey];
    renderTemplateCandidates(state.templates || {});
  }
}

async function openTemplateReviewMarksDrawer() {
  const searchInput = $("#templateReviewMarksSearchInput");
  const similaritySelect = $("#templateReviewMarksSimilaritySelect");
  const processedSelect = $("#templateReviewMarksProcessedSelect");
  if (searchInput) searchInput.value = $("#templateSearchInput")?.value?.trim() || "";
  if (similaritySelect) similaritySelect.value = $("#templateSimilaritySelect")?.value || "";
  if (processedSelect) processedSelect.value = "all";
  state.templateReviewMarks = null;
  state.templateReviewMarksCopyStatus = "";
  state.templateReviewMarksPage = 1;
  $("#templateReviewMarksDrawerBackdrop")?.classList.remove("hidden");
  $("#templateReviewMarksDrawer")?.classList.add("open");
  $("#templateReviewMarksDrawer")?.setAttribute("aria-hidden", "false");
  await loadTemplateReviewMarks();
}

function closeTemplateReviewMarksDrawer() {
  $("#templateReviewMarksDrawerBackdrop")?.classList.add("hidden");
  $("#templateReviewMarksDrawer")?.classList.remove("open");
  $("#templateReviewMarksDrawer")?.setAttribute("aria-hidden", "true");
}

async function copyTemplateReviewMarkPrompt(templateKey, promptHash) {
  const row = (state.templateReviewMarks?.rows || []).find(
    (item) => item.template_key === templateKey && item.prompt_hash === promptHash
  );
  await copyTextToClipboard(templateReviewMarkPromptText(row));
  state.templateReviewMarksCopyStatus = "已复制 1 条";
  renderTemplateReviewMarksDrawer();
}

async function copyTemplateReviewMarksAll() {
  const rows = state.templateReviewMarks?.rows || [];
  await copyTextToClipboard(templateReviewMarksCopyText(rows));
  state.templateReviewMarksCopyStatus = `已复制当前页 ${fmt(rows.length)} 条`;
  renderTemplateReviewMarksDrawer();
}

function exportTemplateReviewMarksCsv() {
  const rows = state.templateReviewMarks?.rows || [];
  const stamp = new Date().toISOString().slice(0, 19).replaceAll(":", "").replace("T", "-");
  downloadTextFile(
    `template-review-marks-${stamp}.csv`,
    templateReviewMarksCsv(rows),
    "text/csv;charset=utf-8"
  );
  state.templateReviewMarksCopyStatus = `已导出当前页 ${fmt(rows.length)} 条`;
  renderTemplateReviewMarksDrawer();
}

async function openTemplateCandidateDrawer(templateKey) {
  const rows = state.templates?.rows || [];
  state.selectedTemplateCandidate = rows.find((row) => row.template_key === templateKey) || { template_key: templateKey };
  state.templateCandidatePromptPage = 1;
  state.templateCandidatePrompts = null;
  $("#templateCandidateDrawerBackdrop")?.classList.remove("hidden");
  $("#templateCandidateDrawer")?.classList.add("open");
  $("#templateCandidateDrawer")?.setAttribute("aria-hidden", "false");
  $("#templateCandidatePromptRows").innerHTML = '<tr><td colspan="4" class="empty">加载中</td></tr>';
  renderTemplateCandidateDrawer();
  try {
    await loadTemplateCandidatePrompts();
  } catch (error) {
    setError(error);
  }
}

function closeTemplateCandidateDrawer() {
  $("#templateCandidateDrawerBackdrop")?.classList.add("hidden");
  $("#templateCandidateDrawer")?.classList.remove("open");
  $("#templateCandidateDrawer")?.setAttribute("aria-hidden", "true");
}

async function refreshTemplateCandidates() {
  state.templateCandidateRefreshing = true;
  renderTemplateCandidates(state.templates || {});
  try {
    const payload = await fetchJson("/api/prompt-template-candidates/refresh", {}, { method: "POST" });
    state.templates = {
      ...(state.templates || {}),
      summary: {
        ...(state.templates?.summary || {}),
        refresh: payload.refresh || state.templates?.summary?.refresh || {},
      },
      refresh_message: payload.message || "",
    };
    renderTemplateCandidates(state.templates);
  } finally {
    state.templateCandidateRefreshing = false;
    renderTemplateCandidates(state.templates || {});
  }
}

async function loadOverviewStatus() {
  state.overview = await fetchJson("/api/overview", { days: currentDays() });
  renderSource();
}

const loadUsers = createUsersLoader({
  fetchJson,
  state,
  userPeriodParams,
  getUserGroupParams,
  getUserProfileParams,
  renderUsers,
});
const loadCreditFlow = createCreditFlowLoader({ fetchJson, state, renderCreditFlow });
const {
  loadFinance,
  loadFinanceHourlyComparison,
  loadFinanceHourlyCumulative,
} = createFinanceModule({
  fetchJson,
  state,
  renderFinance,
  renderFinanceCharts,
  getCompareDates,
  selectNumber,
  fmt,
  setError,
});
const {
  loadGeneration,
  loadGenerationHourlyComparison,
  loadGenerationHourlyCumulative,
  loadGenerationTypeComparison,
} = createGenerationModule({
  fetchJson,
  state,
  renderGeneration,
  renderGenerationCharts,
  getCompareDates,
  selectNumber,
  setError,
});
const loadPrompts = createPromptsLoader({
  fetchJson,
  state,
  getPromptParams,
  renderPromptTaskTypeOptions,
  renderPrompts,
});
const loadPromptSlim = createPromptSlimLoader({
  fetchJson,
  state,
  getPromptSlimParams,
  renderPromptSlim,
});
const {
  loadPromptVectors,
  resumePromptVectorEmbeddings,
} = createPromptVectorsModule({
  fetchJson,
  state,
  getPromptVectorParams,
  renderPromptVectors,
  renderPromptVectorResumeStatus,
  markTabStale,
  markTabLoaded,
  setError,
});
const loadTemplates = createTemplatesLoader({
  fetchJson,
  state,
  getTemplateCandidateParams,
  renderTemplateCandidates,
});
const loadMedia = createMediaLoader({ fetchJson, state, renderMedia });

const tabLoaders = {
  users: loadUsers,
  "credit-flow": loadCreditFlow,
  finance: loadFinance,
  generation: loadGeneration,
  prompts: loadPrompts,
  "prompt-slim": loadPromptSlim,
  "prompt-vectors": loadPromptVectors,
  "prompt-tokens": loadPromptTokens,
  "prompt-decomposition": loadPromptDecomposition,
  templates: loadTemplates,
  media: loadMedia,
};

async function loadCurrentTab({ force = false } = {}) {
  const tab = state.activeTab;
  const loader = tabLoaders[tab] || loadUsers;
  if (!force && state.loadedTabs[tab]) {
    return;
  }
  setLoading(true);
  setError(null);
  try {
    await loader(currentDays());
    markTabLoaded(tab);
  } catch (error) {
    setError(error);
  } finally {
    setLoading(false);
  }
}

const { setActiveTab } = createTabController({
  state,
  tabs,
  disposeChartsForTab,
  syncDaysControl,
  renderLastUpdated,
  loadCurrentTab,
});

function resetPromptPageAndLoad() {
  state.promptPage = 1;
  state.selectedPrompt = null;
  state.promptVariantCache = {};
  markTabStale("prompts");
  if (state.activeTab === "prompts") {
    loadCurrentTab({ force: true });
  }
}

function reloadCurrentTab() {
  if (state.activeTab === "users") {
    state.userProfilePage = 1;
    state.selectedUserGroup = null;
  }
  if (state.activeTab === "prompts") {
    state.promptPage = 1;
    state.selectedPrompt = null;
    state.promptVariantCache = {};
  }
  if (state.activeTab === "prompt-slim") {
    state.promptSlimPage = 1;
    state.selectedPromptSlim = null;
  }
  if (state.activeTab === "prompt-tokens") {
    state.promptTokenPage = 1;
    state.selectedPromptToken = null;
    if (!state.promptTokenCustomTermsDirty) {
      state.promptTokenCustomTerms = null;
      state.promptTokenCustomTermPage = 1;
    }
    if (!state.promptTokenAliasesDirty) {
      state.promptTokenAliases = null;
      state.promptTokenAliasPage = 1;
    }
    state.promptTokenDeletions = null;
    state.promptTokenDeletionPage = 1;
  }
  if (state.activeTab === "prompt-decomposition") {
    state.promptDecompositionPage = 1;
    state.selectedPromptDecomposition = null;
    state.promptDecompositionSaveTitle = "";
    state.promptDecompositionSaved = null;
  }
  if (state.activeTab === "templates") {
    state.templateCandidatePage = 1;
    state.templateCandidatePromptPage = 1;
    state.selectedTemplateCandidate = null;
    state.templateCandidatePrompts = null;
  }
  markTabStale(state.activeTab);
  loadCurrentTab({ force: true });
}

$("#refreshButton").addEventListener("click", reloadCurrentTab);
$("#logoutButton")?.addEventListener("click", logoutLocalAnalytics);
$("#daysSelect").addEventListener("change", () => {
  setCurrentDays(selectNumber("#daysSelect", 30));
  reloadCurrentTab();
});
function resetUserProfilePageAndLoad({ clearGroup = false } = {}) {
  state.userProfilePage = 1;
  if (clearGroup) {
    state.selectedUserGroup = null;
  }
  markTabStale("users");
  if (state.activeTab === "users") {
    loadCurrentTab({ force: true });
  }
}

function resetUserGroupsAndLoad() {
  clearUserGroupSelection({ reload: false });
  markTabStale("users");
  if (state.activeTab === "users") {
    loadCurrentTab({ force: true });
  }
}

function resetUserDateRangeAndLoad() {
  const range = currentUserDateRange();
  const days = inclusiveDateDays(range.start, range.end);
  if (!days) {
    setError(new Error("请选择有效的开始和结束日期"));
    return;
  }
  resetUserProfilePageAndLoad({ clearGroup: true });
}

$("#userGroupDimensionSelect")?.addEventListener("change", resetUserGroupsAndLoad);
$("#userGroupSortSelect")?.addEventListener("change", resetUserGroupsAndLoad);
$("#userGroupLimitSelect")?.addEventListener("change", resetUserGroupsAndLoad);
$("#userGroupRefreshButton")?.addEventListener("click", resetUserGroupsAndLoad);
$("#userGroupClearButton")?.addEventListener("click", () => clearUserGroupSelection());
$("#userStartDateInput")?.addEventListener("change", resetUserDateRangeAndLoad);
$("#userEndDateInput")?.addEventListener("change", resetUserDateRangeAndLoad);
$("#userProfileSegmentSelect")?.addEventListener("change", () => resetUserProfilePageAndLoad({ clearGroup: true }));
$("#userProfileSortSelect")?.addEventListener("change", () => resetUserProfilePageAndLoad());
$("#userProfileRefreshButton")?.addEventListener("click", () => resetUserProfilePageAndLoad({ clearGroup: true }));
$("#userProfileSearchInput")?.addEventListener("input", () => {
  window.clearTimeout(state.userProfileSearchTimer);
  state.userProfileSearchTimer = window.setTimeout(() => resetUserProfilePageAndLoad({ clearGroup: true }), 300);
});
$("#userProfilePrevButton")?.addEventListener("click", () => {
  state.userProfilePage = Math.max(1, state.userProfilePage - 1);
  markTabStale("users");
  loadCurrentTab({ force: true });
});
$("#userProfileNextButton")?.addEventListener("click", () => {
  state.userProfilePage += 1;
  markTabStale("users");
  loadCurrentTab({ force: true });
});
$("#userProfileDrawerClose")?.addEventListener("click", closeUserProfileDrawer);
$("#userProfileDrawerBackdrop")?.addEventListener("click", closeUserProfileDrawer);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("#userProfileDrawer")?.classList.contains("open")) {
    closeUserProfileDrawer();
  }
  if (event.key === "Escape" && $("#promptTokenDrawer")?.classList.contains("open")) {
    closePromptTokenDrawer();
  }
  if (event.key === "Escape" && $("#promptDecompositionDrawer")?.classList.contains("open")) {
    closePromptDecompositionDrawer();
  }
});
document.querySelectorAll("[data-credit-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    state.creditFlowMode = button.dataset.creditMode || "daily";
    document.querySelectorAll("[data-credit-mode]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    if (state.creditFlow) renderCreditFlowCharts();
  });
});
$("#financeMetricSelect")?.addEventListener("change", () => {
  state.financeMetric = $("#financeMetricSelect").value || "usdt_amount";
  if (state.finance) renderFinanceCharts();
});
$("#financeHourlyCompareButton")?.addEventListener("click", loadFinanceHourlyComparison);
$("#financeHourlyCumulativeButton")?.addEventListener("click", loadFinanceHourlyCumulative);
$("#generationHourlyCompareButton")?.addEventListener("click", loadGenerationHourlyComparison);
$("#generationHourlyCumulativeButton")?.addEventListener("click", loadGenerationHourlyCumulative);
$("#generationTypeCompareButton")?.addEventListener("click", loadGenerationTypeComparison);
$("#taskTypeSelect").addEventListener("change", () => {
  state.promptPage = 1;
  state.selectedPrompt = null;
  state.promptVariantCache = {};
  markTabStale("prompts");
  if (state.activeTab === "prompts") {
    loadCurrentTab({ force: true });
  }
});
["#promptScopeSelect", "#promptSortSelect", "#promptMinUsersInput", "#promptMinUsesInput"].forEach((selector) => {
  const element = $(selector);
  if (element) element.addEventListener("change", resetPromptPageAndLoad);
});
let promptSearchTimer = null;
$("#promptSearchInput").addEventListener("input", () => {
  window.clearTimeout(promptSearchTimer);
  promptSearchTimer = window.setTimeout(resetPromptPageAndLoad, 300);
});
$("#promptPrevButton").addEventListener("click", () => {
  state.promptPage = Math.max(1, state.promptPage - 1);
  state.selectedPrompt = null;
  state.promptVariantCache = {};
  markTabStale("prompts");
  loadCurrentTab({ force: true });
});
$("#promptNextButton").addEventListener("click", () => {
  state.promptPage += 1;
  state.selectedPrompt = null;
  state.promptVariantCache = {};
  markTabStale("prompts");
  loadCurrentTab({ force: true });
});
function resetPromptSlimPageAndLoad() {
  state.promptSlimPage = 1;
  state.selectedPromptSlim = null;
  markTabStale("prompt-slim");
  if (state.activeTab === "prompt-slim") {
    loadCurrentTab({ force: true });
  }
}
["#promptSlimStageSelect", "#promptSlimSourceSelect", "#promptSlimReasonSelect", "#promptSlimTaskTypeSelect", "#promptSlimSortSelect", "#promptSlimMinUsersInput", "#promptSlimMinUsesInput"].forEach((selector) => {
  const element = $(selector);
  if (element) element.addEventListener("change", resetPromptSlimPageAndLoad);
});
let promptSlimSearchTimer = null;
$("#promptSlimSearchInput").addEventListener("input", () => {
  window.clearTimeout(promptSlimSearchTimer);
  promptSlimSearchTimer = window.setTimeout(resetPromptSlimPageAndLoad, 300);
});
$("#promptSlimPrevButton").addEventListener("click", () => {
  state.promptSlimPage = Math.max(1, state.promptSlimPage - 1);
  state.selectedPromptSlim = null;
  markTabStale("prompt-slim");
  loadCurrentTab({ force: true });
});
$("#promptSlimNextButton").addEventListener("click", () => {
  state.promptSlimPage += 1;
  state.selectedPromptSlim = null;
  markTabStale("prompt-slim");
  loadCurrentTab({ force: true });
});
$("#promptVectorResumeButton").addEventListener("click", resumePromptVectorEmbeddings);
function resetPromptTokenPageAndLoad({ includeFilters = false } = {}) {
  state.promptTokenPage = 1;
  if (state.activeTab === "prompt-tokens") {
    loadPromptTokenTableOnly({ includeFilters }).catch(setError);
    return;
  }
  markTabStale("prompt-tokens");
}

function resetPromptTokenThresholdAndLoad() {
  currentPromptTokenMinPromptCount();
  syncPromptTokenMinPromptCountInput();
  state.promptTokenPage = 1;
  state.promptTokenPromptPage = 1;
  if (state.activeTab === "prompt-tokens") {
    loadPromptTokenTableOnly({ includeFilters: false }).then(() => {
      if (state.selectedPromptToken && $("#promptTokenDrawer")?.classList.contains("open")) {
        loadPromptTokenPrompts().catch(setError);
      }
    });
    return;
  }
  markTabStale("prompt-tokens");
}
$("#promptTokenSearchButton")?.addEventListener("click", resetPromptTokenPageAndLoad);
$("#promptTokenSortSelect")?.addEventListener("change", resetPromptTokenPageAndLoad);
$("#promptTokenTaskTypeSelect")?.addEventListener("change", () => {
  const modelSelect = $("#promptTokenModelSelect");
  if (modelSelect) modelSelect.value = "";
  resetPromptTokenPageAndLoad({ includeFilters: true });
});
$("#promptTokenModelSelect")?.addEventListener("change", resetPromptTokenPageAndLoad);
$("#promptTokenSearchInput")?.addEventListener("input", () => {
  window.clearTimeout(state.promptTokenSearchTimer);
  state.promptTokenSearchTimer = window.setTimeout(resetPromptTokenPageAndLoad, 300);
});
$("#promptTokenMinPromptCountInput")?.addEventListener("input", () => {
  window.clearTimeout(state.promptTokenMinPromptCountTimer);
  if (!$("#promptTokenMinPromptCountInput")?.value) return;
  state.promptTokenMinPromptCountTimer = window.setTimeout(resetPromptTokenThresholdAndLoad, 350);
});
$("#promptTokenMinPromptCountInput")?.addEventListener("change", resetPromptTokenThresholdAndLoad);
$("#promptTokenCustomTermAddButton")?.addEventListener("click", addPromptTokenCustomTermRow);
$("#promptTokenCustomTermSaveButton")?.addEventListener("click", () => {
  savePromptTokenCustomTerms().catch(setError);
});
$("#promptTokenCustomTermRebuildButton")?.addEventListener("click", () => {
  rebuildPromptTokenCustomTerms().catch(setError);
});
$("#promptTokenRuleSeedOverwriteButton")?.addEventListener("click", () => {
  overwritePromptTokenGeneratedRules().catch(setError);
});
$("#promptTokenCustomTermSearchInput")?.addEventListener("input", (event) => {
  state.promptTokenCustomTermSearch = event.target.value || "";
  state.promptTokenCustomTermPage = 1;
  renderPromptTokenCustomTerms();
});
$("#promptTokenCustomTermCategoryTabs")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-category]");
  if (!button) return;
  state.promptTokenCustomTermCategoryFilter = button.dataset.category || "";
  state.promptTokenCustomTermSubcategoryFilter = "";
  state.promptTokenCustomTermPage = 1;
  renderPromptTokenCustomTerms();
});
$("#promptTokenCustomTermSubcategoryTabs")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-subcategory]");
  if (!button) return;
  state.promptTokenCustomTermSubcategoryFilter = button.dataset.subcategory || "";
  state.promptTokenCustomTermPage = 1;
  renderPromptTokenCustomTerms();
});
$("#promptTokenCustomTermPagination")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (!button) return;
  if (!state.promptTokenCustomTerms) return;
  state.promptTokenCustomTermPage = clampPage(
    button.dataset.page,
    Math.ceil((filteredPromptTokenCustomTermRows().length || 0) / PROMPT_TOKEN_RULE_PAGE_SIZE)
  );
  renderPromptTokenCustomTerms();
});
$("#promptTokenCustomTermPagination")?.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!state.promptTokenCustomTerms) return;
  const input = event.target.querySelector("input[type='number']");
  state.promptTokenCustomTermPage = clampPage(
    input?.value,
    Math.ceil((filteredPromptTokenCustomTermRows().length || 0) / PROMPT_TOKEN_RULE_PAGE_SIZE)
  );
  renderPromptTokenCustomTerms();
});
$("#promptTokenCustomTermRows")?.addEventListener("input", (event) => {
  const input = event.target.closest("input[data-field]");
  if (!input) return;
  const row = input.closest("tr[data-index]");
  const index = Number(row?.dataset.index);
  if (!Number.isInteger(index)) return;
  const rows = promptTokenCustomTermRows();
  if (!rows[index]) return;
  rows[index][input.dataset.field] = input.value;
  input.title = input.value;
  markPromptTokenCustomTermsDirty();
});
$("#promptTokenCustomTermRows")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='delete-custom-term']");
  if (!button) return;
  const row = button.closest("tr[data-index]");
  const index = Number(row?.dataset.index);
  if (!Number.isInteger(index)) return;
  promptTokenCustomTermRows().splice(index, 1);
  markPromptTokenCustomTermsDirty();
  renderPromptTokenCustomTerms();
});
$("#promptTokenAliasAddButton")?.addEventListener("click", addPromptTokenAliasRow);
$("#promptTokenAliasSaveButton")?.addEventListener("click", () => {
  savePromptTokenAliases().catch(setError);
});
$("#promptTokenAliasRebuildButton")?.addEventListener("click", () => {
  rebuildPromptTokenAliases().catch(setError);
});
$("#promptTokenAliasSearchInput")?.addEventListener("input", (event) => {
  state.promptTokenAliasSearch = event.target.value || "";
  state.promptTokenAliasPage = 1;
  renderPromptTokenAliases();
});
$("#promptTokenAliasCategoryTabs")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-category]");
  if (!button) return;
  state.promptTokenAliasCategoryFilter = button.dataset.category || "";
  state.promptTokenAliasPage = 1;
  renderPromptTokenAliases();
});
$("#promptTokenAliasRows")?.addEventListener("input", (event) => {
  const input = event.target.closest("input[data-field], textarea[data-field]");
  if (!input) return;
  const row = input.closest("tr[data-index]");
  const index = Number(row?.dataset.index);
  if (!Number.isInteger(index)) return;
  const rows = promptTokenAliasRows();
  if (!rows[index]) return;
  rows[index][input.dataset.field] = input.value;
  input.title = input.value;
  if (input.matches("textarea[data-autoresize]")) {
    resizePromptTokenAliasTextareas(row);
  }
  markPromptTokenAliasesDirty();
});
$("#promptTokenAliasRows")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='delete-alias']");
  if (!button) return;
  const row = button.closest("tr[data-index]");
  const index = Number(row?.dataset.index);
  if (!Number.isInteger(index)) return;
  promptTokenAliasRows().splice(index, 1);
  markPromptTokenAliasesDirty();
  renderPromptTokenAliases();
});
$("#promptTokenAliasPagination")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (!button) return;
  if (!state.promptTokenAliases) return;
  state.promptTokenAliasPage = clampPage(
    button.dataset.page,
    Math.ceil((filteredPromptTokenAliasRows().length || 0) / PROMPT_TOKEN_RULE_PAGE_SIZE)
  );
  renderPromptTokenAliases();
});
$("#promptTokenAliasPagination")?.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!state.promptTokenAliases) return;
  const input = event.target.querySelector("input[type='number']");
  state.promptTokenAliasPage = clampPage(
    input?.value,
    Math.ceil((filteredPromptTokenAliasRows().length || 0) / PROMPT_TOKEN_RULE_PAGE_SIZE)
  );
  renderPromptTokenAliases();
});
$("#promptTokenRows")?.addEventListener("click", (event) => {
  const deleteButton = event.target.closest("button[data-delete-token]");
  if (deleteButton) {
    deletePromptToken(decodeURIComponent(deleteButton.dataset.deleteToken || "")).catch(setError);
    return;
  }
  const button = event.target.closest("button[data-token]");
  if (!button) return;
  openPromptTokenDrawer(decodeURIComponent(button.dataset.token || ""));
});
$("#promptTokenDeletionRows")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-restore-token]");
  if (!button) return;
  restorePromptToken(decodeURIComponent(button.dataset.restoreToken || "")).catch(setError);
});
$("#promptTokenDeletionPagination")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (!button) return;
  if (!state.promptTokenDeletions) return;
  state.promptTokenDeletionPage = clampPage(
    button.dataset.page,
    Math.ceil(((state.promptTokenDeletions?.rows || []).length || 0) / PROMPT_TOKEN_RULE_PAGE_SIZE)
  );
  renderPromptTokenDeletions();
});
$("#promptTokenDeletionPagination")?.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!state.promptTokenDeletions) return;
  const input = event.target.querySelector("input[type='number']");
  state.promptTokenDeletionPage = clampPage(
    input?.value,
    Math.ceil(((state.promptTokenDeletions?.rows || []).length || 0) / PROMPT_TOKEN_RULE_PAGE_SIZE)
  );
  renderPromptTokenDeletions();
});
$("#promptTokenPagination")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (!button) return;
  state.promptTokenPage = clampPage(button.dataset.page, Math.ceil((state.promptTokens?.pagination?.total || 0) / (state.promptTokens?.pagination?.limit || 1)));
  loadPromptTokenTableOnly({ includeFilters: false }).catch(setError);
});
$("#promptTokenPagination")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const totalPages = Math.ceil((state.promptTokens?.pagination?.total || 0) / (state.promptTokens?.pagination?.limit || 1));
  state.promptTokenPage = clampPage($("#promptTokenPageJumpInput")?.value, totalPages);
  loadPromptTokenTableOnly({ includeFilters: false }).catch(setError);
});
$("#promptTokenDrawerClose")?.addEventListener("click", closePromptTokenDrawer);
$("#promptTokenDrawerBackdrop")?.addEventListener("click", closePromptTokenDrawer);
$("#promptTokenPromptPagination")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (!button) return;
  const pagination = state.promptTokenPrompts?.pagination || {};
  state.promptTokenPromptPage = clampPage(button.dataset.page, Math.ceil((pagination.total || 0) / (pagination.limit || 1)));
  loadPromptTokenPrompts().catch(setError);
});
$("#promptTokenPromptPagination")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const pagination = state.promptTokenPrompts?.pagination || {};
  state.promptTokenPromptPage = clampPage($("#promptTokenPromptPageJumpInput")?.value, Math.ceil((pagination.total || 0) / (pagination.limit || 1)));
  loadPromptTokenPrompts().catch(setError);
});
function resetPromptDecompositionPageAndLoad({ includeFilters = false } = {}) {
  state.promptDecompositionPage = 1;
  if (state.activeTab === "prompt-decomposition") {
    loadPromptDecompositionTableOnly({ includeFilters }).catch(setError);
    return;
  }
  markTabStale("prompt-decomposition");
}
$("#promptDecompositionSearchButton")?.addEventListener("click", () => {
  resetPromptDecompositionPageAndLoad({ includeFilters: false });
});
$("#promptDecompositionSearchInput")?.addEventListener("input", () => {
  window.clearTimeout(state.promptDecompositionSearchTimer);
  state.promptDecompositionSearchTimer = window.setTimeout(() => {
    resetPromptDecompositionPageAndLoad({ includeFilters: false });
  }, 300);
});
$("#promptDecompositionClearButton")?.addEventListener("click", () => {
  state.promptDecompositionSelectedTokens = [];
  state.selectedPromptDecomposition = null;
  resetPromptDecompositionPageAndLoad({ includeFilters: false });
});
$("#promptDecompositionSelectedTokenBar")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-remove-token]");
  if (!button) return;
  const normalized = decodeURIComponent(button.dataset.removeToken || "");
  state.promptDecompositionSelectedTokens = promptDecompositionSelectedTokens().filter((token) => token !== normalized);
  resetPromptDecompositionPageAndLoad({ includeFilters: false });
});
$("#promptDecompositionFacetGrid")?.addEventListener("click", (event) => {
  const subgroupButton = event.target.closest("button[data-subgroup-key]");
  if (subgroupButton) {
    state.promptDecompositionActiveSubgroups[subgroupButton.dataset.groupKey || ""] = subgroupButton.dataset.subgroupKey || "";
    renderPromptDecompositionFacets();
    return;
  }
  const tokenButton = event.target.closest("button[data-toggle-token]");
  if (!tokenButton) return;
  const normalized = decodeURIComponent(tokenButton.dataset.toggleToken || "");
  if (!normalized) return;
  const current = promptDecompositionSelectedTokens();
  if (current.includes(normalized)) {
    state.promptDecompositionSelectedTokens = current.filter((token) => token !== normalized);
  } else {
    state.promptDecompositionSelectedTokens = current.concat(normalized);
  }
  resetPromptDecompositionPageAndLoad({ includeFilters: false });
});
$("#promptDecompositionRows")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-open-decomposition]");
  if (!button) return;
  openPromptDecompositionDrawer(button.dataset.openDecomposition || "", button.dataset.source || "live");
});
$("#promptDecompositionSavedRows")?.addEventListener("click", (event) => {
  const deleteButton = event.target.closest("button[data-delete-saved-template]");
  if (deleteButton) {
    deletePromptDecompositionTemplate(deleteButton.dataset.deleteSavedTemplate).catch(setError);
    return;
  }
  const button = event.target.closest("button[data-open-decomposition]");
  if (!button) return;
  openPromptDecompositionDrawer(button.dataset.openDecomposition || "", button.dataset.source || "saved");
});
$("#promptDecompositionPagination")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (!button) return;
  state.promptDecompositionPage = clampPage(button.dataset.page, promptDecompositionTotalPages());
  loadPromptDecompositionTableOnly({ includeFilters: false }).catch(setError);
});
$("#promptDecompositionPagination")?.addEventListener("submit", (event) => {
  event.preventDefault();
  state.promptDecompositionPage = clampPage($("#promptDecompositionPageJumpInput")?.value, promptDecompositionTotalPages());
  loadPromptDecompositionTableOnly({ includeFilters: false }).catch(setError);
});
$("#promptDecompositionDrawerClose")?.addEventListener("click", closePromptDecompositionDrawer);
$("#promptDecompositionDrawerBackdrop")?.addEventListener("click", closePromptDecompositionDrawer);
$("#promptDecompositionSaveTitleInput")?.addEventListener("input", (event) => {
  state.promptDecompositionSaveTitle = event.target.value || "";
});
$("#promptDecompositionSaveButton")?.addEventListener("click", () => {
  savePromptDecompositionTemplate().catch(setError);
});
function resetTemplateCandidatePageAndLoad({ includeFilters = false } = {}) {
  state.templateCandidatePage = 1;
  state.selectedTemplateCandidate = null;
  state.templateCandidatePrompts = null;
  markTabStale("templates");
  if (state.activeTab === "templates") {
    loadTemplateCandidateTableOnly({ includeFilters }).then(() => markTabLoaded("templates")).catch(setError);
  }
}
$("#templateTaskTypeSelect")?.addEventListener("change", () => {
  const modelSelect = $("#templateModelSelect");
  if (modelSelect) modelSelect.value = "";
  resetTemplateCandidatePageAndLoad({ includeFilters: true });
});
$("#templateModelSelect")?.addEventListener("change", resetTemplateCandidatePageAndLoad);
$("#templateSortSelect")?.addEventListener("change", resetTemplateCandidatePageAndLoad);
$("#templateSimilaritySelect")?.addEventListener("change", resetTemplateCandidatePageAndLoad);
$("#templateReviewStatusSelect")?.addEventListener("change", resetTemplateCandidatePageAndLoad);
$("#templateMinPromptsInput")?.addEventListener("input", () => {
  window.clearTimeout(state.templateCandidateSearchTimer);
  if (!$("#templateMinPromptsInput")?.value) return;
  state.templateCandidateSearchTimer = window.setTimeout(resetTemplateCandidatePageAndLoad, 350);
});
$("#templateMinPromptsInput")?.addEventListener("change", resetTemplateCandidatePageAndLoad);
$("#templateSearchInput")?.addEventListener("input", () => {
  window.clearTimeout(state.templateCandidateSearchTimer);
  state.templateCandidateSearchTimer = window.setTimeout(resetTemplateCandidatePageAndLoad, 300);
});
$("#templateRefreshButton")?.addEventListener("click", () => {
  refreshTemplateCandidates().catch(setError);
});
$("#templateReviewMarksButton")?.addEventListener("click", () => {
  openTemplateReviewMarksDrawer().catch(setError);
});
$("#templateCandidateRows")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-template-key]");
  if (!button) return;
  openTemplateCandidateDrawer(decodeURIComponent(button.dataset.templateKey || "")).catch(setError);
});
$("#templateCandidateRows")?.addEventListener("change", (event) => {
  const input = event.target.closest("input[data-template-low-quality-template]");
  if (!input) return;
  const checked = input.checked;
  toggleTemplateCandidateLowQuality(
    decodeURIComponent(input.dataset.templateLowQualityTemplate || ""),
    checked
  ).catch((error) => {
    input.checked = !checked;
    setError(error);
  });
});
$("#templateCandidatePagination")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (!button) return;
  state.templateCandidatePage = clampPage(button.dataset.page, templateCandidateTotalPages());
  loadTemplateCandidateTableOnly({ includeFilters: false }).catch(setError);
});
$("#templateCandidatePagination")?.addEventListener("submit", (event) => {
  event.preventDefault();
  state.templateCandidatePage = clampPage($("#templateCandidatePageJumpInput")?.value, templateCandidateTotalPages());
  loadTemplateCandidateTableOnly({ includeFilters: false }).catch(setError);
});
$("#templateCandidateDrawerClose")?.addEventListener("click", closeTemplateCandidateDrawer);
$("#templateCandidateDrawerBackdrop")?.addEventListener("click", closeTemplateCandidateDrawer);
$("#templateReviewMarksDrawerClose")?.addEventListener("click", closeTemplateReviewMarksDrawer);
$("#templateReviewMarksDrawerBackdrop")?.addEventListener("click", closeTemplateReviewMarksDrawer);
$("#templateReviewMarksSearchInput")?.addEventListener("input", () => {
  window.clearTimeout(state.templateReviewMarksSearchTimer);
  state.templateReviewMarksSearchTimer = window.setTimeout(() => {
    resetTemplateReviewMarksPageAndLoad().catch(setError);
  }, 300);
});
$("#templateReviewMarksSimilaritySelect")?.addEventListener("change", () => {
  resetTemplateReviewMarksPageAndLoad().catch(setError);
});
$("#templateReviewMarksProcessedSelect")?.addEventListener("change", () => {
  resetTemplateReviewMarksPageAndLoad().catch(setError);
});
$("#templateReviewMarksPagination")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (!button) return;
  const pagination = state.templateReviewMarks?.pagination || {};
  const totalPages = Math.max(1, Math.ceil(Number(pagination.total || 0) / Math.max(1, Number(pagination.limit || 1))));
  state.templateReviewMarksPage = clampPage(button.dataset.page, totalPages);
  loadTemplateReviewMarks().catch(setError);
});
$("#templateReviewMarksPagination")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const pagination = state.templateReviewMarks?.pagination || {};
  const totalPages = Math.max(1, Math.ceil(Number(pagination.total || 0) / Math.max(1, Number(pagination.limit || 1))));
  state.templateReviewMarksPage = clampPage($("#templateReviewMarksPageJumpInput")?.value, totalPages);
  loadTemplateReviewMarks().catch(setError);
});
$("#templateReviewMarksCopyAllButton")?.addEventListener("click", () => {
  copyTemplateReviewMarksAll().catch(setError);
});
$("#templateReviewMarksExportButton")?.addEventListener("click", exportTemplateReviewMarksCsv);
$("#templateReviewMarksRows")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-template-review-copy]");
  if (!button) return;
  copyTemplateReviewMarkPrompt(
    decodeURIComponent(button.dataset.templateReviewCopyTemplate || ""),
    decodeURIComponent(button.dataset.templateReviewCopy || "")
  ).catch(setError);
});
$("#templateReviewMarksRows")?.addEventListener("change", (event) => {
  const input = event.target.closest("input[data-template-review-processed]");
  if (!input) return;
  const checked = input.checked;
  toggleTemplateReviewMarkProcessed(
    decodeURIComponent(input.dataset.templateReviewProcessedTemplate || ""),
    decodeURIComponent(input.dataset.templateReviewProcessed || ""),
    checked
  ).catch((error) => {
    input.checked = !checked;
    setError(error);
  });
});
$("#templateCandidatePromptRows")?.addEventListener("change", (event) => {
  const input = event.target.closest("input[data-template-review-prompt]");
  if (!input) return;
  toggleTemplateCandidateReviewMark(
    decodeURIComponent(input.dataset.templateReviewPrompt || ""),
    input.checked
  ).catch((error) => {
    input.checked = !input.checked;
    setError(error);
  });
});
$("#templateCandidatePromptPagination")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (!button) return;
  const pagination = state.templateCandidatePrompts?.pagination || {};
  state.templateCandidatePromptPage = clampPage(button.dataset.page, Math.ceil((pagination.total || 0) / (pagination.limit || 1)));
  loadTemplateCandidatePrompts().catch(setError);
});
$("#templateCandidatePromptPagination")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const pagination = state.templateCandidatePrompts?.pagination || {};
  state.templateCandidatePromptPage = clampPage($("#templateCandidatePromptPageJumpInput")?.value, Math.ceil((pagination.total || 0) / (pagination.limit || 1)));
  loadTemplateCandidatePrompts().catch(setError);
});
document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => setActiveTab(button.dataset.tab));
});
window.addEventListener("hashchange", () => setActiveTab(location.hash.replace("#", ""), false));
window.addEventListener("resize", resizeCharts);

setActiveTab(location.hash.replace("#", "") || "users", false, false);
syncDaysControl();
loadOverviewStatus().catch(setError);
loadCurrentTab({ force: true });
