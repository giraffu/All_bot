from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NearPromptEdge:
    task_type: str
    source_hash: str
    neighbor_hash: str
    similarity: float


@dataclass(frozen=True)
class NearPromptStats:
    prompt_hash: str
    task_type: str
    prompt: str
    quality_score: float
    uses: int
    users: int
    last_seen: datetime | str | None
    result_likes: int = 0
    result_dislikes: int = 0
    gallery_applies: int = 0
    prompt_unlocks: int = 0
    char_count: int | None = None


@dataclass(frozen=True)
class NearRepresentativeGroup:
    task_type: str
    representative_hash: str
    member_hashes: list[str]
    pair_similarities: list[float]
    similarity_to_representative: dict[str, float]


def representative_score(stats: NearPromptStats | dict[str, Any]) -> tuple[float, int, int, float]:
    if isinstance(stats, NearPromptStats):
        quality_score = stats.quality_score
        uses = stats.uses
        users = stats.users
        last_seen = stats.last_seen
    else:
        quality_score = stats.get("quality_score") or 0
        uses = stats.get("uses") or 0
        users = stats.get("users") or 0
        last_seen = stats.get("last_seen")
    if isinstance(last_seen, datetime):
        last_seen_score = last_seen.timestamp()
    else:
        last_seen_score = 0.0
    return (float(quality_score or 0), int(uses or 0), int(users or 0), last_seen_score)


def build_near_representative_groups(
    edges: list[NearPromptEdge],
    stats_by_hash: dict[str, NearPromptStats],
    *,
    threshold: float,
) -> list[NearRepresentativeGroup]:
    task_adjacency: dict[str, dict[str, dict[str, float]]] = {}
    for edge in edges:
        if edge.similarity < threshold:
            continue
        if edge.source_hash not in stats_by_hash or edge.neighbor_hash not in stats_by_hash:
            continue
        task = edge.task_type or stats_by_hash[edge.source_hash].task_type or "unknown"
        task_adjacency.setdefault(task, {}).setdefault(edge.source_hash, {})
        task_adjacency.setdefault(task, {}).setdefault(edge.neighbor_hash, {})
        task_adjacency[task][edge.source_hash][edge.neighbor_hash] = max(
            edge.similarity,
            task_adjacency[task][edge.source_hash].get(edge.neighbor_hash, 0),
        )
        task_adjacency[task][edge.neighbor_hash][edge.source_hash] = max(
            edge.similarity,
            task_adjacency[task][edge.neighbor_hash].get(edge.source_hash, 0),
        )

    groups: list[NearRepresentativeGroup] = []
    for task_type, adjacency in sorted(task_adjacency.items()):
        candidates = [prompt_hash for prompt_hash in adjacency if prompt_hash in stats_by_hash]
        ordered = sorted(
            candidates,
            key=lambda prompt_hash: (*representative_score(stats_by_hash[prompt_hash]), prompt_hash),
            reverse=True,
        )
        unassigned = set(ordered)
        for representative in ordered:
            if representative not in unassigned:
                continue

            members = [representative]
            neighbors = [
                neighbor
                for neighbor, similarity in adjacency.get(representative, {}).items()
                if neighbor in unassigned and neighbor in stats_by_hash and similarity >= threshold
            ]
            neighbors.sort(
                key=lambda neighbor: (
                    adjacency[representative].get(neighbor, 0),
                    *representative_score(stats_by_hash[neighbor]),
                    neighbor,
                ),
                reverse=True,
            )

            for neighbor in neighbors:
                if all(adjacency.get(neighbor, {}).get(member, 0) >= threshold for member in members):
                    members.append(neighbor)

            unassigned.discard(representative)
            if len(members) < 2:
                continue
            for member in members[1:]:
                unassigned.discard(member)

            pair_similarities = [
                adjacency[left].get(right, 0)
                for index, left in enumerate(members)
                for right in members[index + 1 :]
                if adjacency[left].get(right, 0) >= threshold
            ]
            representative_similarities = {
                member: (1.0 if member == representative else adjacency[representative].get(member, 0.0))
                for member in members
            }
            groups.append(
                NearRepresentativeGroup(
                    task_type=task_type,
                    representative_hash=representative,
                    member_hashes=members,
                    pair_similarities=pair_similarities or [1.0],
                    similarity_to_representative=representative_similarities,
                )
            )

    groups.sort(
        key=lambda group: (
            len(group.member_hashes),
            *representative_score(stats_by_hash[group.representative_hash]),
            group.representative_hash,
        ),
        reverse=True,
    )
    return groups
