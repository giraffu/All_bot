from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from .canary import ComfyCanary
from .config_loader import load_controller_config
from .image_repo import LocalRegistry
from .model_importer import ModelImportPlanner, plan_to_json
from .model_repo import ModelRegistry
from .planner import GpuPoolPlanner
from .providers.lan_ssh import LanSshProvider
from .providers.runpod import RunPodProvider, RunPodSettings
from .runpod_canary import (
    RunPodCanaryRunner,
    load_env_file,
    options_from_args_env as canary_options_from_args_env,
)
from .runpod_prod_worker import (
    PROD_WORKER_DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    RunPodProdWorkerRunner,
    apply_prod_worker_selection_to_env,
    load_env_file_for_prod_worker,
    options_from_args_env as prod_worker_options_from_args_env,
)
from .runpod_split_video_canary import (
    DEFAULT_SPLIT_VIDEO_PROMPT,
    DEFAULT_SPLIT_VIDEO_RESULTS_DIR,
    RunPodSplitVideoCanaryRunner,
)
from .runpod_video_manifests import (
    create_model_r2_client_from_env,
    prepare_split_video_manifests,
)
from .runpod_workers import RunPodWorkersScaler, RunPodWorkersScaleOptions
from .runtime import RuntimePlanner, RuntimeRenderOverrides, runtime_plan_to_jsonable


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


def _cmd_runtime_plan(args) -> int:
    config = load_controller_config(args.config_root)
    planner = RuntimePlanner(config)
    overrides = _runtime_overrides_from_args(args)
    if not args.assignment and overrides.has_any:
        raise ValueError("runtime-plan overrides require --assignment")
    if args.assignment:
        payload = runtime_plan_to_jsonable(
            planner.build_plan(
                args.assignment,
                target_profile_id=args.profile,
                overrides=overrides,
            )
        )
    else:
        payload = [runtime_plan_to_jsonable(item) for item in planner.build_all_plans()]
    _print_json(payload)
    return 0


def _cmd_runtime_render(args) -> int:
    config = load_controller_config(args.config_root)
    print(
        RuntimePlanner(config).render_compose(
            args.assignment,
            target_profile_id=args.profile,
            overrides=_runtime_overrides_from_args(args),
        ),
        end="",
    )
    return 0


def _runtime_overrides_from_args(args) -> RuntimeRenderOverrides:
    return RuntimeRenderOverrides(
        host_port=getattr(args, "host_port", None),
        container_name=getattr(args, "container_name", None),
        api_url=getattr(args, "api_url", None),
        ws_url=getattr(args, "ws_url", None),
        runtime_shape=getattr(args, "runtime_shape", None),
        agent_id=getattr(args, "agent_id", None),
        central_url=getattr(args, "central_url", None),
        environment=getattr(args, "environment", None),
    )


def _cmd_runtime_apply(args) -> int:
    config = load_controller_config(args.config_root)
    payload = RuntimePlanner(config).build_dry_run_action(
        "runtime-apply",
        args.assignment,
        execute=args.execute,
    )
    _print_json(payload)
    return 2 if args.execute else 0


def _cmd_switch_profile(args) -> int:
    config = load_controller_config(args.config_root)
    payload = RuntimePlanner(config).build_dry_run_action(
        "switch-profile",
        args.assignment,
        target_profile_id=args.profile,
        execute=args.execute,
    )
    _print_json(payload)
    return 2 if args.execute else 0


def _cmd_rollback_profile(args) -> int:
    config = load_controller_config(args.config_root)
    payload = RuntimePlanner(config).build_rollback_plan(
        args.assignment,
        execute=args.execute,
    )
    _print_json(payload)
    return 2 if args.execute else 0


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


def _runpod_provider_from_args(_args) -> RunPodProvider:
    return RunPodProvider(RunPodSettings.from_env())


def _cmd_runpod_validate_key(args) -> int:
    payload = _runpod_provider_from_args(args).validate_key()
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_list_pods(args) -> int:
    payload = _runpod_provider_from_args(args).list_pods(
        managed_only=not args.all,
        desired_status=args.desired_status,
    )
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_get_pod(args) -> int:
    payload = _runpod_provider_from_args(args).get_pod(pod_id=args.pod_id)
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_pod_readiness(args) -> int:
    payload = _runpod_provider_from_args(args).pod_readiness(pod_id=args.pod_id)
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_render_create(args) -> int:
    payload = _runpod_provider_from_args(args).render_create_pod_request(
        task_type=args.task_type,
        environment=args.env,
    )
    _print_json(payload)
    return 0


def _cmd_runpod_reconcile(args) -> int:
    provider = _runpod_provider_from_args(args)
    if args.from_file:
        pods = json.loads(args.from_file.read_text(encoding="utf-8"))
        if isinstance(pods, dict):
            pods = pods.get("pods", [])
        payload = provider.reconcile_managed_pods(pods=list(pods))
    else:
        payload = provider.reconcile_managed_pods()
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_create(args) -> int:
    payload = _runpod_provider_from_args(args).create_pod(
        task_type=args.task_type,
        environment=args.env,
        execute=args.execute,
    )
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_start(args) -> int:
    payload = _runpod_provider_from_args(args).start_pod(
        pod_id=args.pod_id,
        task_type=args.task_type,
        execute=args.execute,
    )
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_stop(args) -> int:
    payload = _runpod_provider_from_args(args).stop_pod(
        pod_id=args.pod_id,
        task_type=args.task_type,
        execute=args.execute,
    )
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_delete(args) -> int:
    payload = _runpod_provider_from_args(args).delete_pod(
        pod_id=args.pod_id,
        task_type=args.task_type,
        execute=args.execute,
    )
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_canary(args) -> int:
    env_file_info = load_env_file(args.env_file)
    provider = _runpod_provider_from_args(args)
    options = canary_options_from_args_env(args)
    payload = RunPodCanaryRunner(provider, options).run()
    payload["env_file"] = env_file_info
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_split_video_canary(args) -> int:
    env_file_info = load_env_file(args.env_file)
    provider = _runpod_provider_from_args(args)
    options = canary_options_from_args_env(args)
    options = replace(
        options,
        task_type="split_video_profiles",
        prompt=args.prompt or DEFAULT_SPLIT_VIDEO_PROMPT,
        download_results_dir=(
            options.download_results_dir or DEFAULT_SPLIT_VIDEO_RESULTS_DIR
        ),
    )
    payload = RunPodSplitVideoCanaryRunner(
        provider,
        options,
        profiles=tuple(args.profile or ()),
    ).run()
    payload["env_file"] = env_file_info
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_workers(args) -> int:
    env_file_info = load_env_file(getattr(args, "env_file", None))
    provider = _runpod_provider_from_args(args)
    options = RunPodWorkersScaleOptions(
        profile=args.profile,
        desired=args.desired,
        environment=args.env,
        execute=bool(getattr(args, "execute", False)),
    )
    scaler = RunPodWorkersScaler(provider, options)
    if args.workers_command == "render-scale":
        payload = scaler.render_scale()
    elif args.workers_command == "scale":
        payload = scaler.scale()
    else:  # pragma: no cover
        raise ValueError(f"unsupported runpod workers command: {args.workers_command}")
    payload["env_file"] = env_file_info
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_split_video_manifests(args) -> int:
    env_file_info = load_env_file(getattr(args, "env_file", None))
    bucket = args.bucket or RunPodSettings.from_env().model_bucket
    if not bucket:
        raise ValueError("RUNPOD_MODEL_BUCKET or --bucket is required")
    payload = prepare_split_video_manifests(
        client=create_model_r2_client_from_env(),
        bucket=bucket,
        source_key=args.source_key,
        execute=args.execute,
    )
    payload["env_file"] = env_file_info
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_runpod_prod_worker(args) -> int:
    env_files = []
    env_files.append(load_env_file(getattr(args, "runpod_env_file", None)))
    env_files.append(
        load_env_file_for_prod_worker(
            getattr(args, "prod_env_file", None),
            override=True,
            protect_existing_prefixes=("RUNPOD_",),
        )
    )
    selection = apply_prod_worker_selection_to_env(args)
    provider = _runpod_provider_from_args(args)
    options = prod_worker_options_from_args_env(args)
    payload = RunPodProdWorkerRunner(provider, options).run()
    payload["env_files"] = env_files
    payload["selection"] = selection
    _print_json(payload)
    return 0 if payload.get("ok") else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AllBot GPU pool controller v1")
    parser.add_argument("--config-root", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("inventory").set_defaults(func=_cmd_inventory)
    subparsers.add_parser("plan").set_defaults(func=_cmd_plan)

    runtime_plan = subparsers.add_parser("runtime-plan")
    runtime_plan.add_argument("--assignment", default=None)
    runtime_plan.add_argument("--profile", default=None)
    runtime_plan.add_argument("--host-port", type=int, default=None)
    runtime_plan.add_argument("--container-name", default=None)
    runtime_plan.add_argument("--api-url", default=None)
    runtime_plan.add_argument("--ws-url", default=None)
    runtime_plan.add_argument(
        "--runtime-shape",
        choices=("standard_comfy_runtime", "runpod_all_in_one"),
        default=None,
    )
    runtime_plan.add_argument("--agent-id", default=None)
    runtime_plan.add_argument("--central-url", default=None)
    runtime_plan.add_argument(
        "--environment",
        choices=("cloud-test", "cloud-prod"),
        default=None,
    )
    runtime_plan.set_defaults(func=_cmd_runtime_plan)

    runtime_render = subparsers.add_parser("runtime-render")
    runtime_render.add_argument("--assignment", required=True)
    runtime_render.add_argument("--profile", default=None)
    runtime_render.add_argument("--host-port", type=int, default=None)
    runtime_render.add_argument("--container-name", default=None)
    runtime_render.add_argument("--api-url", default=None)
    runtime_render.add_argument("--ws-url", default=None)
    runtime_render.add_argument(
        "--runtime-shape",
        choices=("standard_comfy_runtime", "runpod_all_in_one"),
        default=None,
    )
    runtime_render.add_argument("--agent-id", default=None)
    runtime_render.add_argument("--central-url", default=None)
    runtime_render.add_argument(
        "--environment",
        choices=("cloud-test", "cloud-prod"),
        default=None,
    )
    runtime_render.set_defaults(func=_cmd_runtime_render)

    runtime_apply = subparsers.add_parser("runtime-apply")
    runtime_apply.add_argument("--assignment", required=True)
    runtime_apply.add_argument("--execute", action="store_true")
    runtime_apply.set_defaults(func=_cmd_runtime_apply)

    switch_profile = subparsers.add_parser("switch-profile")
    switch_profile.add_argument("--assignment", required=True)
    switch_profile.add_argument("--profile", required=True)
    switch_profile.add_argument("--execute", action="store_true")
    switch_profile.set_defaults(func=_cmd_switch_profile)

    rollback_profile = subparsers.add_parser("rollback-profile")
    rollback_profile.add_argument("--assignment", required=True)
    rollback_profile.add_argument("--execute", action="store_true")
    rollback_profile.set_defaults(func=_cmd_rollback_profile)

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
    workflow_model_check.add_argument(
        "--repo-root", type=Path, default=ModelRegistry().root
    )
    workflow_model_check.add_argument(
        "--workflow-dir", type=Path, default=Path("workers/comfy_agent/workflows")
    )
    workflow_model_check.set_defaults(func=_cmd_workflow_model_check)

    model_import_plan = subparsers.add_parser("model-import-plan")
    model_import_plan.add_argument(
        "--repo-root", type=Path, default=ModelRegistry().root
    )
    model_import_plan.add_argument(
        "--workflow-dir", type=Path, default=Path("workers/comfy_agent/workflows")
    )
    model_import_plan.add_argument("--bundle", action="append", default=None)
    model_import_plan.add_argument("--no-sha256", action="store_true")
    model_import_plan.set_defaults(func=_cmd_model_import_plan)

    model_import_execute = subparsers.add_parser("model-import-execute")
    model_import_execute.add_argument(
        "--repo-root", type=Path, default=ModelRegistry().root
    )
    model_import_execute.add_argument(
        "--workflow-dir", type=Path, default=Path("workers/comfy_agent/workflows")
    )
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

    runpod = subparsers.add_parser("runpod")
    runpod_subparsers = runpod.add_subparsers(dest="runpod_command", required=True)

    runpod_validate = runpod_subparsers.add_parser("validate-key")
    runpod_validate.set_defaults(func=_cmd_runpod_validate_key)

    runpod_list = runpod_subparsers.add_parser("list-pods")
    runpod_list.add_argument(
        "--all", action="store_true", help="include unmanaged pods"
    )
    runpod_list.add_argument("--desired-status", default=None)
    runpod_list.set_defaults(func=_cmd_runpod_list_pods)

    runpod_get = runpod_subparsers.add_parser("get-pod")
    runpod_get.add_argument("--pod-id", required=True)
    runpod_get.set_defaults(func=_cmd_runpod_get_pod)

    runpod_readiness = runpod_subparsers.add_parser("pod-readiness")
    runpod_readiness.add_argument("--pod-id", required=True)
    runpod_readiness.set_defaults(func=_cmd_runpod_pod_readiness)

    runpod_render = runpod_subparsers.add_parser("render-create")
    runpod_render.add_argument("--task-type", default="img2img_lora")
    runpod_render.add_argument("--env", default="cloud-test")
    runpod_render.set_defaults(func=_cmd_runpod_render_create)

    runpod_reconcile = runpod_subparsers.add_parser("reconcile-managed-pods")
    runpod_reconcile.add_argument("--from-file", type=Path, default=None)
    runpod_reconcile.set_defaults(func=_cmd_runpod_reconcile)

    runpod_create = runpod_subparsers.add_parser("create-pod")
    runpod_create.add_argument("--task-type", default="img2img_lora")
    runpod_create.add_argument("--env", default="cloud-test")
    runpod_create.add_argument("--execute", action="store_true")
    runpod_create.set_defaults(func=_cmd_runpod_create)

    runpod_start = runpod_subparsers.add_parser("start-pod")
    runpod_start.add_argument("--pod-id", required=True)
    runpod_start.add_argument("--task-type", default="img2img_lora")
    runpod_start.add_argument("--execute", action="store_true")
    runpod_start.set_defaults(func=_cmd_runpod_start)

    runpod_stop = runpod_subparsers.add_parser("stop-pod")
    runpod_stop.add_argument("--pod-id", required=True)
    runpod_stop.add_argument("--task-type", default="img2img_lora")
    runpod_stop.add_argument("--execute", action="store_true")
    runpod_stop.set_defaults(func=_cmd_runpod_stop)

    runpod_delete = runpod_subparsers.add_parser("delete-pod")
    runpod_delete.add_argument("--pod-id", required=True)
    runpod_delete.add_argument("--task-type", default="img2img_lora")
    runpod_delete.add_argument("--execute", action="store_true")
    runpod_delete.set_defaults(func=_cmd_runpod_delete)

    runpod_canary = runpod_subparsers.add_parser(
        "canary",
        help="safe cloud-test RunPod canary: create pod, run three tasks, cleanup",
    )
    runpod_canary.add_argument("--task-type", default="img2img_lora")
    runpod_canary.add_argument("--env", default="cloud-test")
    runpod_canary.add_argument("--env-file", type=Path, default=Path(".env.cloud.test"))
    runpod_canary.add_argument(
        "--no-env-file", action="store_const", const=None, dest="env_file"
    )
    runpod_canary.add_argument("--execute", action="store_true")
    runpod_canary.add_argument(
        "--cleanup", action=argparse.BooleanOptionalAction, default=True
    )
    runpod_canary.add_argument(
        "--disable-workers",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    runpod_canary.add_argument("--worker-id", action="append", default=None)
    runpod_canary.add_argument("--web-api-url", default=None)
    runpod_canary.add_argument("--central-url", default=None)
    runpod_canary.add_argument("--web-user-id", type=int, default=None)
    runpod_canary.add_argument("--web-pwd-ver", type=int, default=None)
    runpod_canary.add_argument("--prompt", default=None)
    runpod_canary.add_argument("--negative-prompt", default=None)
    runpod_canary.add_argument("--input-object-key", default=None)
    runpod_canary.add_argument("--scail2-reference-object-key", default=None)
    runpod_canary.add_argument("--scail2-motion-video-object-key", default=None)
    runpod_canary.add_argument("--output-dir", type=Path, default=None)
    runpod_canary.add_argument("--download-results-dir", type=Path, default=None)
    runpod_canary.add_argument(
        "--reuse-pod-id",
        action="append",
        default=None,
        help=(
            "Reuse an existing canary pod as PROFILE=POD_ID. "
            "Pair with --no-cleanup when preserving a debugging pod."
        ),
    )
    runpod_canary.add_argument(
        "--allow-existing-prod-managed-pods",
        action="store_true",
        help=(
            "Allow cloud-test canary to ignore existing managed prod manual "
            "RunPod pods while still rejecting cloud-test leftovers."
        ),
    )
    runpod_canary.add_argument("--readiness-timeout", type=float, default=900.0)
    runpod_canary.add_argument("--worker-timeout", type=float, default=600.0)
    runpod_canary.add_argument("--task-timeout", type=float, default=1800.0)
    runpod_canary.add_argument("--poll-interval", type=float, default=10.0)
    runpod_canary.add_argument("--task-poll-interval", type=float, default=5.0)
    runpod_canary.add_argument("--control-ttl", type=int, default=3600)
    runpod_canary.add_argument("--quiet", action="store_true")
    runpod_canary.set_defaults(func=_cmd_runpod_canary)

    runpod_split_video_canary = runpod_subparsers.add_parser(
        "split-video-canary",
        help="cloud-test canary for split image_to_video and wan22_video_v2 RunPod profiles",
    )
    runpod_split_video_canary.add_argument("--env", default="cloud-test")
    runpod_split_video_canary.add_argument(
        "--env-file", type=Path, default=Path(".env.cloud.test")
    )
    runpod_split_video_canary.add_argument(
        "--no-env-file",
        action="store_const",
        const=None,
        dest="env_file",
    )
    runpod_split_video_canary.add_argument("--execute", action="store_true")
    runpod_split_video_canary.add_argument(
        "--profile",
        action="append",
        choices=("image_to_video", "wan22_video_v2"),
        default=None,
        help=(
            "Split video profile to test. Repeat to test multiple profiles. "
            "Defaults to both image_to_video and wan22_video_v2."
        ),
    )
    runpod_split_video_canary.add_argument(
        "--cleanup",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    runpod_split_video_canary.add_argument(
        "--disable-workers",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    runpod_split_video_canary.add_argument("--worker-id", action="append", default=None)
    runpod_split_video_canary.add_argument("--web-api-url", default=None)
    runpod_split_video_canary.add_argument("--central-url", default=None)
    runpod_split_video_canary.add_argument("--web-user-id", type=int, default=None)
    runpod_split_video_canary.add_argument("--web-pwd-ver", type=int, default=None)
    runpod_split_video_canary.add_argument(
        "--reuse-pod-id",
        action="append",
        default=None,
        help=(
            "Reuse an existing split-video pod as PROFILE=POD_ID. "
            "Pair with --no-cleanup when preserving a debugging pod."
        ),
    )
    runpod_split_video_canary.add_argument(
        "--prompt", default=DEFAULT_SPLIT_VIDEO_PROMPT
    )
    runpod_split_video_canary.add_argument("--negative-prompt", default=None)
    runpod_split_video_canary.add_argument("--input-object-key", default=None)
    runpod_split_video_canary.add_argument("--output-dir", type=Path, default=None)
    runpod_split_video_canary.add_argument(
        "--download-results-dir",
        type=Path,
        default=DEFAULT_SPLIT_VIDEO_RESULTS_DIR,
    )
    runpod_split_video_canary.add_argument(
        "--readiness-timeout", type=float, default=900.0
    )
    runpod_split_video_canary.add_argument(
        "--worker-timeout", type=float, default=600.0
    )
    runpod_split_video_canary.add_argument("--task-timeout", type=float, default=1800.0)
    runpod_split_video_canary.add_argument("--poll-interval", type=float, default=10.0)
    runpod_split_video_canary.add_argument(
        "--task-poll-interval", type=float, default=5.0
    )
    runpod_split_video_canary.add_argument("--control-ttl", type=int, default=3600)
    runpod_split_video_canary.add_argument("--quiet", action="store_true")
    runpod_split_video_canary.set_defaults(func=_cmd_runpod_split_video_canary)

    runpod_workers = runpod_subparsers.add_parser(
        "workers",
        help="scale cloud-test RunPod worker profiles",
    )
    workers_subparsers = runpod_workers.add_subparsers(
        dest="workers_command",
        required=True,
    )
    workers_common = argparse.ArgumentParser(add_help=False)
    workers_common.add_argument("--profile", required=True)
    workers_common.add_argument("--desired", type=int, required=True)
    workers_common.add_argument("--env", default="cloud-test")
    workers_common.add_argument(
        "--env-file", type=Path, default=Path(".env.cloud.test")
    )
    workers_common.add_argument(
        "--no-env-file", action="store_const", const=None, dest="env_file"
    )

    workers_render_scale = workers_subparsers.add_parser(
        "render-scale",
        parents=[workers_common],
    )
    workers_render_scale.set_defaults(func=_cmd_runpod_workers)

    workers_scale = workers_subparsers.add_parser(
        "scale",
        parents=[workers_common],
    )
    workers_scale.add_argument("--execute", action="store_true")
    workers_scale.set_defaults(func=_cmd_runpod_workers)

    runpod_split_video_manifests = runpod_subparsers.add_parser(
        "split-video-manifests",
        help="split Wan22 AIO model manifest into image_to_video and wan22_video_v2 manifests",
    )
    runpod_split_video_manifests.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env.cloud.test"),
    )
    runpod_split_video_manifests.add_argument(
        "--no-env-file",
        action="store_const",
        const=None,
        dest="env_file",
    )
    runpod_split_video_manifests.add_argument("--bucket", default=None)
    runpod_split_video_manifests.add_argument(
        "--source-key",
        default="wan22_aio_video/2026-06-12-test/manifest.json",
    )
    runpod_split_video_manifests.add_argument("--execute", action="store_true")
    runpod_split_video_manifests.set_defaults(func=_cmd_runpod_split_video_manifests)

    runpod_prod_worker = runpod_subparsers.add_parser(
        "prod-worker",
        help="manual cloud-prod RunPod worker control",
    )
    prod_worker_subparsers = runpod_prod_worker.add_subparsers(
        dest="prod_worker_command",
        required=True,
    )
    prod_worker_common = argparse.ArgumentParser(add_help=False)
    prod_worker_common.add_argument(
        "--runpod-env-file",
        type=Path,
        default=Path(".env.cloud.test"),
        help="env file used for RunPod API/profile defaults",
    )
    prod_worker_common.add_argument(
        "--no-runpod-env-file",
        action="store_const",
        const=None,
        dest="runpod_env_file",
    )
    prod_worker_common.add_argument(
        "--prod-env-file",
        type=Path,
        default=Path(".env.cloud.prod"),
        help="env file used for prod Central/Web/R2/JWT values",
    )
    prod_worker_common.add_argument(
        "--no-prod-env-file",
        action="store_const",
        const=None,
        dest="prod_env_file",
    )
    prod_worker_common.add_argument("--agent-id", default=None)
    prod_worker_common.add_argument(
        "--profile",
        choices=(
            "img2img",
            "image_to_video",
            "wan22_video_v2",
            "i2i_pro",
            "scail2",
            "ltx_video",
            "pornmaster_flux2_edit",
        ),
        default=None,
        help="prod RunPod worker profile; default img2img",
    )
    prod_worker_common.add_argument(
        "--slot",
        default=None,
        help="manual prod RunPod worker slot, e.g. 01 or NN",
    )
    prod_worker_common.add_argument("--central-url", default=None)
    prod_worker_common.add_argument("--web-api-url", default=None)
    prod_worker_common.add_argument("--web-user-id", type=int, default=None)
    prod_worker_common.add_argument("--web-pwd-ver", type=int, default=None)
    prod_worker_common.add_argument("--input-object-key", default=None)
    prod_worker_common.add_argument("--scail2-reference-object-key", default=None)
    prod_worker_common.add_argument("--scail2-motion-video-object-key", default=None)
    prod_worker_common.add_argument("--output-dir", type=Path, default=None)
    prod_worker_common.add_argument("--download-results-dir", type=Path, default=None)
    prod_worker_common.add_argument("--prompt", default=None)
    prod_worker_common.add_argument("--negative-prompt", default=None)
    prod_worker_common.add_argument("--readiness-timeout", type=float, default=900.0)
    prod_worker_common.add_argument(
        "--worker-timeout",
        type=float,
        default=PROD_WORKER_DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    )
    prod_worker_common.add_argument("--drain-timeout", type=float, default=300.0)
    prod_worker_common.add_argument("--task-timeout", type=float, default=1800.0)
    prod_worker_common.add_argument("--poll-interval", type=float, default=10.0)
    prod_worker_common.add_argument("--task-poll-interval", type=float, default=5.0)
    prod_worker_common.add_argument("--quiet", action="store_true")

    for command_name in ("render", "status"):
        prod_worker_command = prod_worker_subparsers.add_parser(
            command_name,
            parents=[prod_worker_common],
        )
        prod_worker_command.set_defaults(func=_cmd_runpod_prod_worker)

    for command_name in ("up", "enable", "disable", "restart", "down", "canary"):
        prod_worker_command = prod_worker_subparsers.add_parser(
            command_name,
            parents=[prod_worker_common],
        )
        prod_worker_command.add_argument("--execute", action="store_true")
        prod_worker_command.set_defaults(func=_cmd_runpod_prod_worker)

    prod_worker_add = prod_worker_subparsers.add_parser(
        "add",
        parents=[prod_worker_common],
    )
    prod_worker_add.add_argument("--count", type=int, required=True)
    prod_worker_add.add_argument("--execute", action="store_true")
    prod_worker_add.set_defaults(func=_cmd_runpod_prod_worker)

    prod_worker_scale = prod_worker_subparsers.add_parser(
        "scale",
        parents=[prod_worker_common],
    )
    prod_worker_scale.add_argument("--desired", type=int, required=True)
    prod_worker_scale.add_argument("--execute", action="store_true")
    prod_worker_scale.set_defaults(func=_cmd_runpod_prod_worker)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ValueError as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
