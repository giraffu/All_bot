import logging

from src.log_redaction import install_log_redaction


def test_global_log_redaction_hides_telegram_bot_tokens(caplog):
    install_log_redaction()
    secret = "123456:SUPER_SECRET_TOKEN"

    with caplog.at_level(logging.WARNING, logger="allbot.redaction.test"):
        logging.getLogger("allbot.redaction.test").warning(
            "request failed url=%s",
            f"https://api.telegram.org/bot{secret}/getUpdates",
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in rendered
    assert "/bot<redacted>/getUpdates" in rendered


def test_global_log_redaction_hides_tokens_in_mapping_args(caplog):
    install_log_redaction()
    secret = "654321:ANOTHER_SECRET"

    with caplog.at_level(logging.ERROR, logger="allbot.redaction.mapping"):
        logging.getLogger("allbot.redaction.mapping").error(
            "request failed %(url)s",
            {"url": f"https://telegram.invalid/bot{secret}/sendMessage"},
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in rendered
    assert "/bot<redacted>/sendMessage" in rendered
