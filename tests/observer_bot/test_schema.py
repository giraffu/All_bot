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
    assert "queue_total_pending_threshold INTEGER NOT NULL DEFAULT 20" in sql
    assert "queue_type_pending_threshold INTEGER NOT NULL DEFAULT 10" in sql
    assert "ADD COLUMN IF NOT EXISTS queue_total_pending_threshold" in sql
    assert "ADD COLUMN IF NOT EXISTS queue_type_pending_threshold" in sql
    assert sql.count("BETWEEN 1 AND 100000") == 4
    assert "support_tickets" not in sql
    assert "history" not in sql
