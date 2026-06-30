from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "local_analytics_platform" / "static"


def test_core_tabs_use_echarts_mount_points_instead_of_spark_bars():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/static/vendor/echarts.min.js" in html
    assert "spark-bars" not in html
    assert "hourly-bars" not in html
    assert "renderChart(id, option)" in app_js
    assert "buildLineBarOption" in app_js
    assert "buildDonutOption" in app_js
    assert "buildStackedBarOption" in app_js
    assert 'data-tab="prompt-graph"' in html
    assert 'id="promptGraphChart"' in html
    assert "renderPromptGraph" in app_js
    assert '<select id="promptGraphTaskTypeSelect"></select>' in html
    assert 'value="centroid_bridge"' not in html
    assert "自然场景 / 微簇" in app_js
    assert "不跨任务连接" in app_js

    for mount_id in [
        "userTrendChart",
        "creditFlowTrendChart",
        "financeTrendChart",
        "financeHourlyChart",
        "generationTrendChart",
        "generationCompareChart",
        "promptGraphChart",
    ]:
        assert f'id="{mount_id}"' in html
