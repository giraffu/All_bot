export function renderUserVisualChartsView({
  visuals,
  renderChart,
  buildLineBarOption,
  buildDonutOption,
  buildFunnelOption,
  buildHorizontalBarOption,
  chartEmptyOption,
  numeric,
  shortNumber,
}) {
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

export function renderUserGroupsView({
  payload,
  selectedUserGroup,
  query,
  tableRows,
  escapeHtml,
  fmt,
  fmtAmount,
  fmtPercent,
  fmtPeriod,
  fmtSigned,
  onSelect,
}) {
  const rows = payload.rows || [];
  const dimensionLabel = payload.dimension?.label || "人群";
  const filters = payload.filters || {};
  const segmentLabel = query("#userProfileSegmentSelect")?.selectedOptions?.[0]?.textContent || "全部用户";
  const dateLabel = filters.start_date && filters.end_date ? `${filters.start_date} 至 ${filters.end_date}` : fmtPeriod(payload.days);
  const searchLabel = filters.search ? ` · 搜索 ${filters.search}` : "";
  query("#userGroupStatus").textContent = `${dimensionLabel} · ${fmt(rows.length)} 个分桶 · 来自下方列表筛选范围（${dateLabel} · ${segmentLabel}${searchLabel}）`;
  query("#userGroupRows").innerHTML = tableRows(rows, (row) => {
    const isSelected = selectedUserGroup
      && selectedUserGroup.dimension === (payload.dimension?.key || "")
      && selectedUserGroup.group_key === row.group_key;
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
    const select = () => onSelect(row.dataset.groupKey || "", row.dataset.groupLabel || "");
    row.addEventListener("click", select);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select();
      }
    });
  });
}
