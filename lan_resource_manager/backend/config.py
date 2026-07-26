from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    allbot_root: Path
    state_dir: Path
    data_dir: Path
    prod_env_file: Path
    aio_env_file: Path
    model_env_file: Path
    allowed_networks: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    live_stale_seconds: int = 180

    @classmethod
    def from_env(cls) -> "Settings":
        home = Path(os.environ.get("HOME", "/home/app"))
        allbot_root = Path(os.environ.get("ALLBOT_ROOT", "/workspace"))
        return cls(
            allbot_root=allbot_root,
            state_dir=Path(
                os.environ.get(
                    "LAN_AIO_STATE_DIR",
                    str(home / ".local/state/allbot/lan-aio"),
                )
            ),
            data_dir=Path(
                os.environ.get(
                    "RESOURCE_MANAGER_DATA_DIR",
                    str(home / ".local/state/allbot/lan-resource-manager"),
                )
            ),
            prod_env_file=Path(
                os.environ.get("LAN_AIO_PROD_ENV_FILE", "/run/secrets/cloud-prod.env")
            ),
            aio_env_file=Path(
                os.environ.get("LAN_AIO_AIO_ENV_FILE", "/run/secrets/lan-aio.env")
            ),
            model_env_file=Path(
                os.environ.get(
                    "LAN_AIO_MODEL_ENV_FILE", "/run/secrets/lan-model-cache.env"
                )
            ),
            allowed_networks=tuple(
                item.strip()
                for item in os.environ.get(
                    "RESOURCE_MANAGER_ALLOWED_NETWORKS",
                    "192.168.1.0/24,127.0.0.0/8",
                ).split(",")
                if item.strip()
            ),
            allowed_hosts=tuple(
                item.strip()
                for item in os.environ.get(
                    "RESOURCE_MANAGER_ALLOWED_HOSTS",
                    "192.168.1.115,localhost,127.0.0.1,testserver",
                ).split(",")
                if item.strip()
            ),
            allowed_origins=tuple(
                item.strip()
                for item in os.environ.get(
                    "RESOURCE_MANAGER_ALLOWED_ORIGINS",
                    "http://192.168.1.115:8096",
                ).split(",")
                if item.strip()
            ),
            live_stale_seconds=int(
                os.environ.get("RESOURCE_MANAGER_LIVE_STALE_SECONDS", "180")
            ),
        )
