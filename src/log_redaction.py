"""Process-wide logging guards for credential-bearing request URLs."""

from __future__ import annotations

import logging
import re
from typing import Any


_TELEGRAM_BOT_TOKEN_URL_PATTERN = re.compile(
    r"/bot\d+:[^/\s\"'?#]+",
    flags=re.IGNORECASE,
)


def redact_log_value(value: Any) -> Any:
    rendered = value if isinstance(value, str) else str(value)
    if "/bot" not in rendered.lower():
        return value
    redacted = _TELEGRAM_BOT_TOKEN_URL_PATTERN.sub("/bot<redacted>", rendered)
    return redacted if redacted != rendered else value


def _redact_record(record: logging.LogRecord) -> None:
    record.msg = redact_log_value(record.msg)
    if isinstance(record.args, tuple):
        record.args = tuple(redact_log_value(value) for value in record.args)
    elif isinstance(record.args, dict):
        record.args = {
            key: redact_log_value(value) for key, value in record.args.items()
        }


def install_log_redaction() -> None:
    """Install an idempotent guard before any handler formats a log record."""

    current_factory = logging.getLogRecordFactory()
    if not getattr(current_factory, "_allbot_log_redaction_guard", False):

        def guarded_record_factory(*args, **kwargs):
            record = current_factory(*args, **kwargs)
            _redact_record(record)
            return record

        guarded_record_factory._allbot_log_redaction_guard = True
        logging.setLogRecordFactory(guarded_record_factory)

    # Full request URLs are both noisy and credential-bearing for Telegram.
    for logger_name in ("httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
