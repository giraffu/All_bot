from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "local_analytics_platform" / "static"


def test_core_tabs_use_echarts_mount_points_instead_of_spark_bars():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((STATIC_DIR / "js").glob("*.js"))
    )

    assert "/static/vendor/echarts.min.js" in html
    assert "/static/styles.css?v=20260705-auth-v1" in html
    assert 'type="module" src="/static/js/bootstrap.js?v=20260706-modules-v1"' in html
    assert "spark-bars" not in html
    assert "hourly-bars" not in html
    assert "renderChart(id, option)" in app_js
    assert "buildLineBarOption" in app_js
    assert "buildDonutOption" in app_js
    assert "buildStackedBarOption" in app_js
    assert 'data-tab="prompt-vectors"' in html
    assert "提示词向量化" in html
    for removed in [
        'data-tab="prompt-graph"',
        'data-tab="prompt-near-representatives"',
        'data-tab="prompt-near-graph"',
        'data-tab="prompt-scenes"',
        'id="promptNearThresholdRange"',
        'id="promptNearGraphChart"',
        'id="promptSceneRows"',
        'id="promptGraphChart"',
        "/api/prompt-near-representatives",
        "/api/prompt-near-graph",
        "/api/prompt-scenes",
        "/api/prompt-graph",
        "/api/prompt-vectors/clusters",
        "renderPromptGraph",
        "renderPromptNearGraph",
        "renderPromptNearRepresentatives",
        "renderPromptScenes",
    ]:
        assert removed not in html
        assert removed not in app_js
    assert 'value="centroid_bridge"' not in html
    assert "renderTemplateCandidates(state.templates)" in app_js
    assert "function renderTemplateCandidates(payload)" in app_js
    assert "function tableRows(rows = [], renderer)" in app_js
    assert "function renderPromptTaskTypeOptions()" in app_js
    assert "state.promptTaskTypes = state.prompts?.distributions?.task_type || []" in app_js
    assert "state.promptTaskTypes = generation.by_type || []" not in app_js

    for mount_id in [
        "creditFlowTrendChart",
        "financeTrendChart",
        "financeHourlyChart",
        "generationTrendChart",
        "generationCompareChart",
        "userCoreTrendChart",
        "userTrustCompositionChart",
        "userConversionFunnelChart",
        "userDailyActivityChart",
        "userRechargeRateChart",
    ]:
        assert f'id="{mount_id}"' in html

    for removed_user_mount in [
        "userTrendChart",
        "userConversionChart",
        "referralConversionChart",
        "identityDistributionChart",
        "groupDistributionChart",
        "creditDistributionChart",
        "generationDistributionChart",
        "activityDistributionChart",
        "generationLeaderboard",
        "creditsLeaderboard",
        "referralsLeaderboard",
        "lowTrustLeaderboard",
        "recentActiveLeaderboard",
    ]:
        assert f'id="{removed_user_mount}"' not in html

    assert 'id="userRechargeRates"' in html
    assert 'id="userSummary" class="metric-grid user-metric-grid"' in html
    assert 'id="userRechargeRates" class="metric-grid user-metric-grid user-rate-grid"' in html
    assert 'id="daysSelectControl"' in html
    assert 'id="logoutButton"' in html
    assert 'id="userDateRangeControls"' in html
    assert 'id="userStartDateInput"' in html
    assert 'id="userEndDateInput"' in html
    assert 'id="userGroupRows"' in html
    assert 'id="userGroupDimensionSelect"' in html
    assert 'id="userGroupSegmentSelect"' not in html
    assert 'id="userGroupSortSelect"' in html
    assert 'id="userGroupLimitSelect"' in html
    assert 'id="userGroupSelectionLabel"' in html
    assert 'id="userGroupClearButton"' in html
    assert 'id="userProfileRows"' in html
    assert 'id="userProfileDrawer"' in html
    assert 'id="userProfileSearchInput"' in html
    assert 'id="userProfileSegmentSelect"' in html
    assert 'id="userProfileSortSelect"' in html
    assert "人群透视分析" in html
    assert "人群下钻用户列表" in html
    assert "人群规模趋势" in html
    assert "核心规模趋势" not in html
    assert "renderUserGroups" in app_js
    assert "renderUserVisualCharts" in app_js
    assert "userCoreTrendChart" in app_js
    assert '"从未活跃": false' in app_js
    assert '"低信任": false' in app_js
    assert 'name: "人群指标", scale: true' in app_js
    assert "userTrustCompositionChart" in app_js
    assert "userConversionFunnelChart" in app_js
    assert "userDailyActivityChart" in app_js
    assert "userRechargeRateChart" in app_js
    assert "selectUserGroup" in app_js
    assert "userPeriodParams" in app_js
    assert "logoutLocalAnalytics" in app_js
    assert "/api/auth/logout" in app_js
    assert "/login?next=" in app_js
    assert "currentUserDateRange" in app_js
    assert "start_date" in app_js
    assert "userGroupSegmentSelect" not in app_js
    assert "renderUserCharts" not in app_js
    assert "renderReferralLeaderboard" not in app_js
    assert "renderLowTrustLeaderboard" not in app_js
    assert "renderUserProfileList" in app_js
    assert "openUserProfile" in app_js
    assert "renderUserProfileDetail" in app_js
    assert "/api/user-analytics/groups" in app_js
    assert "/api/user-analytics/users" in app_js
    assert "visualizations" in app_js
    assert "low_trust_exempt_users" in app_js
    assert "never_active_users" in app_js
    assert "dormant_users" in app_js
    assert "recharge_rate_total_users" in app_js
    assert "avg_inviter_invitee_recharge_rate" in app_js
    assert "invitee_recharge_rate" in app_js
    assert "低信任免费层" in app_js


def test_local_analytics_login_static_page_exists():
    login_html = (STATIC_DIR / "login.html").read_text(encoding="utf-8")

    assert "本地数据分析平台" in login_html
    assert "/api/auth/login" in login_html
    assert "autocomplete=\"username\"" in login_html
    assert "autocomplete=\"current-password\"" in login_html
