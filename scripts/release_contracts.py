"""Stable contracts shared by the release CLI and target adapters.

This module deliberately contains no environment discovery or mutation.  It is
safe for tests and future orchestration modules to import without importing the
9k-line compatibility facade in :mod:`scripts.release`.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence


ReleaseCallable = Callable[..., Any]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class ReleaseCommand:
    """Immutable process input before argparse projects it into a namespace."""

    argv: tuple[str, ...]

    @classmethod
    def from_argv(cls, argv: Sequence[str]) -> "ReleaseCommand":
        return cls(tuple(argv))


@dataclass(frozen=True, slots=True)
class ReleasePlan:
    """Immutable public snapshot of a computed release plan."""

    services: tuple[str, ...]
    level: str
    requires_db_upgrade: bool
    blockers: tuple[str, ...]
    unknown_paths: tuple[str, ...]
    matched_rules: tuple[str, ...]
    manifest: Mapping[str, Any]
    previous_sha: str

    @classmethod
    def from_legacy(
        cls,
        impact: Any,
        manifest: Mapping[str, Any],
        previous_sha: str,
    ) -> "ReleasePlan":
        return cls(
            services=tuple(sorted(impact.services)),
            level=str(impact.level),
            requires_db_upgrade=bool(impact.requires_db_upgrade),
            blockers=tuple(sorted(impact.blockers)),
            unknown_paths=tuple(impact.unknown_paths),
            matched_rules=tuple(impact.matched_rules),
            manifest=_freeze(manifest),
            previous_sha=previous_sha,
        )


@dataclass(frozen=True, slots=True)
class ReleaseDependencies:
    """Explicit I/O boundary used by planning and target execution.

    The broad callable signatures are intentional at this compatibility stage:
    existing adapters have mature but different call shapes.  Splitting these
    fields into narrower target protocols can now happen without changing the
    CLI or forcing tests to patch private module globals.
    """

    resolve_manifest_path: ReleaseCallable
    read_json: ReleaseCallable
    resolve_previous_sha: ReleaseCallable
    load_release_index: ReleaseCallable
    load_v2_track: ReleaseCallable
    run: ReleaseCallable
    remote_shell: ReleaseCallable
    sleep: ReleaseCallable
    current_pages_deployment_id: ReleaseCallable
