#!/usr/bin/env python3
"""Run the isolated 5-second Ingredients/MSR V2/Sulphur comparison."""

from __future__ import annotations

import argparse
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


def build_cases(
    *,
    repo_root: Path,
    ingredients_sheet_name: str,
    msr_panel_names: list[str],
    character_descriptions: list[str],
    prompt: str,
    seed: int,
) -> list[dict[str, Any]]:
    if (
        seed < 0
        or not prompt.strip()
        or not 2 <= len(msr_panel_names) <= 4
        or len(character_descriptions) != len(msr_panel_names)
        or not all(value.strip() for value in character_descriptions)
    ):
        raise AbCanaryError(
            "seed, 2 to 4 panels, matching descriptions and prompt are required"
        )
    path = repo_root / BASELINE_WORKFLOW
    baseline = json.loads(path.read_text(encoding="utf-8"))
    baseline = WorkflowPatcher(
        str(repo_root / "workers/comfy_agent/workflows")
    ).patch_workflow(
        "ltx_t2v_ic",
        baseline,
        {
            "prompt": prompt,
            "duration": 5,
            "character_sheet": ingredients_sheet_name,
            "character_description": character_descriptions[0],
            "seed": seed,
        },
    )

    def msr(strength: float) -> dict[str, Any]:
        return WorkflowPatcher(
            str(repo_root / "workers/comfy_agent/workflows")
        ).patch_workflow(
            "ltx_t2v_ic",
            json.loads(path.read_text(encoding="utf-8")),
            {
                "prompt": prompt,
                "duration": 5,
                "character_sheets": msr_panel_names,
                "character_descriptions": character_descriptions,
                "sulphur_strength": strength,
                "seed": seed,
            },
        )

    specs = (
        ("ingredients_5s", None, baseline),
        ("msr_v2_5s", None, msr(0)),
        ("msr_v2_sulphur_025_5s", 0.25, msr(0.25)),
        ("msr_v2_sulphur_050_5s", 0.5, msr(0.5)),
    )
    return [
        {
            "label": label,
            "duration": 5,
            "seed": seed,
            "sulphur_strength": strength,
            "workflow": workflow,
        }
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
    parser.add_argument("--msr-panel", type=Path, action="append", required=True)
    parser.add_argument(
        "--character-description-file", type=Path, action="append", required=True
    )
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--gpu-ssh-host", default="allbot-gpu-177")
    parser.add_argument("--gpu-index", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=3600)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if not 2 <= len(args.msr_panel) <= 4:
        raise SystemExit("2 to 4 --msr-panel values are required")
    if len(args.character_description_file) != len(args.msr_panel):
        raise SystemExit("one --character-description-file is required per panel")
    descriptions = [
        path.read_text(encoding="utf-8").strip()
        for path in args.character_description_file
    ]
    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sheet_remote = f"allbot-msr-ab-{run_id}-sheet.png"
    panel_remotes = [
        f"allbot-msr-ab-{run_id}-panel-{index}.png"
        for index in range(1, len(args.msr_panel) + 1)
    ]
    cases = build_cases(
        repo_root=ROOT,
        ingredients_sheet_name=sheet_remote,
        msr_panel_names=panel_remotes,
        character_descriptions=descriptions,
        prompt=prompt,
        seed=args.seed,
    )
    summary = {
        "ok": True,
        "dry_run": not args.execute,
        "seed": args.seed,
        "cases": [case_evidence_metadata(c) for c in cases],
    }
    if not args.execute:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    output_dir = (
        args.output_dir
        or Path(os.getenv("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        / "allbot/ltx-msr-sulphur-ab"
        / run_id
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    evidence = {
        **summary,
        "dry_run": False,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "results": [],
    }
    _write_json(output_dir / "evidence.json", evidence)
    try:
        validate_runtime(_http_json("GET", f"{args.comfy_url.rstrip('/')}/object_info"))
        uploaded_sheet = _upload_image(
            comfy_url=args.comfy_url,
            path=args.character_sheet,
            remote_name=sheet_remote,
        )
        uploaded_panels = [
            _upload_image(comfy_url=args.comfy_url, path=path, remote_name=remote)
            for path, remote in zip(args.msr_panel, panel_remotes)
        ]
        for case in cases:
            if "270" in case["workflow"]:
                case["workflow"]["270"]["inputs"]["image"] = uploaded_sheet
            for node_id, name in zip(("802", "803", "804", "805"), uploaded_panels):
                if node_id in case["workflow"]:
                    case["workflow"][node_id]["inputs"]["image"] = name
            before = _gpu_stats(ssh_host=args.gpu_ssh_host, gpu_index=args.gpu_index)
            started = time.monotonic()
            result = submit_and_wait(
                comfy_url=args.comfy_url,
                workflow=case["workflow"],
                timeout_seconds=args.timeout_seconds,
                poll_seconds=args.poll_seconds,
            )
            video = output_dir / f"{case['label']}.mp4"
            _download_output(
                comfy_url=args.comfy_url, output=result["videos"][0], target=video
            )
            media = validate_media_contract(_ffprobe(video), expected_duration=5)
            contact = output_dir / f"{case['label']}-contact.png"
            _make_contact_sheet(video=video, target=contact, duration=5)
            evidence["results"].append(
                {
                    **case_evidence_metadata(case),
                    "prompt_id": result["prompt_id"],
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "video_file": video.name,
                    "contact_sheet_file": contact.name,
                    "media": media,
                    "gpu_before": before,
                    "gpu_after": _gpu_stats(
                        ssh_host=args.gpu_ssh_host, gpu_index=args.gpu_index
                    ),
                }
            )
            _write_json(output_dir / "evidence.json", evidence)
        evidence.update(
            status="passed", completed_at=datetime.now(timezone.utc).isoformat()
        )
        _write_json(output_dir / "evidence.json", evidence)
    except Exception as exc:
        evidence.update(
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error_type=type(exc).__name__,
        )
        _write_json(output_dir / "evidence.json", evidence)
        raise
    print(json.dumps({"ok": True, "output_dir": str(output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
