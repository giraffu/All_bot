from pathlib import Path


def test_observer_schema_is_isolated_and_idempotent():
    sql = (Path(__file__).parents[2] / "observer_bot" / "schema.sql").read_text()

    assert "CREATE TABLE IF NOT EXISTS observer_group_messages" in sql
    assert "CREATE TABLE IF NOT EXISTS observer_alert_states" in sql
    assert "CREATE TABLE IF NOT EXISTS observer_report_runs" in sql
    assert "CREATE TABLE IF NOT EXISTS observer_runtime_settings" in sql
    assert "CREATE TABLE IF NOT EXISTS observer_admin_recipients" in sql
    assert "CREATE TABLE IF NOT EXISTS observer_authorized_chats" in sql
    assert "CREATE TABLE IF NOT EXISTS observer_notification_logs" in sql
    assert "support_tickets" not in sql
    assert "history" not in sql
