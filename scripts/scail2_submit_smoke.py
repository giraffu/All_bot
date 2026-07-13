#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


UI_ONLY_NODE_TYPES = {"MarkdownNote", "Reroute"}
LINKABLE_TYPES = {
    "AUDIO",
    "CLIP",
    "CLIP_VISION",
    "CLIP_VISION_OUTPUT",
    "CONDITIONING",
    "IMAGE",
    "LATENT",
    "MASK",
    "MODEL",
    "SAM3_TRACK_DATA",
    "VAE",
    "VHS_BatchManager",
    "VHS_VIDEOINFO",
}


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    data = None
    headers = {"User-Agent": "allbot-scail2-smoke/1.0"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def _node_input_defs(info: dict[str, Any]) -> list[tuple[str, Any]]:
    inputs = info.get("input") or {}
    ordered: list[tuple[str, Any]] = []
    for section_name in ("required", "optional"):
        section = inputs.get(section_name) or {}
        ordered.extend(section.items())
    return ordered


def _is_widget_input(name: str, spec: Any) -> bool:
    if name == "upload":
        return False
    if not isinstance(spec, list) or not spec:
        return False
    kind = spec[0]
    if isinstance(kind, list):
        return True
    if isinstance(kind, str):
        if "," in kind:
            return False
        return kind in {"INT", "FLOAT", "BOOLEAN", "STRING", "COMBO", "COMFY_DYNAMICCOMBO_V3"}
    return False


def _clean_widget_dict(values: dict[str, Any], class_info: dict[str, Any]) -> dict[str, Any]:
    allowed = {name for name, _ in _node_input_defs(class_info)}
    return {key: value for key, value in values.items() if key in allowed}


def _control_after_generate(spec: Any) -> bool:
    if not isinstance(spec, list) or len(spec) < 2 or not isinstance(spec[1], dict):
        return False
    return bool(spec[1].get("control_after_generate"))


def _dynamic_widget_specs(parent_name: str, spec: Any, selected: Any) -> list[tuple[str, Any]]:
    if not isinstance(spec, list) or len(spec) < 2 or spec[0] != "COMFY_DYNAMICCOMBO_V3":
        return []
    metadata = spec[1] if isinstance(spec[1], dict) else {}
    for option in metadata.get("options") or []:
        if not isinstance(option, dict) or option.get("key") != selected:
            continue
        nested_inputs = option.get("inputs") or {}
        nested: list[tuple[str, Any]] = []
        for section_name in ("required", "optional"):
            section = nested_inputs.get(section_name) or {}
            nested.extend((f"{parent_name}.{nested_name}", nested_spec) for nested_name, nested_spec in section.items())
        return nested
    return []


def _apply_widget_list(
    *,
    inputs: dict[str, Any],
    widgets: list[Any],
    class_info: dict[str, Any],
) -> None:
    linked_names = set(inputs)
    widget_index = 0
    for name, spec in _node_input_defs(class_info):
        if widget_index >= len(widgets):
            break
        if not _is_widget_input(name, spec):
            continue
        value = widgets[widget_index]
        widget_index += 1
        if name not in linked_names:
            inputs[name] = value
        if _control_after_generate(spec) and widget_index < len(widgets):
            widget_index += 1

        for dynamic_name, dynamic_spec in _dynamic_widget_specs(name, spec, value):
            if widget_index >= len(widgets):
                break
            if not _is_widget_input(dynamic_name, dynamic_spec):
                continue
            dynamic_value = widgets[widget_index]
            widget_index += 1
            if dynamic_name not in linked_names:
                inputs[dynamic_name] = dynamic_value


def _build_link_maps(workflow: dict[str, Any]) -> tuple[dict[int, tuple[int, int]], dict[int, dict[str, Any]]]:
    link_map: dict[int, tuple[int, int]] = {}
    for raw_link in workflow.get("links") or []:
        if len(raw_link) < 6:
            continue
        link_id, origin_id, origin_slot = raw_link[0], raw_link[1], raw_link[2]
        link_map[int(link_id)] = (int(origin_id), int(origin_slot))
    nodes_by_id = {int(node["id"]): node for node in workflow.get("nodes") or []}
    return link_map, nodes_by_id


def _resolve_link(
    link_id: int,
    link_map: dict[int, tuple[int, int]],
    nodes_by_id: dict[int, dict[str, Any]],
    seen: set[int] | None = None,
) -> list[Any]:
    seen = seen or set()
    if link_id in seen:
        raise ValueError(f"cycle while resolving link {link_id}")
    seen.add(link_id)
    origin_id, origin_slot = link_map[link_id]
    origin_node = nodes_by_id.get(origin_id) or {}
    if origin_node.get("type") == "Reroute":
        for ui_input in origin_node.get("inputs") or []:
            reroute_link = ui_input.get("link")
            if reroute_link is not None:
                return _resolve_link(int(reroute_link), link_map, nodes_by_id, seen)
    return [str(origin_id), origin_slot]


def workflow_to_api_prompt(
    workflow: dict[str, Any],
    object_info: dict[str, Any],
    *,
    reference_image: str,
    motion_video: str,
    frame_cap: int | None,
    length: int | None,
    filename_prefix: str,
) -> dict[str, Any]:
    link_map, nodes_by_id = _build_link_maps(workflow)
    prompt: dict[str, Any] = {}
    missing_node_types: set[str] = set()

    for node in workflow.get("nodes") or []:
        node_id = str(node["id"])
        class_type = str(node.get("type") or "")
        if class_type in UI_ONLY_NODE_TYPES:
            continue
        class_info = object_info.get(class_type)
        if not class_info:
            missing_node_types.add(class_type)
            continue

        inputs: dict[str, Any] = {}
        for ui_input in node.get("inputs") or []:
            name = ui_input.get("name")
            raw_link = ui_input.get("link")
            if not name or raw_link is None:
                continue
            inputs[str(name)] = _resolve_link(int(raw_link), link_map, nodes_by_id)

        widgets = node.get("widgets_values")
        if isinstance(widgets, dict):
            inputs.update(_clean_widget_dict(widgets, class_info))
        elif isinstance(widgets, list):
            _apply_widget_list(inputs=inputs, widgets=widgets, class_info=class_info)

        if class_type == "LoadImage":
            inputs["image"] = reference_image
        elif class_type == "VHS_LoadVideo":
            inputs["video"] = motion_video
            if frame_cap is not None:
                inputs["frame_load_cap"] = frame_cap
        elif class_type == "WanSCAILToVideo" and length is not None:
            inputs["length"] = length
        elif class_type == "VHS_VideoCombine":
            inputs["filename_prefix"] = filename_prefix
            inputs["save_output"] = True

        prompt[node_id] = {"class_type": class_type, "inputs": inputs}

    if missing_node_types:
        missing = ", ".join(sorted(missing_node_types))
        raise RuntimeError(f"missing ComfyUI node types: {missing}")

    unresolved_links = {
        str(node_id): [value[0] for value in item["inputs"].values() if isinstance(value, list)]
        for node_id, item in prompt.items()
    }
    prompt_ids = set(prompt)
    bad_refs = sorted(
        {
            ref_id
            for refs in unresolved_links.values()
            for ref_id in refs
            if ref_id not in prompt_ids
        }
    )
    if bad_refs:
        raise RuntimeError(f"API prompt references skipped UI-only nodes: {', '.join(bad_refs)}")

    missing_required: list[str] = []
    for node_id, item in prompt.items():
        class_info = object_info[item["class_type"]]
        required = (class_info.get("input") or {}).get("required") or {}
        for name in required:
            if name not in item["inputs"]:
                missing_required.append(f"{node_id}:{item['class_type']}.{name}")
    if missing_required:
        raise RuntimeError("missing required inputs: " + ", ".join(missing_required[:20]))

    return prompt


def _collect_video_outputs(history_entry: dict[str, Any]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    for node_output in (history_entry.get("outputs") or {}).values():
        for key in ("gifs", "videos", "images"):
            for item in node_output.get(key) or []:
                filename = str(item.get("filename") or "")
                if filename.lower().endswith(".mp4"):
                    videos.append(item)
    return videos


def submit_and_wait(
    *,
    comfy_url: str,
    prompt: dict[str, Any],
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    client_id = str(uuid.uuid4())
    submit = _http_json(
        "POST",
        f"{comfy_url.rstrip('/')}/prompt",
        {"prompt": prompt, "client_id": client_id},
    )
    prompt_id = submit.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return prompt_id: {submit}")

    deadline = time.time() + timeout_seconds
    last_status = ""
    while time.time() < deadline:
        time.sleep(poll_seconds)
        history = _http_json("GET", f"{comfy_url.rstrip('/')}/history/{prompt_id}")
        if prompt_id not in history:
            queue = _http_json("GET", f"{comfy_url.rstrip('/')}/queue")
            status = json.dumps(
                {
                    "running": len(queue.get("queue_running") or []),
                    "pending": len(queue.get("queue_pending") or []),
                },
                ensure_ascii=False,
            )
            if status != last_status:
                print(f"[scail2-smoke] waiting prompt_id={prompt_id} {status}", flush=True)
                last_status = status
            continue

        entry = history[prompt_id]
        status = entry.get("status") or {}
        if status.get("completed") is False or status.get("status_str") == "error":
            raise RuntimeError(json.dumps(status, ensure_ascii=False))
        return {"prompt_id": prompt_id, "history": entry, "videos": _collect_video_outputs(entry)}
    raise TimeoutError(f"timed out waiting for prompt_id={prompt_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a Nomadoor SCAIL-2 UI workflow to ComfyUI")
    parser.add_argument("--comfy-url", default="http://192.168.1.2:8190")
    parser.add_argument(
        "--workflow",
        type=Path,
        default=Path("workers/comfy_agent/workflows/SCAIL-2_Animation.json"),
    )
    parser.add_argument("--reference-image", default="pexels-photo-31438123.jpg")
    parser.add_argument("--motion-video", default="14637751_2160_3840_30fps.mp4")
    parser.add_argument("--frame-cap", type=int, default=81)
    parser.add_argument("--length", type=int, default=81)
    parser.add_argument("--filename-prefix", default="SCAIL-2")
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="convert and validate without submitting")
    parser.add_argument("--print-prompt", action="store_true", help="print converted API prompt JSON")
    args = parser.parse_args()

    workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
    object_info = _http_json("GET", f"{args.comfy_url.rstrip('/')}/object_info")
    prompt = workflow_to_api_prompt(
        workflow,
        object_info,
        reference_image=args.reference_image,
        motion_video=args.motion_video,
        frame_cap=args.frame_cap,
        length=args.length,
        filename_prefix=args.filename_prefix,
    )
    print(
        json.dumps(
            {
                "workflow": str(args.workflow),
                "api_nodes": len(prompt),
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
        )
    )
    if args.print_prompt:
        print(json.dumps(prompt, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    try:
        result = submit_and_wait(
            comfy_url=args.comfy_url,
            prompt=prompt,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(body, file=sys.stderr)
        raise
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("videos"):
        raise RuntimeError("SCAIL-2 smoke completed but no mp4 output was reported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
