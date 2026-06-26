const state = {
  users: null,
  creditFlow: null,
  overview: null,
  finance: null,
  generation: null,
  prompts: null,
  promptSlim: null,
  promptVectors: null,
  promptVectorDetail: null,
  templates: null,
  media: null,
  promptTaskTypes: [],
  promptVariantCache: {},
  selectedPrompt: null,
  selectedPromptSlim: null,
  selectedPromptVectorCluster: null,
  promptPage: 1,
  promptSlimPage: 1,
  promptVectorPage: 1,
  activeTab: "users",
  tabDays: {
    users: 30,
    "credit-flow": 30,
    finance: 30,
    generation: 30,
    prompts: 30,
    "prompt-slim": 0,
    "prompt-vectors": 0,
    templates: 30,
    media: 30,
  },
  loadedTabs: {},
  tabUpdatedAt: {},
};

const tabs = {
  users: {
    kicker: "用户画像",
    title: "用户增长、活跃和分层",
    subtitle: "增长、活跃、身份、灵石和用户排行",
  },
  "credit-flow": {
    kicker: "灵石收支",
    title: "灵石收入、支出和健康度",
    subtitle: "来源、消耗、风险用户复核",
  },
  finance: {
    kicker: "充值情况",
    title: "订单、渠道、套餐和付费健康度",
    subtitle: "成功订单、RMB / TON / Stars、发放灵石和复购分层",
  },
  generation: {
    kicker: "生成分析",
    title: "生成趋势、质量和消耗效率",
    subtitle: "任务类型、来源、质量漏斗、用户排行和高信号作品",
  },
  prompts: {
    kicker: "提示词洞察",
    title: "提示词复用、任务类型和互动价值",
    subtitle: "排除一键应用衍生记录，聚合相同提示词和高价值信号",
  },
  "prompt-slim": {
    kicker: "提示词瘦身",
    title: "提示词候选、剔除规则和信号检查",
    subtitle: "读取持久化瘦身宽表，检查候选、低质原因和反馈信号",
  },
  "prompt-vectors": {
    kicker: "向量相似",
    title: "提示词语义相似簇审核",
    subtitle: "读取持久化向量与相似簇表，只在同任务类型内生成审核候选",
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

function currentDays() {
  return Number(state.tabDays[state.activeTab] ?? 30);
}

function setCurrentDays(days) {
  state.tabDays[state.activeTab] = Number.isFinite(Number(days)) ? Number(days) : 30;
}

function syncDaysControl() {
  const select = $("#daysSelect");
  if (!select) return;
  const lockedAllTimeTabs = new Set(["prompt-slim", "prompt-vectors"]);
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

function setActiveTab(tabName, syncHash = true, shouldLoad = true) {
  const requested = tabName === "overview" ? "generation" : tabName;
  const tab = tabs[requested] ? requested : "users";
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
  syncDaysControl();
  renderLastUpdated();
  if (syncHash || tabName === "overview") {
    history.replaceState(null, "", `#${tab}`);
  }
  if (shouldLoad) {
    loadCurrentTab();
  }
}

function renderUsers() {
  const summary = state.users?.summary || {};
  const period = fmtPeriod(state.users?.days);
  $("#userSummary").innerHTML = [
    metric("总用户", fmt(summary.total_users), `${period}新增 ${fmt(summary.new_users)}`),
    metric("近周期活跃", fmt(summary.active_users), "按生成记录去重"),
    metric("入宗门用户", fmt(summary.channel_members), "is_channel_member"),
    metric("密码用户", fmt(summary.password_users), "Web 登录账号"),
    metric("真实付费用户", fmt(summary.paying_users), "RMB / TON / Stars"),
    metric("生成用户", fmt(summary.generation_users), "generation_count > 0"),
    metric("持有灵石", fmt(summary.total_credits), `活跃用户持有 ${fmt(summary.active_credits)}`),
    metric("投稿封禁", fmt(summary.submission_banned_users), "is_submission_banned"),
  ].join("");

  renderSpark("#userNewSpark", state.users?.daily || [], "new_users");
  renderSpark("#userActiveSpark", state.users?.daily || [], "active_users");
  renderSpark("#userCheckinSpark", state.users?.daily || [], "checkins");

  const distributions = state.users?.distributions || {};
  renderDistribution("#identityDistribution", distributions.identity || []);
  renderDistribution("#groupDistribution", distributions.user_group || []);
  renderDistribution("#creditDistribution", distributions.credit_holding || []);
  renderDistribution("#generationDistribution", distributions.generation_count || []);
  renderDistribution("#activityDistribution", distributions.activity_segments || []);

  const leaderboards = state.users?.leaderboards || {};
  renderUserLeaderboard("#generationLeaderboard", leaderboards.generation, (row) => fmt(row.generation_count), (row) => fmtDate(row.last_activity));
  renderUserLeaderboard("#creditsLeaderboard", leaderboards.credits, (row) => fmt(row.credits), (row) => fmt(row.generation_count));
  renderUserLeaderboard("#referralsLeaderboard", leaderboards.referrals, (row) => fmt(row.referral_count), (row) => row.is_channel_member ? "是" : "否");
  renderUserLeaderboard("#recentActiveLeaderboard", leaderboards.recent_active, (row) => fmtDate(row.last_activity), (row) => fmt(row.credits));
}

function renderCreditFlow() {
  const summary = state.creditFlow?.summary || {};
  const health = state.creditFlow?.health || {};
  $("#creditFlowSummary").innerHTML = [
    metric("收支净额", fmtSigned(summary.net_change), `收入 ${fmt(summary.gross_income)} / 支出 ${fmt(summary.gross_expense)}`),
    metric("支出覆盖", fmtPercent(health.expense_coverage_ratio), `日均支出 ${fmtAmount(summary.avg_daily_expense)}`),
    metric("付费充值占比", fmtPercent(health.paid_recharge_ratio), `充值 ${fmt(summary.paid_recharge_income)}`),
    metric("非付费发放", fmtPercent(health.non_paid_grant_ratio), `签到/邀请等 ${fmt(summary.non_paid_grant_income)}`),
    metric("退款率", fmtPercent(health.refund_to_generation_ratio), `退款 ${fmt(summary.refund_income)} / 生成 ${fmt(summary.generation_expense)}`),
    metric("余额可消耗", fmtAmount(summary.balance_burn_days, " 天"), `当前余额 ${fmt(summary.current_total_credits)}`),
    metric("收入集中度", fmtPercent(health.top_income_user_share), `签到压力 ${fmtPercent(health.checkin_pressure_ratio)}`),
    metric("内部转移", fmt(summary.internal_transfer_income), `Gallery 支出 ${fmt(summary.internal_transfer_expense)}`),
  ].join("");

  const daily = state.creditFlow?.daily || [];
  renderSpark("#creditIncomeSpark", daily, "income");
  renderSpark("#creditExpenseSpark", daily, "expense");
  renderSpark("#creditNetSpark", daily, "net_change", { absolute: true, signed: true });

  const categories = state.creditFlow?.categories || [];
  renderAmountDistribution(
    "#creditIncomeCategories",
    categories.filter((row) => row.direction === "income" && Number(row.income || 0) > 0),
    "income"
  );
  renderAmountDistribution(
    "#creditExpenseCategories",
    categories.filter((row) => row.direction === "expense" && Number(row.expense || 0) > 0),
    "expense"
  );

  const composition = state.creditFlow?.composition || {};
  renderAmountDistribution("#creditCompositionIdentity", composition.identity || [], "income");
  renderAmountDistribution("#creditCompositionGroup", composition.user_group || [], "income");
  renderAmountDistribution("#creditCompositionChannel", composition.channel_member || [], "income");
  renderAmountDistribution("#creditCompositionPayer", composition.payer || [], "income");
  renderHealthFlags(health.flags || []);
  renderCreditRiskUsers(state.creditFlow?.risk_users || []);
}

function renderSpark(selector, rows, key, options = {}) {
  const values = rows.map((row) => {
    const raw = Number(row[key] || 0);
    return options.absolute ? Math.abs(raw) : Math.max(raw, 0);
  });
  const max = Math.max(1, ...values);
  $(selector).innerHTML = rows
    .map((row, index) => {
      const raw = Number(row[key] || 0);
      const height = Math.max(4, Math.round((values[index] / max) * 86));
      const display = options.signed ? fmtSigned(raw) : fmt(raw);
      const className = raw < 0 ? "spark-bar negative" : "spark-bar";
      return `<div class="${className}" style="height:${height}px" title="${escapeHtml(row.day)}: ${display}"></div>`;
    })
    .join("");
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

function renderFunnelDistribution(selector, rows = [], total = 0) {
  if (!rows.length) {
    $(selector).innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  const denominator = Math.max(1, Number(total || 0));
  $(selector).innerHTML = rows
    .map((row) => {
      const count = Number(row.count || 0);
      const width = Math.max(2, Math.min(100, Math.round((count / denominator) * 100)));
      const share = `${Math.round((count / denominator) * 1000) / 10}%`;
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

function renderAmountDistribution(selector, rows = [], valueKey = "income") {
  if (!rows.length) {
    $(selector).innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  const total = rows.reduce((sum, row) => sum + Number(row[valueKey] || 0), 0);
  const max = Math.max(1, ...rows.map((row) => Number(row[valueKey] || 0)));
  $(selector).innerHTML = rows
    .map((row) => {
      const value = Number(row[valueKey] || 0);
      const width = Math.max(2, Math.round((value / max) * 100));
      const share = total ? `${Math.round((value / total) * 1000) / 10}%` : "0%";
      const label = row.label || row.category || "-";
      const detail = `${fmt(row.users)} 人 · ${fmt(row.events)} 次`;
      return `
        <div class="distribution-row amount-row">
          <div class="distribution-meta">
            <span>${escapeHtml(label)}</span>
            <strong>${fmt(value)}</strong>
            <small>${detail}</small>
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

function renderHealthFlags(flags = [], selector = "#creditHealthFlags") {
  $(selector).innerHTML = flags.length
    ? flags.map((flag) => `<span class="pill ${flag.includes("未触发") ? "gray" : "amber"}">${escapeHtml(flag)}</span>`).join("")
    : '<span class="muted">暂无风险标记</span>';
}

function renderUserIdentity(row) {
  return `
    <div class="user-cell">
      <strong>${escapeHtml(row.full_name || "未知用户")}</strong>
      <span>ID ${fmt(row.id)} · @${escapeHtml(row.username || "n/a")}</span>
      ${row.is_submission_banned ? '<span class="status-badge danger">投稿封禁</span>' : ""}
    </div>
  `;
}

function renderUserBadge(row, key = "current_identity") {
  const value = row[key] || (key === "user_group" ? "凡人" : "外门弟子");
  const badgeClass = key === "user_group" ? "group" : "identity";
  return `<span class="status-badge ${badgeClass}">${escapeHtml(value)}</span>`;
}

function renderUserLeaderboard(selector, rows = [], valueRenderer, noteRenderer) {
  $(selector).innerHTML = tableRows(rows, (row) => `
    <tr>
      <td>${renderUserIdentity(row)}</td>
      <td>
        ${renderUserBadge(row)}
        <div class="muted small">${escapeHtml(row.user_group || "凡人")}</div>
      </td>
      <td><strong>${valueRenderer(row)}</strong></td>
      <td>${noteRenderer(row)}</td>
    </tr>
  `);
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
          <div>签到 ${fmt(row.checkin_income)} · 邀请 ${fmt(row.referral_income)}</div>
          <div>退款 ${fmt(row.refund_income)} · 充值 ${fmt(row.recharge_income)}</div>
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

function renderFinanceHourly() {
  const rows = state.finance?.hourly || [];
  const byHour = new Map(rows.map((row) => [Number(row.hour), row]));
  const max = Math.max(1, ...rows.map((row) => Number(row.plan_reward_credits || 0)));
  $("#financeHourlyBars").innerHTML = Array.from({ length: 24 }, (_, hour) => {
    const row = byHour.get(hour) || { success_orders: 0, plan_reward_credits: 0 };
    const height = Math.max(5, Math.round((Number(row.plan_reward_credits || 0) / max) * 100));
    const title = `${hour}:00 订单 ${fmt(row.success_orders)} · 灵石 ${fmt(row.plan_reward_credits)} · RMB ${fmtAmount(row.rmb_amount)}`;
    return `
      <div class="hour-slot">
        <div class="hourly-bar finance-hourly-bar" style="height:${height}px" title="${escapeHtml(title)}"></div>
        <span>${hour}</span>
      </div>
    `;
  }).join("");
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
  renderSpark("#financeRevenueSpark", daily, "usdt_amount");
  renderSpark("#financeCreditsSpark", daily, "plan_reward_credits");
  renderSpark("#financeOrdersSpark", daily, "success_orders");
  renderFinanceHourly();

  renderAmountDistribution(
    "#financeChannelDistribution",
    (state.finance?.channels || []).map((row) => ({
      label: channelLabel(row.channel),
      income: row.usdt_amount,
      users: row.payers,
      events: row.success_orders,
    })),
    "income"
  );
  renderAmountDistribution(
    "#financePlanDistribution",
    (state.finance?.plans || []).map((row) => ({
      label: row.plan_name,
      income: row.usdt_amount,
      users: row.payers,
      events: row.success_orders,
    })),
    "income"
  );
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

  const daily = state.generation?.daily || [];
  renderSpark("#generationVolumeSpark", daily, "generations");
  renderSpark("#generationCreditsSpark", daily, "credits_spent");
  renderSpark("#generationFailuresSpark", daily, "worker_failures");

  renderAmountDistribution(
    "#generationSourceMix",
    (state.generation?.source_mix || []).map((row) => ({
      label: row.label,
      count: row.count,
      users: row.creators,
      events: row.count,
    })),
    "count"
  );
  renderFunnelDistribution("#generationQualitySegments", state.generation?.quality_segments || [], summary.generations);
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

function renderPromptVectorOptionSet(selector, rows = [], staticOptions = []) {
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

function renderPromptVectorFilterOptions() {
  const distributions = state.promptVectors?.distributions || {};
  renderPromptVectorOptionSet(
    "#promptVectorTaskTypeSelect",
    distributions.task_type || [],
    [{ value: "", label: "全部" }]
  );
}

function renderPromptVectorSummary() {
  const summary = state.promptVectors?.summary || {};
  const model = state.promptVectors?.model || {};
  if (state.promptVectors && state.promptVectors.ready === false) {
    $("#promptVectorSummary").innerHTML = [
      metric("向量表状态", "未构建", state.promptVectors.message || "等待刷新命令"),
      metric("模型", escapeHtml(model.model_id || "-"), escapeHtml(model.model_key || "-")),
      metric("候选覆盖", "0%", "先运行 pilot 或全量向量化"),
      metric("相似簇", "0", "暂无审核候选"),
    ].join("");
    return;
  }
  $("#promptVectorSummary").innerHTML = [
    metric("候选提示词", fmt(summary.candidate_count), "quality_stage = candidate"),
    metric("已向量化", fmt(summary.embedded_count), `覆盖 ${fmtAmount(summary.embedding_coverage)}%`),
    metric("相似边", fmt(summary.edge_count), `重复 ${fmt(summary.duplicate_edge_count)} · 相似 ${fmt(summary.similar_edge_count)}`),
    metric("审核簇", fmt(summary.cluster_count), `成员 ${fmt(summary.clustered_prompts)}`),
    metric("模型", escapeHtml(model.model_id || "-"), `维度 ${fmt(model.embedding_dim)}`),
    metric("刷新", fmtDate(summary.latest_refreshed_at || model.last_success_at), model.last_error ? `错误 ${model.last_error}` : "向量索引可重建"),
  ].join("");
}

function renderPromptVectorDistributions() {
  const distributions = state.promptVectors?.distributions || {};
  renderDistribution("#promptVectorTaskTypeDistribution", distributions.task_type || []);
  renderDistribution("#promptVectorSizeDistribution", distributions.cluster_size || []);
  renderDistribution("#promptVectorBandDistribution", (distributions.band || []).map((row) => ({
    ...row,
    label: row.label === "duplicate" ? "疑似重复" : "相似邻居",
  })));
}

function renderPromptVectorSignalText(row = {}) {
  return `
    <div>总使用 ${fmt(row.total_uses)} · 总用户 ${fmt(row.total_users)}</div>
    <div class="muted small">代表 ${fmt(row.representative_uses)} 次 / ${fmt(row.representative_users)} 人</div>
    <div class="muted small">赞 ${fmt(row.representative_result_likes)} · 应用 ${fmt(row.representative_gallery_applies)} · 解锁 ${fmt(row.representative_prompt_unlocks)}</div>
  `;
}

function renderPromptVectors() {
  renderPromptVectorFilterOptions();
  renderPromptVectorSummary();
  renderPromptVectorDistributions();

  const rows = state.promptVectors?.clusters || [];
  if (!state.selectedPromptVectorCluster || !rows.some((item) => item.cluster_id === state.selectedPromptVectorCluster.cluster_id)) {
    state.selectedPromptVectorCluster = rows[0] || null;
    state.promptVectorDetail = null;
  }

  $("#promptVectorRows").innerHTML = tableRows(rows, (row) => `
    <tr data-cluster-id="${escapeHtml(row.cluster_id)}" class="${state.selectedPromptVectorCluster?.cluster_id === row.cluster_id ? "selected-row" : ""}">
      <td>
        <strong>${fmt(row.member_count)}</strong> 条
        <div class="muted small">均值 ${fmtAmount(Number(row.avg_similarity || 0) * 100)}%</div>
        <div class="muted small">${fmtAmount(Number(row.min_similarity || 0) * 100)}% - ${fmtAmount(Number(row.max_similarity || 0) * 100)}%</div>
      </td>
      <td>
        <div class="prompt-preview">${escapeHtml(row.representative_preview)}</div>
        <div class="pill-list">
          <span class="pill gray">${escapeHtml(row.task_type || "-")}</span>
          <span class="pill">质量 ${fmtAmount(row.quality_score)}</span>
        </div>
      </td>
      <td>${renderPromptVectorSignalText(row)}</td>
      <td>
        <div>重复边 ${fmt(row.duplicate_edge_count)}</div>
        <div class="muted small mono">${escapeHtml(row.representative_hash || "-")}</div>
      </td>
      <td>
        <div>${fmtDate(row.refreshed_at)}</div>
        <div class="muted small">${fmtDate(row.last_seen)}</div>
      </td>
    </tr>
  `);

  document.querySelectorAll("#promptVectorRows tr").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedPromptVectorCluster = rows.find((item) => item.cluster_id === row.dataset.clusterId) || rows[0] || null;
      state.promptVectorDetail = null;
      renderPromptVectors();
      if (state.selectedPromptVectorCluster) {
        loadPromptVectorDetail(state.selectedPromptVectorCluster.cluster_id).catch(setError);
      }
    });
  });

  const pagination = state.promptVectors?.pagination || {};
  const total = Number(pagination.total || 0);
  $("#promptVectorPageInfo").textContent = `第 ${fmt(pagination.page || 1)} 页 · 共 ${fmt(total)} 簇`;
  $("#promptVectorPrevButton").disabled = Number(pagination.page || 1) <= 1;
  $("#promptVectorNextButton").disabled = !pagination.has_next;

  renderPromptVectorDetail();
}

function renderPromptVectorDetail() {
  const selected = state.selectedPromptVectorCluster;
  if (!selected) {
    $("#promptVectorDetail").innerHTML = '<div class="empty">暂无相似簇</div>';
    return;
  }
  if (!state.promptVectorDetail || state.promptVectorDetail.cluster?.cluster_id !== selected.cluster_id) {
    $("#promptVectorDetail").innerHTML = `
      <h3>相似簇 · ${fmt(selected.member_count)} 条</h3>
      <p class="prompt-fulltext">${escapeHtml(selected.representative_prompt || selected.representative_preview || "")}</p>
      <div class="empty compact">正在加载成员</div>
    `;
    return;
  }
  const cluster = state.promptVectorDetail.cluster || selected;
  const members = state.promptVectorDetail.members || [];
  $("#promptVectorDetail").innerHTML = `
    <h3>${escapeHtml(cluster.task_type || "-")} · ${fmt(cluster.member_count)} 条相似提示词</h3>
    <p class="prompt-fulltext">${escapeHtml(cluster.representative_prompt || cluster.representative_preview || "")}</p>
    <dl>
      <dt>Cluster</dt><dd class="mono">${escapeHtml(cluster.cluster_id)}</dd>
      <dt>代表 Hash</dt><dd class="mono">${escapeHtml(cluster.representative_hash)}</dd>
      <dt>相似度</dt><dd>均值 ${fmtAmount(Number(cluster.avg_similarity || 0) * 100)}% · 最低 ${fmtAmount(Number(cluster.min_similarity || 0) * 100)}%</dd>
      <dt>总信号</dt><dd>使用 ${fmt(cluster.total_uses)} · 用户 ${fmt(cluster.total_users)} · 质量 ${fmtAmount(cluster.quality_score)}</dd>
      <dt>刷新</dt><dd>${fmtDate(cluster.refreshed_at)}</dd>
    </dl>
    <div class="cluster-member-list">
      ${members.map((member) => `
        <div class="cluster-member ${member.is_representative ? "representative" : ""}">
          <div class="cluster-member-head">
            <span class="pill ${member.is_representative ? "" : "gray"}">${member.is_representative ? "代表项" : `相似 ${fmtAmount(Number(member.similarity_to_representative || 0) * 100)}%`}</span>
            <span class="muted small">使用 ${fmt(member.uses)} · 用户 ${fmt(member.users)} · 质量 ${fmtAmount(member.quality_score)}</span>
          </div>
          <div class="cluster-member-prompt">${escapeHtml(member.prompt_preview || member.prompt || "-")}</div>
          <div class="muted small">结果赞 ${fmt(member.result_likes)} · 踩 ${fmt(member.result_dislikes)} · Gallery 应用 ${fmt(member.gallery_applies)} · 解锁 ${fmt(member.prompt_unlocks)}</div>
        </div>
      `).join("") || '<div class="empty compact">暂无成员</div>'}
    </div>
  `;
}

function renderTemplateCandidates(source = state.templates) {
  const candidates = (source?.candidates || [])
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
    metric("采样记录", fmt((state.media?.records || []).length), fmtPeriod(state.media?.days)),
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

function renderPromptTaskTypeOptions() {
  const select = $("#taskTypeSelect");
  const existing = select.value;
  const allowed = new Set(state.promptTaskTypes.map((row) => row.task_type).filter(Boolean));
  const selected = existing && allowed.has(existing) ? existing : "";
  const options = ['<option value="">全部</option>'].concat(
    state.promptTaskTypes.map((row) => `<option value="${escapeHtml(row.task_type)}">${escapeHtml(row.task_type)}</option>`)
  );
  select.innerHTML = options.join("");
  select.value = selected;
  return selected;
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
  return {
    task_type: $("#promptVectorTaskTypeSelect")?.value || "",
    min_similarity: Number($("#promptVectorMinSimilaritySelect")?.value || 0.92),
    min_size: Number($("#promptVectorMinSizeInput")?.value || 2),
    q: $("#promptVectorSearchInput")?.value?.trim() || "",
    sort: $("#promptVectorSortSelect")?.value || "member_count",
    page: state.promptVectorPage,
    limit: 40,
  };
}

function getTemplatePromptParams(days = currentDays()) {
  return {
    days,
    task_type: "",
    template_scope: "natural",
    q: "",
    min_users: 1,
    min_uses: 1,
    sort: "value_score",
    page: 1,
    limit: 40,
  };
}

async function loadOverviewStatus() {
  state.overview = await fetchJson("/api/overview", { days: currentDays() });
  renderSource();
}

async function loadUsers(days) {
  state.users = await fetchJson("/api/user-analytics", { days, limit: 12 });
  renderUsers();
}

async function loadCreditFlow(days) {
  state.creditFlow = await fetchJson("/api/credit-flow-analytics", { days, limit: 12 });
  renderCreditFlow();
}

async function loadFinance(days) {
  state.finance = await fetchJson("/api/finance", { days, limit: 12 });
  renderFinance();
}

async function loadGeneration(days) {
  state.generation = await fetchJson("/api/generation", { days, limit: 12 });
  renderGeneration();
}

async function loadPrompts(days) {
  const generation = await fetchJson("/api/generation", { days, limit: 12 });
  state.promptTaskTypes = generation.by_type || [];
  renderPromptTaskTypeOptions();
  state.prompts = await fetchJson("/api/prompts", getPromptParams(days));
  renderPrompts();
}

async function loadPromptSlim() {
  state.promptSlim = await fetchJson("/api/prompt-slim", getPromptSlimParams());
  renderPromptSlim();
}

async function loadPromptVectors() {
  state.promptVectors = await fetchJson("/api/prompt-vectors", getPromptVectorParams());
  const rows = state.promptVectors?.clusters || [];
  if (!state.selectedPromptVectorCluster || !rows.some((row) => row.cluster_id === state.selectedPromptVectorCluster.cluster_id)) {
    state.selectedPromptVectorCluster = rows[0] || null;
    state.promptVectorDetail = null;
  }
  renderPromptVectors();
  if (state.selectedPromptVectorCluster && state.promptVectors?.ready !== false) {
    await loadPromptVectorDetail(state.selectedPromptVectorCluster.cluster_id);
  }
}

async function loadPromptVectorDetail(clusterId) {
  if (!clusterId) return;
  state.promptVectorDetail = await fetchJson(`/api/prompt-vectors/clusters/${encodeURIComponent(clusterId)}`);
  renderPromptVectorDetail();
}

async function loadTemplates(days) {
  state.templates = await fetchJson("/api/prompts", getTemplatePromptParams(days));
  renderTemplateCandidates(state.templates);
}

async function loadMedia(days) {
  state.media = await fetchJson("/api/media-audit", { days, limit: 100 });
  renderMedia();
}

const tabLoaders = {
  users: loadUsers,
  "credit-flow": loadCreditFlow,
  finance: loadFinance,
  generation: loadGeneration,
  prompts: loadPrompts,
  "prompt-slim": loadPromptSlim,
  "prompt-vectors": loadPromptVectors,
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
  if (state.activeTab === "prompts") {
    state.promptPage = 1;
    state.selectedPrompt = null;
    state.promptVariantCache = {};
  }
  if (state.activeTab === "prompt-slim") {
    state.promptSlimPage = 1;
    state.selectedPromptSlim = null;
  }
  if (state.activeTab === "prompt-vectors") {
    state.promptVectorPage = 1;
    state.selectedPromptVectorCluster = null;
    state.promptVectorDetail = null;
  }
  markTabStale(state.activeTab);
  loadCurrentTab({ force: true });
}

$("#refreshButton").addEventListener("click", reloadCurrentTab);
$("#daysSelect").addEventListener("change", () => {
  setCurrentDays(selectNumber("#daysSelect", 30));
  reloadCurrentTab();
});
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
function resetPromptVectorPageAndLoad() {
  state.promptVectorPage = 1;
  state.selectedPromptVectorCluster = null;
  state.promptVectorDetail = null;
  markTabStale("prompt-vectors");
  if (state.activeTab === "prompt-vectors") {
    loadCurrentTab({ force: true });
  }
}
["#promptVectorTaskTypeSelect", "#promptVectorMinSimilaritySelect", "#promptVectorMinSizeInput", "#promptVectorSortSelect"].forEach((selector) => {
  const element = $(selector);
  if (element) element.addEventListener("change", resetPromptVectorPageAndLoad);
});
let promptVectorSearchTimer = null;
$("#promptVectorSearchInput").addEventListener("input", () => {
  window.clearTimeout(promptVectorSearchTimer);
  promptVectorSearchTimer = window.setTimeout(resetPromptVectorPageAndLoad, 300);
});
$("#promptVectorPrevButton").addEventListener("click", () => {
  state.promptVectorPage = Math.max(1, state.promptVectorPage - 1);
  state.selectedPromptVectorCluster = null;
  state.promptVectorDetail = null;
  markTabStale("prompt-vectors");
  loadCurrentTab({ force: true });
});
$("#promptVectorNextButton").addEventListener("click", () => {
  state.promptVectorPage += 1;
  state.selectedPromptVectorCluster = null;
  state.promptVectorDetail = null;
  markTabStale("prompt-vectors");
  loadCurrentTab({ force: true });
});
document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => setActiveTab(button.dataset.tab));
});
window.addEventListener("hashchange", () => setActiveTab(location.hash.replace("#", ""), false));

setActiveTab(location.hash.replace("#", "") || "users", false, false);
syncDaysControl();
loadOverviewStatus().catch(setError);
loadCurrentTab({ force: true });
