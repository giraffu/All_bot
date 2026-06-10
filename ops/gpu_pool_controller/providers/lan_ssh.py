from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from ..types import GpuNode


@dataclass(frozen=True)
class SshCommandResult:
    host: str
    command: str
    returncode: int
    stdout: str
    stderr: str


class LanSshProvider:
    provider = "lan_ssh"

    def __init__(self, *, connect_timeout_seconds: int = 5):
        self.connect_timeout_seconds = connect_timeout_seconds

    def inventory_from_config(self, nodes: dict[str, GpuNode]) -> dict[str, Any]:
        return {
            node_id: {
                "provider": node.provider,
                "host": node.host,
                "ip": node.ip,
                "ssh_alias": node.ssh_alias,
                "runtime": node.runtime,
                "model_dir": node.model_dir,
                "gpus": [
                    {"index": gpu.index, "name": gpu.name, "vram_gb": gpu.vram_gb}
                    for gpu in node.gpus
                ],
                "comfy": [
                    {
                        "id": comfy.id,
                        "api_url": comfy.api_url,
                        "gpu_index": comfy.gpu_index,
                        "worker_id": comfy.worker_id,
                        "model_dir": comfy.model_dir,
                        "comfy_runtime_kind": comfy.comfy_runtime_kind,
                        "comfy_runtime_managed": comfy.comfy_runtime_managed,
                        "container_name": comfy.container_name,
                        "supported_task_types": list(comfy.supported_task_types),
                    }
                    for comfy in node.comfy
                ],
            }
            for node_id, node in nodes.items()
            if node.provider == self.provider
        }

    def run_readonly(self, node: GpuNode, command: str) -> SshCommandResult:
        ssh_command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={self.connect_timeout_seconds}",
            node.ssh_alias,
            command,
        ]
        proc = subprocess.run(
            ssh_command,
            check=False,
            text=True,
            capture_output=True,
        )
        return SshCommandResult(
            host=node.ssh_alias,
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    @staticmethod
    def to_jsonable(result: SshCommandResult) -> dict[str, Any]:
        return {
            "host": result.host,
            "command": result.command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    @staticmethod
    def dumps_inventory(inventory: dict[str, Any]) -> str:
        return json.dumps(inventory, ensure_ascii=False, indent=2)
