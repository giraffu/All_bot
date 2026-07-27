"""Pure request-policy projection for immutable release planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


class PlanValidationError(ValueError):
    """A release request violates a planning policy before any I/O."""


@dataclass(frozen=True, slots=True)
class V2PlanRequest:
    requested_modules: frozenset[str]
    requested_services: frozenset[str]
    test_data_repair: bool
    dashboard_fast_track: bool
    control_plane_repair_fast_track: bool


def validate_v2_plan_request(
    args: Any,
    *,
    split_services: Callable[[Iterable[str]], set[str]],
) -> V2PlanRequest:
    """Validate mutually exclusive schema-v2 planning modes without I/O."""

    requested_modules = split_services(args.modules)
    requested_services = split_services(args.services)
    test_data_repair = bool(getattr(args, "repair_test_data_services", False))
    dashboard_fast_track = bool(getattr(args, "dashboard_fast_track", False))
    repair_fast_track = bool(
        getattr(args, "control_plane_repair_fast_track", False)
    )

    if test_data_repair:
        if args.env != "test" or args.track != "control-plane":
            raise PlanValidationError(
                "test data service repair is only available for the test control-plane"
            )
        if args.command not in {"plan", "preflight", "deploy"}:
            raise PlanValidationError(
                "test data service repair is only available for plan, preflight, or deploy"
            )
        if requested_modules or requested_services != {"postgres", "redis"}:
            raise PlanValidationError(
                "test data service repair requires exactly postgres and redis services"
            )

    if dashboard_fast_track:
        if args.env != "prod" or args.track != "control-plane":
            raise PlanValidationError(
                "dashboard fast-track is only available for the production control-plane"
            )
        if args.command not in {"plan", "preflight", "deploy", "rollback"}:
            raise PlanValidationError(
                "dashboard fast-track is only available for plan, preflight, deploy, or rollback"
            )
        if requested_modules or requested_services or args.from_sha:
            raise PlanValidationError(
                "dashboard fast-track does not accept module, service, or from-SHA overrides"
            )

    if repair_fast_track:
        if args.env != "prod" or args.track != "control-plane":
            raise PlanValidationError(
                "control-plane repair fast-track is only available for the production control-plane"
            )
        if args.command not in {"plan", "preflight", "deploy"}:
            raise PlanValidationError(
                "control-plane repair fast-track is only available for plan, preflight, or deploy"
            )
        if (
            requested_modules
            or requested_services
            or args.from_sha
            or dashboard_fast_track
        ):
            raise PlanValidationError(
                "control-plane repair fast-track does not accept module, service, from-SHA, or other fast-track overrides"
            )

    if requested_services and args.track != "control-plane":
        raise PlanValidationError(
            "--services is only an alias for control-plane modules"
        )

    return V2PlanRequest(
        requested_modules=frozenset(requested_modules),
        requested_services=frozenset(requested_services),
        test_data_repair=test_data_repair,
        dashboard_fast_track=dashboard_fast_track,
        control_plane_repair_fast_track=repair_fast_track,
    )
