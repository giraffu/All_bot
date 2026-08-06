from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "local_analytics_platform" / "static"


def test_core_tabs_use_echarts_mount_points_instead_of_spark_bars():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    app_js = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((STATIC_DIR / "js").glob("*.js"))
    )

    assert "/static/vendor/echarts.min.js" in html
    assert "/static/styles.css?v=20260806-nas-history-media-v2" in html
    assert 'type="module" src="/static/js/bootstrap.js?v=20260806-nas-history-media-v2"' in html
    assert 'from "./state.js?v=20260805-generation-history-v1"' in app_js
    assert "await response.text()" in app_js
    assert "JSON.parse(rawBody)" in app_js
    assert "await response.json()" not in app_js
    assert "spark-bars" not in html
    assert "hourly-bars" not in html
    assert "renderChart(id, option)" in app_js
    assert "buildLineBarOption" in app_js
    assert "buildDonutOption" in app_js
    assert "buildStackedBarOption" in app_js
    assert 'data-tab="prompt-vectors"' in html
    assert 'data-tab="generation-history"' in html
    assert 'data-panel="generation-history"' in html
    assert html.index('data-tab="generation-history"') > html.index('data-tab="generation"')
    assert html.index('data-tab="generation-history"') < html.index('data-tab="prompts"')
    assert 'id="generationHistoryTaskTypeSelect"' in html
    assert 'id="generationHistorySortSelect"' in html
    assert 'id="generationHistoryRows"' in html
    assert 'id="generationHistoryPagination"' in html
    assert "用户 ID" in html
    assert "用户昵称" in html
    assert "输入地址" in html
    assert "输出地址" in html
    assert "/api/generation-history" in app_js
    assert "role_group: roleGroup" in app_js
    assert 'data-role-group="${roleGroup}"' in app_js
    assert 'asset.content_url || ""' in app_js
    assert "本地可用" in app_js
    assert "generationHistoryPage" in app_js
    assert 'value="type_count_desc"' in html
    assert 'class="generation-history-prompt-text"' in app_js
    assert 'escapeHtml(row.user_id ?? "-")' in app_js
    assert "-webkit-line-clamp: 4" in styles
    assert "提示词向量化" in html
    assert 'data-tab="prompt-tokens"' in html
    assert 'data-panel="prompt-tokens"' in html
    assert 'data-tab="prompt-decomposition"' in html
    assert 'data-panel="prompt-decomposition"' in html
    assert 'id="promptDecompositionFacetGrid"' in html
    assert 'id="promptDecompositionRows"' in html
    assert 'id="promptDecompositionSavedRows"' in html
    assert 'id="promptDecompositionDrawer"' in html
    assert 'id="promptTokenRows"' in html
    assert 'id="promptTokenTaskTypeSelect"' in html
    assert 'id="promptTokenModelSelect"' in html
    assert 'id="promptTokenMinPromptCountInput"' in html
    assert 'id="promptTokenCustomTermRows"' in html
    assert 'id="promptTokenCustomTermSearchInput"' in html
    assert 'id="promptTokenCustomTermCategoryTabs"' in html
    assert 'id="promptTokenCustomTermSubcategoryTabs"' in html
    assert 'id="promptTokenCustomTermPagination"' in html
    assert "<th>分类</th>" not in html.split('id="promptTokenCustomTermRows"', 1)[0].rsplit("<table", 1)[-1]
    assert "<th>子分类</th>" not in html.split('id="promptTokenCustomTermRows"', 1)[0].rsplit("<table", 1)[-1]
    assert 'id="promptTokenCustomTermLoadButton"' not in html
    assert 'id="promptTokenCustomTermAddButton"' in html
    assert 'id="promptTokenCustomTermSaveButton"' in html
    assert 'id="promptTokenCustomTermRebuildButton"' in html
    assert 'id="promptTokenRuleSeedOverwriteButton"' in html
    assert 'id="promptTokenRuleSeedStatus"' in html
    assert 'id="promptTokenAliasRows"' in html
    assert 'id="promptTokenAliasSearchInput"' in html
    assert 'id="promptTokenAliasCategoryTabs"' in html
    assert 'id="promptTokenAliasLoadButton"' not in html
    assert 'id="promptTokenAliasPagination"' in html
    assert 'id="promptTokenAliasAddButton"' in html
    assert 'id="promptTokenAliasSaveButton"' in html
    assert 'id="promptTokenAliasRebuildButton"' in html
    assert 'textarea data-field="aliases_text" data-autoresize="true"' in app_js
    assert "resizePromptTokenAliasTextareas" in app_js
    assert "PROMPT_TOKEN_RULE_PAGE_SIZE = 25" in app_js
    assert "filteredPromptTokenAliasRows" in app_js
    assert 'id="promptTokenDeletionRows"' in html
    assert 'id="promptTokenDeletionPagination"' in html
    assert 'id="promptTokenDeletionLoadButton"' not in html
    assert 'id="promptTokenDrawer"' in html
    assert 'id="promptTokenPagination"' in html
    assert 'id="promptTokenPromptPagination"' in html
    assert 'id="promptTokenPrevButton"' not in html
    assert 'id="promptTokenNextButton"' not in html
    assert 'id="promptTokenPromptPrevButton"' not in html
    assert 'id="promptTokenPromptNextButton"' not in html
    assert "/api/prompt-tokens" in app_js
    assert "/api/prompt-token-prompts" in app_js
    assert "/api/prompt-token-custom-terms" in app_js
    assert "/api/prompt-token-custom-terms/rebuild" in app_js
    assert "/api/prompt-token-aliases" in app_js
    assert "/api/prompt-token-aliases/rebuild" in app_js
    assert "/api/prompt-token-rules/overwrite-generated" in app_js
    assert "/api/prompt-token-deletions" in app_js
    assert "/api/prompt-token-deletions/restore" in app_js
    assert "/api/prompt-decomposition" in app_js
    assert "/api/prompt-decomposition/saved" in app_js
    load_prompt_tokens_body = app_js.split("async function loadPromptTokens() {", 1)[1].split(
        "\nasync function loadPromptTokenDeletions", 1
    )[0]
    assert "/api/prompt-token-custom-terms" not in load_prompt_tokens_body
    assert "/api/prompt-token-aliases" not in load_prompt_tokens_body
    assert "/api/prompt-token-deletions" not in load_prompt_tokens_body
    assert "min_prompt_count" in app_js
    assert "schedulePromptTokenAliasPoll" in app_js
    assert "renderPageControl" in app_js
    assert "function promptTokenTotalPages" in app_js
    assert "async function reloadPromptTokensPreservingPage" in app_js
    assert "function ensurePromptTokenRuleTablesLoaded" in app_js
    assert "renderPromptTokenRuleCategoryTabs" in app_js
    assert "renderPromptTokenRuleSubcategoryTabs" in app_js
    assert "promptTokenCustomTermSubcategoryFilter" in app_js
    assert "renderPromptDecompositionFacets" in app_js
    assert "renderPromptDecompositionDrawer" in app_js
    assert "savePromptDecompositionTemplate" in app_js
    delete_token_body = app_js.split("async function deletePromptToken(token) {", 1)[1].split(
        "\nasync function restorePromptToken", 1
    )[0]
    restore_token_body = app_js.split("async function restorePromptToken(token) {", 1)[1].split(
        "\nfunction getPromptParams", 1
    )[0]
    assert "state.promptTokenPage = 1" not in delete_token_body
    assert "state.promptTokenPage = 1" not in restore_token_body
    assert "await reloadPromptTokensPreservingPage()" in delete_token_body
    assert "await reloadPromptTokensPreservingPage()" in restore_token_body
    assert "promptVectorTokenDistribution" not in html
    assert "promptVectorTokenDistribution" not in app_js
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
    assert 'id="templateTaskTypeSelect"' in html
    assert 'id="templateModelSelect"' in html
    assert 'id="templateMinPromptsInput"' in html
    assert 'id="templateSimilaritySelect"' in html
    assert 'id="templateReviewStatusSelect"' in html
    assert '<option value="low_quality">低质量</option>' in html
    assert 'id="templateCandidateRows"' in html
    assert 'id="templateCandidatePagination"' in html
    assert 'id="templateReviewMarksButton"' in html
    assert 'id="templateReviewMarksDrawer"' in html
    assert 'id="templateReviewMarksRows"' in html
    assert 'id="templateReviewMarksCopyAllButton"' in html
    assert 'id="templateReviewMarksExportButton"' in html
    assert 'id="templateReviewMarksSearchInput"' in html
    assert 'id="templateReviewMarksProcessedSelect"' in html
    assert 'id="templateReviewMarksPagination"' in html
    assert 'id="templateCandidateDrawer"' in html
    assert 'id="templateCandidatePromptRows"' in html
    assert 'id="templateCandidatePromptPagination"' in html
    assert "<th>暂存</th>" in html
    assert "/api/prompt-template-candidates" in app_js
    assert "/api/prompt-template-candidates/review-marks" in app_js
    assert "/api/prompt-template-candidates/review-marks/processed" in app_js
    assert "/api/prompt-template-candidates/template-review-marks" in app_js
    assert "/api/prompt-template-candidates/refresh" in app_js
    assert "getTemplateCandidateParams" in app_js
    assert "loadTemplateReviewMarks" in app_js
    assert "renderTemplateReviewMarksDrawer" in app_js
    assert "copyTemplateReviewMarksAll" in app_js
    assert "exportTemplateReviewMarksCsv" in app_js
    assert "toggleTemplateReviewMarkProcessed" in app_js
    assert "processed_status" in app_js
    assert "data-template-review-processed" in app_js
    assert "data-template-low-quality-template" in app_js
    assert "toggleTemplateCandidateLowQuality" in app_js
    assert "renderTemplateReviewBadges" in app_js
    assert "低质量" in app_js
    assert '.template-review-check input[type="checkbox"]' in styles
    assert '.template-low-quality-check input[type="checkbox"]' in styles
    assert ".template-candidate-actions" in styles
    assert ".template-review-mark-actions button" in styles
    assert "renderTemplateSimilarityBadge" in app_js
    assert "toggleTemplateCandidateReviewMark" in app_js
    assert "getTemplatePromptParams" not in app_js
    assert 'fetchJson("/api/prompts", getTemplatePromptParams' not in app_js
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
