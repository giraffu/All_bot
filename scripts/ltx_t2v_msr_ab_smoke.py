#!/usr/bin/env python3
"""Run the isolated 5-second Ingredients/MSR V2/Sulphur comparison."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for path in (ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ltx_t2v_ic_ab_smoke import (  # noqa: E402
    AbCanaryError,
    BASELINE_WORKFLOW,
    _download_output,
    _ffprobe,
    _gpu_stats,
    _http_json,
    _make_contact_sheet,
    _upload_image,
    _write_json,
    submit_and_wait,
    validate_media_contract,
)
from workers.comfy_agent.workflow_patcher import WorkflowPatcher  # noqa: E402


MSR_LORA = "ltx2.3/LTX-2.3-Licon-MSR-V2.safetensors"
SULPHUR_LORA = "ltx2.3/sulphur_lora_rank_768.safetensors"
REQUIRED_NODES = {
    "CheckpointLoaderSimple",
    "LiconMSR",
    "LTXICLoRALoaderModelOnly",
    "LTXAddVideoICLoRAGuide",
    "LTXVCropGuides",
    "LoraLoaderModelOnly",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _to_msr(
    ingredients: dict[str, Any],
    *,
    reference_names: list[str],
    sulphur_strength: float | None,
) -> dict[str, Any]:
    if len(reference_names) != 4 or any(not value.strip() for value in reference_names):
        raise AbCanaryError("MSR V2 requires exactly four reference filenames")
    workflow = copy.deepcopy(ingredients)
    for node_id in ("195", "196", "270", "274", "5100", "273", "712", "198", "115"):
        workflow.pop(node_id, None)
    workflow["26:39"]["inputs"].update(width=768, height=448, length=121)
    workflow["800"] = {
        "class_type": "LTXICLoRALoaderModelOnly",
        "inputs": {
            "model": ["127", 0],
            "lora_name": MSR_LORA,
            "strength_model": 1.0,
        },
    }
    for offset, remote_name in enumerate(reference_names, start=2):
        workflow[str(800 + offset)] = {
            "class_type": "LoadImage",
            "inputs": {"image": remote_name},
        }
    workflow["806"] = {
        "class_type": "EmptyImage",
        "inputs": {"width": 768, "height": 448, "batch_size": 1, "color": 16777215},
    }
    workflow["801"] = {
        "class_type": "LiconMSR",
        "inputs": {
            "width": 768,
            "height": 448,
            "frame_count": "41",
            "1": ["802", 0],
            "2": ["803", 0],
            "3": ["804", 0],
            "4": ["805", 0],
            "background": ["806", 0],
        },
    }
    workflow["807"] = {
        "class_type": "LTXAddVideoICLoRAGuide",
        "inputs": {
            "positive": ["26:46", 0],
            "negative": ["26:46", 1],
            "vae": ["127", 2],
            "latent": ["26:39", 0],
            "image": ["801", 0],
            "frame_idx": 0,
            "strength": 1.0,
            "latent_downscale_factor": ["800", 1],
            "crop": "center",
            "use_tiled_encode": False,
            "tile_size": 256,
            "tile_overlap": 64,
        },
    }
    model = ["800", 0]
    if sulphur_strength is not None:
        workflow["808"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["800", 0],
                "lora_name": SULPHUR_LORA,
                "strength_model": sulphur_strength,
            },
        }
        model = ["808", 0]
    workflow["119"]["inputs"]["video_latent"] = ["807", 2]
    workflow["704"]["inputs"].update(
        model=model, positive=["807", 0], negative=["807", 1]
    )
    workflow["106"]["inputs"].update(
        positive=["807", 0], negative=["807", 1]
    )
    return workflow


def build_cases(
    *,
    repo_root: Path,
    ingredients_sheet_name: str,
    msr_reference_names: list[str],
    character_description: str,
    prompt: str,
    seed: int,
) -> list[dict[str, Any]]:
    if seed < 0 or not character_description.strip() or not prompt.strip():
        raise AbCanaryError("seed, character description and prompt are required")
    path = repo_root / BASELINE_WORKFLOW
    baseline = json.loads(path.read_text(encoding="utf-8"))
    baseline = WorkflowPatcher(str(repo_root / "workers/comfy_agent/workflows")).patch_workflow(
        "ltx_t2v_ic",
        baseline,
        {
            "prompt": prompt,
            "duration": 5,
            "character_sheet": ingredients_sheet_name,
            "character_description": character_description,
            "seed": seed,
        },
    )
    specs = (
        ("ingredients_5s", None, baseline),
        ("msr_v2_5s", None, _to_msr(baseline, reference_names=msr_reference_names, sulphur_strength=None)),
        ("msr_v2_sulphur_025_5s", 0.25, _to_msr(baseline, reference_names=msr_reference_names, sulphur_strength=0.25)),
        ("msr_v2_sulphur_050_5s", 0.5, _to_msr(baseline, reference_names=msr_reference_names, sulphur_strength=0.5)),
    )
    return [
        {"label": label, "duration": 5, "seed": seed, "sulphur_strength": strength, "workflow": workflow}
        for label, strength, workflow in specs
    ]


def case_evidence_metadata(case: dict[str, Any]) -> dict[str, Any]:
    is_msr = "800" in case["workflow"]
    chain = ["checkpoint:127"]
    if is_msr:
        chain.append("msr:800")
        if case["sulphur_strength"] is not None:
            chain.append(f"sulphur:808@{case['sulphur_strength']:.2f}")
    else:
        chain.extend(["ingredients:195", "ic_params:196"])
    return {
        "label": case["label"],
        "duration_seconds": 5,
        "seed": case["seed"],
        "sulphur_strength": case["sulphur_strength"],
        "workflow_sha256": hashlib.sha256(_canonical(case["workflow"])).hexdigest(),
        "model_chain": chain,
    }


def validate_runtime(object_info: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_NODES - set(object_info))
    if missing:
        raise AbCanaryError("missing ComfyUI node types: " + ", ".join(missing))
    def combo_options(node: str) -> set[str]:
        spec = object_info[node]["input"]["required"]["lora_name"]
        if spec[0] == "COMBO":
            return set(spec[1].get("options") or [])
        return set(spec[0])

    loras = combo_options("LTXICLoRALoaderModelOnly")
    generic_loras = combo_options("LoraLoaderModelOnly")
    if MSR_LORA not in loras or SULPHUR_LORA not in generic_loras:
        raise AbCanaryError("MSR V2 or Sulphur LoRA is absent from runtime")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--comfy-url", default="http://192.168.1.177:8191")
    parser.add_argument("--character-sheet", type=Path, required=True)
    parser.add_argument("--msr-reference", type=Path, action="append", required=True)
    parser.add_argument("--character-description-file", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--gpu-ssh-host", default="allbot-gpu-177")
    parser.add_argument("--gpu-index", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=3600)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if len(args.msr_reference) != 4:
        raise SystemExit("exactly four --msr-reference values are required")
    description = args.character_description_file.read_text(encoding="utf-8").strip()
    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sheet_remote = f"allbot-msr-ab-{run_id}-sheet.png"
    ref_remotes = [f"allbot-msr-ab-{run_id}-ref-{index}.png" for index in range(1, 5)]
    cases = build_cases(
        repo_root=ROOT,
        ingredients_sheet_name=sheet_remote,
        msr_reference_names=ref_remotes,
        character_description=description,
        prompt=prompt,
        seed=args.seed,
    )
    summary = {"ok": True, "dry_run": not args.execute, "seed": args.seed, "cases": [case_evidence_metadata(c) for c in cases]}
    if not args.execute:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    output_dir = args.output_dir or Path(os.getenv("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "allbot/ltx-msr-sulphur-ab" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    evidence = {**summary, "dry_run": False, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(), "results": []}
    _write_json(output_dir / "evidence.json", evidence)
    try:
        validate_runtime(_http_json("GET", f"{args.comfy_url.rstrip('/')}/object_info"))
        uploaded_sheet = _upload_image(comfy_url=args.comfy_url, path=args.character_sheet, remote_name=sheet_remote)
        uploaded_refs = [
            _upload_image(comfy_url=args.comfy_url, path=path, remote_name=remote)
            for path, remote in zip(args.msr_reference, ref_remotes)
        ]
        for case in cases:
            if "270" in case["workflow"]:
                case["workflow"]["270"]["inputs"]["image"] = uploaded_sheet
            for node_id, name in zip(("802", "803", "804", "805"), uploaded_refs):
                if node_id in case["workflow"]:
                    case["workflow"][node_id]["inputs"]["image"] = name
            before = _gpu_stats(ssh_host=args.gpu_ssh_host, gpu_index=args.gpu_index)
            started = time.monotonic()
            result = submit_and_wait(comfy_url=args.comfy_url, workflow=case["workflow"], timeout_seconds=args.timeout_seconds, poll_seconds=args.poll_seconds)
            video = output_dir / f"{case['label']}.mp4"
            _download_output(comfy_url=args.comfy_url, output=result["videos"][0], target=video)
            media = validate_media_contract(_ffprobe(video), expected_duration=5)
            contact = output_dir / f"{case['label']}-contact.png"
            _make_contact_sheet(video=video, target=contact, duration=5)
            evidence["results"].append({
                **case_evidence_metadata(case), "prompt_id": result["prompt_id"],
                "elapsed_seconds": round(time.monotonic() - started, 3), "video_file": video.name,
                "contact_sheet_file": contact.name, "media": media, "gpu_before": before,
                "gpu_after": _gpu_stats(ssh_host=args.gpu_ssh_host, gpu_index=args.gpu_index),
            })
            _write_json(output_dir / "evidence.json", evidence)
        evidence.update(status="passed", completed_at=datetime.now(timezone.utc).isoformat())
        _write_json(output_dir / "evidence.json", evidence)
    except Exception as exc:
        evidence.update(status="failed", completed_at=datetime.now(timezone.utc).isoformat(), error_type=type(exc).__name__)
        _write_json(output_dir / "evidence.json", evidence)
        raise
    print(json.dumps({"ok": True, "output_dir": str(output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
