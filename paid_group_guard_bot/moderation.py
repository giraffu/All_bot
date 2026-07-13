from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse


DEFAULT_MODERATION_CONFIG_PATH = "/app/runtime/paid-group-guard/config.json"
DEFAULT_MODERATION_LOG_PATH = "/app/logs/paid_group_moderation.jsonl"
TEXT_SNIPPET_LIMIT = 160
MAX_LIST_ITEMS = 1000

LINK_PATTERN = re.compile(r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/)[^\s<>()\"']+")


@dataclass(frozen=True)
class PaidGroupModerationConfig:
    enabled: bool = True
    dry_run: bool = False
    block_links: bool = True
    allowed_domains: tuple[str, ...] = field(default_factory=tuple)
    forbidden_words: tuple[str, ...] = field(default_factory=tuple)
    exempt_user_ids: frozenset[int] = field(default_factory=frozenset)


@dataclass(frozen=True)
class PaidGroupModerationDecision:
    should_delete: bool
    reason: str | None = None
    matched_value: str | None = None


@dataclass(frozen=True)
class PaidGroupModerationLogEvent:
    timestamp: str
    chat_id: int
    message_id: int
    user_id: int
    username: str | None
    full_name: str | None
    reason: str
    matched_value: str | None
    text_snippet: str
    action: str
    error: str | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _dedupe_strings(values) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set)):
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        normalized.append(item)
        seen.add(key)
        if len(normalized) >= MAX_LIST_ITEMS:
            break
    return tuple(normalized)


def _dedupe_ints(values) -> frozenset[int]:
    if not isinstance(values, (list, tuple, set)):
        return frozenset()

    normalized: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item <= 0 or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
        if len(normalized) >= MAX_LIST_ITEMS:
            break
    return frozenset(normalized)


def normalize_domain(value: str | None) -> str | None:
    raw = str(value or "").strip().casefold()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    domain = parsed.netloc or parsed.path.split("/", 1)[0]
    domain = domain.rsplit("@", 1)[-1].split(":", 1)[0].strip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or None


def _normalize_domains(values) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in _dedupe_strings(values):
        domain = normalize_domain(value)
        if domain is None or domain in seen:
            continue
        normalized.append(domain)
        seen.add(domain)
    return tuple(normalized)


def default_moderation_config() -> PaidGroupModerationConfig:
    return PaidGroupModerationConfig(
        enabled=_env_bool("PAID_GROUP_MODERATION_ENABLED", True),
        dry_run=_env_bool("PAID_GROUP_MODERATION_DRY_RUN", False),
        block_links=_env_bool("PAID_GROUP_BLOCK_LINKS", True),
    )


def normalize_moderation_config(data: dict | None) -> PaidGroupModerationConfig:
    defaults = default_moderation_config()
    if not isinstance(data, dict):
        return defaults

    return PaidGroupModerationConfig(
        enabled=_coerce_bool(data.get("enabled"), defaults.enabled),
        dry_run=_coerce_bool(data.get("dry_run"), defaults.dry_run),
        block_links=_coerce_bool(data.get("block_links"), defaults.block_links),
        allowed_domains=_normalize_domains(data.get("allowed_domains", [])),
        forbidden_words=_dedupe_strings(data.get("forbidden_words", [])),
        exempt_user_ids=_dedupe_ints(data.get("exempt_user_ids", [])),
    )


def moderation_config_to_dict(config: PaidGroupModerationConfig) -> dict:
    payload = asdict(config)
    payload["allowed_domains"] = list(config.allowed_domains)
    payload["forbidden_words"] = list(config.forbidden_words)
    payload["exempt_user_ids"] = sorted(config.exempt_user_ids)
    return payload


def load_moderation_config(path: str | Path) -> PaidGroupModerationConfig:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return default_moderation_config()
    except (OSError, json.JSONDecodeError):
        return default_moderation_config()
    return normalize_moderation_config(payload)


def write_moderation_config(
    path: str | Path, config: PaidGroupModerationConfig
) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = moderation_config_to_dict(config)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(config_path.parent),
        prefix=f".{config_path.name}.",
        delete=False,
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, config_path)


class PaidGroupModerationConfigProvider:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._cached_mtime: float | None = None
        self._cached_config: PaidGroupModerationConfig | None = None

    def load(self) -> PaidGroupModerationConfig:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = None

        if self._cached_config is not None and self._cached_mtime == mtime:
            return self._cached_config

        config = load_moderation_config(self.path)
        self._cached_config = config
        self._cached_mtime = mtime
        return config


def extract_url_candidates(text: str | None) -> list[str]:
    if not text:
        return []
    return [match.group(0).rstrip(".,;:!?)]}") for match in LINK_PATTERN.finditer(text)]


def is_allowed_link(candidate: str, allowed_domains: tuple[str, ...]) -> bool:
    if not allowed_domains:
        return False
    domain = normalize_domain(candidate)
    if domain is None:
        return False
    return any(
        domain == allowed or domain.endswith(f".{allowed}")
        for allowed in allowed_domains
    )


def evaluate_moderation_decision(
    *,
    config: PaidGroupModerationConfig,
    text: str,
    link_candidates: list[str] | None = None,
) -> PaidGroupModerationDecision:
    if not config.enabled:
        return PaidGroupModerationDecision(should_delete=False)

    candidates = list(link_candidates or [])
    candidates.extend(extract_url_candidates(text))
    if config.block_links:
        for candidate in candidates:
            if not candidate:
                continue
            if is_allowed_link(candidate, config.allowed_domains):
                continue
            return PaidGroupModerationDecision(
                should_delete=True,
                reason="link",
                matched_value=candidate,
            )

    folded_text = text.casefold()
    for word in config.forbidden_words:
        if word and word.casefold() in folded_text:
            return PaidGroupModerationDecision(
                should_delete=True,
                reason="forbidden_word",
                matched_value=word,
            )

    return PaidGroupModerationDecision(should_delete=False)


def build_text_snippet(text: str | None) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= TEXT_SNIPPET_LIMIT:
        return normalized
    return normalized[:TEXT_SNIPPET_LIMIT]


def append_moderation_log(path: str | Path, event: PaidGroupModerationLogEvent) -> None:
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True))
        fh.write("\n")


def now_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
