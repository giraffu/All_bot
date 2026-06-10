from __future__ import annotations

import argparse
import json
from pathlib import Path

from .canary import ComfyCanary
from .config_loader import load_controller_config
from .image_repo import LocalRegistry
from .model_importer import ModelImportPlanner, plan_to_json
from .model_repo import ModelRegistry
from .planner import GpuPoolPlanner
from .providers.lan_ssh import LanSshProvider


def _print_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_inventory(args) -> int:
    config = load_controller_config(args.config_root)
    provider = LanSshProvider()
    payload = provider.inventory_from_config(config.nodes)
    _print_json(payload)
    return 0


def _cmd_plan(args) -> int:
    config = load_controller_config(args.config_root)
    _print_json(GpuPoolPlanner(config).to_jsonable())
    return 0


def _cmd_canary(args) -> int:
    config = load_controller_config(args.config_root)
    assignment = config.assignments[args.assignment]
    node = config.nodes[assignment.node_id]
    comfy = next(item for item in node.comfy if item.id == assignment.comfy_id)
    profile = config.profiles[assignment.profile_id]
    result = ComfyCanary(timeout_seconds=args.timeout).run(comfy=comfy, profile=profile)
    _print_json({"ok": result.ok, "checks": result.checks, "details": result.details})
    return 0 if result.ok else 2


def _cmd_model_import(args) -> int:
    registry = ModelRegistry(args.repo_root)
    manifest = registry.import_file(
        bundle=args.bundle,
        version=args.version,
        source_path=args.source,
        relative_path=args.relative_path,
        source_node=args.source_node,
        profiles=args.profile,
    )
    _print_json(manifest)
    return 0


def _cmd_workflow_model_check(args) -> int:
    config = load_controller_config(args.config_root)
    planner = ModelImportPlanner(
        config,
        registry=ModelRegistry(args.repo_root),
        workflow_dir=args.workflow_dir,
    )
    payload = planner.workflow_model_check()
    _print_json(payload)
    return 0 if payload["missing_count"] == 0 else 2


def _cmd_model_import_plan(args) -> int:
    config = load_controller_config(args.config_root)
    planner = ModelImportPlanner(
        config,
        registry=ModelRegistry(args.repo_root),
        workflow_dir=args.workflow_dir,
    )
    plans = planner.build_import_plans(
        bundle_ids=args.bundle,
        include_sha256=not args.no_sha256,
    )
    payload = {"plans": [plan_to_json(plan) for plan in plans]}
    payload["missing_count"] = sum(plan["missing_count"] for plan in payload["plans"])
    _print_json(payload)
    return 0 if payload["missing_count"] == 0 else 2


def _cmd_model_import_execute(args) -> int:
    config = load_controller_config(args.config_root)
    planner = ModelImportPlanner(
        config,
        registry=ModelRegistry(args.repo_root),
        workflow_dir=args.workflow_dir,
    )
    _print_json(planner.execute_import(bundle_ids=args.bundle))
    return 0


def _cmd_model_rsync_plan(args) -> int:
    registry = ModelRegistry(args.repo_root)
    _print_json(
        {
            "commands": registry.render_rsync_plan(
                bundle=args.bundle,
                version=args.version,
                target_host=args.target_host,
                target_model_dir=args.target_model_dir,
            )
        }
    )
    return 0


def _cmd_image_plan(args) -> int:
    registry = LocalRegistry(host=args.host, port=args.port)
    _print_json(
        {
            "endpoint": registry.endpoint,
            "commands": registry.render_publish_plan(
                source_image=args.source_image,
                repository=args.repository,
                tag=args.tag,
            ),
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AllBot GPU pool controller v1")
    parser.add_argument("--config-root", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("inventory").set_defaults(func=_cmd_inventory)
    subparsers.add_parser("plan").set_defaults(func=_cmd_plan)

    canary = subparsers.add_parser("canary")
    canary.add_argument("--assignment", required=True)
    canary.add_argument("--timeout", type=float, default=8.0)
    canary.set_defaults(func=_cmd_canary)

    model_import = subparsers.add_parser("model-import")
    model_import.add_argument("--repo-root", type=Path, default=ModelRegistry().root)
    model_import.add_argument("--bundle", required=True)
    model_import.add_argument("--version", required=True)
    model_import.add_argument("--source", type=Path, required=True)
    model_import.add_argument("--relative-path", required=True)
    model_import.add_argument("--source-node", required=True)
    model_import.add_argument("--profile", action="append", default=[])
    model_import.set_defaults(func=_cmd_model_import)

    workflow_model_check = subparsers.add_parser("workflow-model-check")
    workflow_model_check.add_argument("--repo-root", type=Path, default=ModelRegistry().root)
    workflow_model_check.add_argument("--workflow-dir", type=Path, default=Path("workers/comfy_agent/workflows"))
    workflow_model_check.set_defaults(func=_cmd_workflow_model_check)

    model_import_plan = subparsers.add_parser("model-import-plan")
    model_import_plan.add_argument("--repo-root", type=Path, default=ModelRegistry().root)
    model_import_plan.add_argument("--workflow-dir", type=Path, default=Path("workers/comfy_agent/workflows"))
    model_import_plan.add_argument("--bundle", action="append", default=None)
    model_import_plan.add_argument("--no-sha256", action="store_true")
    model_import_plan.set_defaults(func=_cmd_model_import_plan)

    model_import_execute = subparsers.add_parser("model-import-execute")
    model_import_execute.add_argument("--repo-root", type=Path, default=ModelRegistry().root)
    model_import_execute.add_argument("--workflow-dir", type=Path, default=Path("workers/comfy_agent/workflows"))
    model_import_execute.add_argument("--bundle", action="append", default=None)
    model_import_execute.set_defaults(func=_cmd_model_import_execute)

    rsync_plan = subparsers.add_parser("model-rsync-plan")
    rsync_plan.add_argument("--repo-root", type=Path, default=ModelRegistry().root)
    rsync_plan.add_argument("--bundle", required=True)
    rsync_plan.add_argument("--version", required=True)
    rsync_plan.add_argument("--target-host", required=True)
    rsync_plan.add_argument("--target-model-dir", required=True)
    rsync_plan.set_defaults(func=_cmd_model_rsync_plan)

    image_plan = subparsers.add_parser("image-plan")
    image_plan.add_argument("--host", default="192.168.1.115")
    image_plan.add_argument("--port", type=int, default=5000)
    image_plan.add_argument("--source-image", required=True)
    image_plan.add_argument("--repository", required=True)
    image_plan.add_argument("--tag", required=True)
    image_plan.set_defaults(func=_cmd_image_plan)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
