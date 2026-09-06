from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_SRC = ROOT / "dashboard" / "frontend" / "src"

# Existing migration queue. New SFCs cannot join this list; each migrated component is
# removed here in the same change, making the TypeScript debt monotonically smaller.
LEGACY_JAVASCRIPT_SFCS = {
    "components/ActiveTasksTable.vue",
    "components/AvgDailyCreditDistributionChart.vue",
    "components/AvgDailyDistributionChart.vue",
    "components/CreditDistributionChart.vue",
    "components/CreditHoldingDistributionChart.vue",
    "components/CumulativeHourlyChart.vue",
    "components/DashboardHeaderBar.vue",
    "components/DashboardSidebar.vue",
    "components/GalleryCommentsTable.vue",
    "components/GalleryTable.vue",
    "components/GenerationDistributionChart.vue",
    "components/HistoryModal.vue",
    "components/HistoryTable.vue",
    "components/HomeDashboard.vue",
    "components/LineChart.vue",
    "components/LogTable.vue",
    "components/RechargeSystem.vue",
    "components/ReferralTable.vue",
    "components/StatsCards.vue",
    "components/TemplateManager.vue",
    "components/UserFavoritesModal.vue",
    "components/UserGroupDistributionChart.vue",
    "components/UserTable.vue",
    "components/UserTableDialogs.vue",
    "components/UserTableRowActions.vue",
    "components/UserTableToolbar.vue",
    "components/WorkerHistoryTable.vue",
}


def test_dashboard_new_sfc_requires_script_setup_typescript():
    actual = {
        str(path.relative_to(DASHBOARD_SRC))
        for path in DASHBOARD_SRC.rglob("*.vue")
        if '<script setup lang="ts">' not in path.read_text(encoding="utf-8")
    }

    assert actual == LEGACY_JAVASCRIPT_SFCS
