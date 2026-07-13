from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .types import DEFAULT_DOCKER_REGISTRY_ROOT


@dataclass(frozen=True)
class LocalRegistry:
    host: str = "192.168.1.115"
    port: int = 5000
    data_root: Path = DEFAULT_DOCKER_REGISTRY_ROOT

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    def target_ref(self, repository: str, tag: str) -> str:
        return f"{self.endpoint}/{repository}:{tag}"

    def render_publish_plan(self, *, source_image: str, repository: str, tag: str) -> list[str]:
        target = self.target_ref(repository, tag)
        return [
            f"docker tag {source_image} {target}",
            f"docker push {target}",
            f"docker pull {target}",
        ]

    def render_seed_plan(self, images: list[tuple[str, str, str]]) -> list[str]:
        commands: list[str] = []
        for source_image, repository, tag in images:
            commands.extend(
                self.render_publish_plan(
                    source_image=source_image,
                    repository=repository,
                    tag=tag,
                )
            )
        return commands
