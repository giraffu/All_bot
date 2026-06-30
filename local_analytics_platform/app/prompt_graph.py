from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncpg
import numpy as np

from .prompt_mart import PROMPT_NORMALIZATION_VERSION
from .prompt_vectors import (
    DEFAULT_DUPLICATE_THRESHOLD,
    DEFAULT_SIMILAR_THRESHOLD,
    DEFAULT_VECTOR_MODEL_ID,
    DEFAULT_VECTOR_MODEL_KEY,
    embedding_from_bytes,
)


PROMPT_GRAPH_ALGORITHM_VERSION = "prompt-graph-v2"
PROMPT_GRAPH_LAYOUT_ALGORITHM = "pca-v1"
DEFAULT_NATURAL_SCENE_MIN_SIMILARITY = DEFAULT_DUPLICATE_THRESHOLD
NATURAL_SCENE_PREFIX = "scene-v2"
MICRO_COMMUNITY_PREFIX = "micro-v2"
TASK_COMMUNITY_PREFIX = "task-v2"
TAIL_COMMUNITY_PREFIX = "tail-v2"


CREATE_PROMPT_GRAPH_SCHEMA_SQL = [
    """
    create table if not exists analytics_prompt_graph_state (
        key text primary key,
        value text not null,
        updated_at timestamptz not null default now()
    )
    """,
    f"""
    create table if not exists analytics_prompt_graph_nodes (
        model_id text not null,
        normalization_version text not null,
        algorithm_version text not null default '{PROMPT_GRAPH_ALGORITHM_VERSION}',
        prompt_hash text not null,
        task_type text not null,
        prompt text not null,
        node_status text not null,
        has_embedding boolean not null default false,
        has_scene boolean not null default false,
        has_micro boolean not null default false,
        scene_id text,
        micro_cluster_id text,
        quality_score numeric(20, 2) not null default 0,
        uses bigint not null default 0,
        users bigint not null default 0,
        first_seen timestamptz,
        last_seen timestamptz,
        refreshed_at timestamptz not null default now(),
        primary key (model_id, normalization_version, algorithm_version, prompt_hash),
        constraint chk_prompt_graph_node_status check (node_status in ('unembedded', 'no_scene', 'singleton', 'clustered'))
    )
    """,
    f"""
    create table if not exists analytics_prompt_graph_communities (
        community_id text primary key,
        model_id text not null,
        normalization_version text not null,
        algorithm_version text not null default '{PROMPT_GRAPH_ALGORITHM_VERSION}',
        community_type text not null,
        parent_community_id text,
        task_type text not null,
        label text not null,
        representative_hash text,
        representative_prompt text not null default '',
        member_count bigint not null default 0,
        micro_count bigint not null default 0,
        singleton_count bigint not null default 0,
        no_scene_count bigint not null default 0,
        min_similarity numeric(8, 6),
        avg_similarity numeric(8, 6),
        max_similarity numeric(8, 6),
        total_uses bigint not null default 0,
        total_users bigint not null default 0,
        quality_score numeric(20, 2) not null default 0,
        created_at timestamptz not null default now(),
        refreshed_at timestamptz not null default now(),
        constraint chk_prompt_graph_community_type check (community_type in ('scene', 'micro', 'task'))
    )
    """,
    """
    create table if not exists analytics_prompt_graph_memberships (
        community_id text not null,
        prompt_hash text not null,
        model_id text not null,
        normalization_version text not null,
        algorithm_version text not null,
        membership_type text not null,
        task_type text not null,
        confidence numeric(8, 6),
        confidence_band text not null,
        member_rank integer not null,
        created_at timestamptz not null default now(),
        primary key (community_id, prompt_hash, membership_type),
        constraint chk_prompt_graph_membership_type check (membership_type in ('scene', 'micro')),
        constraint chk_prompt_graph_confidence_band check (confidence_band in ('high', 'medium', 'low', 'unknown'))
    )
    """,
    """
    create table if not exists analytics_prompt_graph_community_edges (
        model_id text not null,
        normalization_version text not null,
        algorithm_version text not null,
        source_community_id text not null,
        target_community_id text not null,
        edge_type text not null,
        source_task_type text not null default 'unknown',
        target_task_type text not null default 'unknown',
        weight numeric(10, 6) not null default 0,
        prompt_edge_count bigint not null default 0,
        duplicate_edge_count bigint not null default 0,
        similar_edge_count bigint not null default 0,
        avg_similarity numeric(8, 6),
        max_similarity numeric(8, 6),
        created_at timestamptz not null default now(),
        primary key (model_id, normalization_version, algorithm_version, source_community_id, target_community_id, edge_type),
        constraint chk_prompt_graph_edge_type check (edge_type in ('similarity', 'centroid_bridge', 'scene_micro'))
    )
    """,
    """
    create table if not exists analytics_prompt_graph_layout (
        model_id text not null,
        normalization_version text not null,
        algorithm_version text not null,
        community_type text not null,
        community_id text not null,
        layout_algorithm text not null,
        x numeric(14, 6) not null,
        y numeric(14, 6) not null,
        radius numeric(10, 4) not null default 8,
        refreshed_at timestamptz not null default now(),
        primary key (model_id, normalization_version, algorithm_version, community_id, layout_algorithm)
    )
    """,
    "create index if not exists idx_prompt_graph_nodes_status on analytics_prompt_graph_nodes(model_id, normalization_version, algorithm_version, node_status)",
    "create index if not exists idx_prompt_graph_nodes_scene on analytics_prompt_graph_nodes(scene_id)",
    "create index if not exists idx_prompt_graph_nodes_micro on analytics_prompt_graph_nodes(micro_cluster_id)",
    "create index if not exists idx_prompt_graph_communities_type on analytics_prompt_graph_communities(model_id, normalization_version, algorithm_version, community_type, member_count desc)",
    "create index if not exists idx_prompt_graph_memberships_prompt on analytics_prompt_graph_memberships(prompt_hash)",
    "create index if not exists idx_prompt_graph_edges_source on analytics_prompt_graph_community_edges(source_community_id, edge_type)",
    "create index if not exists idx_prompt_graph_edges_target on analytics_prompt_graph_community_edges(target_community_id, edge_type)",
]


PROMPT_GRAPH_READY_SQL = """
select
    to_regclass('public.analytics_prompt_graph_state') is not null
    and to_regclass('public.analytics_prompt_graph_nodes') is not null
    and to_regclass('public.analytics_prompt_graph_communities') is not null
    and to_regclass('public.analytics_prompt_graph_memberships') is not null
    and to_regclass('public.analytics_prompt_graph_community_edges') is not null
    and to_regclass('public.analytics_prompt_graph_layout') is not null
    as ready
"""


@dataclass(frozen=True)
class PromptGraphConfig:
    model_id: str = DEFAULT_VECTOR_MODEL_ID
    model_key: str = DEFAULT_VECTOR_MODEL_KEY
    natural_scene_min_similarity: float = DEFAULT_NATURAL_SCENE_MIN_SIMILARITY


@dataclass(frozen=True)
class GraphScene:
    scene_id: str
    task_type: str
    member_count: int
    centroid: np.ndarray


@dataclass(frozen=True)
class GraphAtom:
    task_type: str
    atom_id: str


@dataclass(frozen=True)
class GraphAtomEdge:
    task_type: str
    source_atom_id: str
    target_atom_id: str
    similarity: float = DEFAULT_NATURAL_SCENE_MIN_SIMILARITY


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[tuple[str, str], tuple[str, str]] = {}

    def add(self, item: tuple[str, str]) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: tuple[str, str]) -> tuple[str, str]:
        self.add(item)
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: tuple[str, str], right: tuple[str, str]) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        self.parent[max(left_root, right_root)] = min(left_root, right_root)


def _graph_state_key(model_id: str, normalization_version: str, key: str) -> str:
    return f"{model_id}:{normalization_version}:{PROMPT_GRAPH_ALGORITHM_VERSION}:{key}"


async def ensure_prompt_graph_schema(conn: Any) -> None:
    for statement in CREATE_PROMPT_GRAPH_SCHEMA_SQL:
        await conn.execute(statement)


async def set_graph_state(conn: Any, model_id: str, values: dict[str, Any]) -> None:
    for key, value in values.items():
        await conn.execute(
            """
            insert into analytics_prompt_graph_state (key, value, updated_at)
            values ($1::text, $2::text, now())
            on conflict (key) do update set value = excluded.value, updated_at = now()
            """,
            _graph_state_key(model_id, PROMPT_NORMALIZATION_VERSION, key),
            json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value,
        )


def graph_node_status(*, has_embedding: bool, has_scene: bool, has_micro: bool) -> str:
    if not has_embedding:
        return "unembedded"
    if not has_scene:
        return "no_scene"
    if not has_micro:
        return "singleton"
    return "clustered"


def _hash_key(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def natural_scene_id(task_type: str, atom_ids: list[str]) -> str:
    fingerprint = _hash_key(f"{PROMPT_GRAPH_ALGORITHM_VERSION}|{task_type}|{'|'.join(sorted(atom_ids))}")
    return f"{NATURAL_SCENE_PREFIX}:{fingerprint}"


def micro_community_id(cluster_id: str) -> str:
    return f"{MICRO_COMMUNITY_PREFIX}:{cluster_id}"


def task_community_id(task_type: str) -> str:
    return f"{TASK_COMMUNITY_PREFIX}:{_hash_key(task_type)}"


def tail_community_id(task_type: str) -> str:
    return f"{TAIL_COMMUNITY_PREFIX}:{_hash_key(task_type)}"


def split_atom_id(atom_id: str) -> tuple[str, str]:
    kind, _, key = atom_id.partition(":")
    if kind not in {"micro", "prompt"} or not key:
        raise ValueError(f"invalid graph atom id: {atom_id}")
    return kind, key


def build_natural_scene_atom_rows(
    micro_atoms: list[GraphAtom],
    edges: list[GraphAtomEdge],
) -> list[tuple[str, str, str, str, int]]:
    graph = _UnionFind()
    for atom in micro_atoms:
        graph.add((atom.task_type, atom.atom_id))
    for edge in edges:
        if edge.source_atom_id == edge.target_atom_id:
            continue
        source = (edge.task_type, edge.source_atom_id)
        target = (edge.task_type, edge.target_atom_id)
        graph.union(source, target)

    components: dict[tuple[str, str], list[str]] = {}
    for task_type, atom_id in sorted(graph.parent):
        components.setdefault(graph.find((task_type, atom_id)), []).append(atom_id)

    rows: list[tuple[str, str, str, str, int]] = []
    for root, atom_ids in sorted(components.items()):
        task_type = root[0]
        sorted_atoms = sorted(set(atom_ids))
        has_micro = any(atom_id.startswith("micro:") for atom_id in sorted_atoms)
        if not has_micro and len(sorted_atoms) < 2:
            continue
        scene_id = natural_scene_id(task_type, sorted_atoms)
        for rank, atom_id in enumerate(sorted_atoms, start=1):
            atom_kind, atom_key = split_atom_id(atom_id)
            rows.append((scene_id, task_type, atom_kind, atom_key, rank))
    return rows


def _community_radius(member_count: int) -> float:
    return round(max(5.0, min(34.0, 4.0 + math.log1p(max(0, int(member_count))) * 2.8)), 4)


def _stable_unit_interval(value: str) -> float:
    raw = hashlib.md5(value.encode("utf-8")).hexdigest()[:12]
    return int(raw, 16) / float(16**12 - 1)


def build_scene_layout_rows(
    model_id: str,
    normalization_version: str,
    scenes: list[GraphScene],
) -> list[tuple[Any, ...]]:
    if not scenes:
        return []
    rows: list[tuple[Any, ...]] = []
    scenes_by_task: dict[str, list[GraphScene]] = {}
    for scene in scenes:
        scenes_by_task.setdefault(scene.task_type, []).append(scene)
    for task_type in sorted(scenes_by_task):
        task_scenes = scenes_by_task[task_type]
        if len(task_scenes) == 1:
            coords = np.zeros((1, 2), dtype=np.float32)
        else:
            matrix = np.stack([scene.centroid for scene in task_scenes]).astype(np.float32, copy=False)
            centered = matrix - matrix.mean(axis=0, keepdims=True)
            try:
                _, _, vt = np.linalg.svd(centered, full_matrices=False)
                components = vt[:2]
                if components.shape[0] == 1:
                    components = np.vstack([components, np.zeros_like(components[0])])
                coords = centered @ components[:2].T
                for axis in range(2):
                    component = components[axis]
                    pivot = int(np.argmax(np.abs(component)))
                    if component[pivot] < 0:
                        coords[:, axis] *= -1
            except np.linalg.LinAlgError:
                angles = np.linspace(0, 2 * math.pi, len(task_scenes), endpoint=False)
                coords = np.stack([np.cos(angles), np.sin(angles)], axis=1).astype(np.float32)
            for axis in range(2):
                limit = float(np.max(np.abs(coords[:, axis])))
                if math.isfinite(limit) and limit > 0:
                    coords[:, axis] = coords[:, axis] / limit
        for index, scene in enumerate(task_scenes):
            rows.append(
                (
                    model_id,
                    normalization_version,
                    PROMPT_GRAPH_ALGORITHM_VERSION,
                    "scene",
                    scene.scene_id,
                    PROMPT_GRAPH_LAYOUT_ALGORITHM,
                    round(float(coords[index, 0]), 6),
                    round(float(coords[index, 1]), 6),
                    _community_radius(scene.member_count),
                )
            )
    return rows


def build_child_layout_rows(
    model_id: str,
    normalization_version: str,
    children: list[dict[str, Any]],
    parent_layout: dict[str, tuple[float, float]],
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for child in children:
        community_id = str(child["community_id"])
        parent_id = child.get("parent_community_id")
        parent_x, parent_y = parent_layout.get(str(parent_id), (0.0, 0.0))
        angle = _stable_unit_interval(community_id) * 2 * math.pi
        distance = 0.08 + _stable_unit_interval(f"{community_id}:distance") * 0.16
        member_count = int(child.get("member_count") or 0)
        rows.append(
            (
                model_id,
                normalization_version,
                PROMPT_GRAPH_ALGORITHM_VERSION,
                str(child.get("community_type") or "micro"),
                community_id,
                PROMPT_GRAPH_LAYOUT_ALGORITHM,
                round(parent_x + math.cos(angle) * distance, 6),
                round(parent_y + math.sin(angle) * distance, 6),
                _community_radius(member_count),
            )
        )
    return rows


async def _clear_graph(conn: Any, config: PromptGraphConfig) -> None:
    args = (config.model_id, PROMPT_NORMALIZATION_VERSION, PROMPT_GRAPH_ALGORITHM_VERSION)
    for table in (
        "analytics_prompt_graph_layout",
        "analytics_prompt_graph_community_edges",
        "analytics_prompt_graph_memberships",
        "analytics_prompt_graph_communities",
        "analytics_prompt_graph_nodes",
    ):
        await conn.execute(
            f"""
            delete from {table}
            where model_id = $1::text
              and normalization_version = $2::text
              and algorithm_version = $3::text
            """,
            *args,
        )


async def _insert_nodes(conn: Any, config: PromptGraphConfig) -> str:
    return await conn.execute(
        """
        insert into analytics_prompt_graph_nodes (
            model_id,
            normalization_version,
            algorithm_version,
            prompt_hash,
            task_type,
            prompt,
            node_status,
            has_embedding,
            has_scene,
            has_micro,
            scene_id,
            micro_cluster_id,
            quality_score,
            uses,
            users,
            first_seen,
            last_seen,
            refreshed_at
        )
        select
            $1::text as model_id,
            $2::text as normalization_version,
            $3::text as algorithm_version,
            s.prompt_hash,
            coalesce(e.task_type, s.task_types[1], 'unknown') as task_type,
            coalesce(s.prompt, '') as prompt,
            case
                when e.prompt_hash is null then 'unembedded'
                else 'no_scene'
            end as node_status,
            (e.prompt_hash is not null) as has_embedding,
            false as has_scene,
            (micro.cluster_id is not null) as has_micro,
            null::text as scene_id,
            micro.cluster_id,
            coalesce(s.quality_score, 0),
            coalesce(s.uses, 0),
            coalesce(s.users, 0),
            s.first_seen,
            s.last_seen,
            now()
        from analytics_prompt_slim_candidates s
        left join analytics_prompt_embeddings e
          on e.prompt_hash = s.prompt_hash
         and e.model_id = $1::text
         and e.normalization_version = $2::text
         and e.status = 'embedded'
        left join lateral (
            select m.cluster_id
            from analytics_prompt_similarity_members m
            join analytics_prompt_similarity_clusters c on c.cluster_id = m.cluster_id
            where m.prompt_hash = s.prompt_hash
              and c.model_id = $1::text
              and c.normalization_version = $2::text
            order by m.member_rank, m.cluster_id
            limit 1
        ) micro on true
        where s.quality_stage = 'candidate'
          and s.normalization_version = $2::text
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )


async def _stage_natural_scene_atoms(conn: Any, config: PromptGraphConfig) -> int:
    await conn.execute("drop table if exists pg_temp.prompt_graph_scene_atoms")
    await conn.execute("drop table if exists pg_temp.prompt_graph_node_atoms")
    await conn.execute(
        """
        create temporary table prompt_graph_scene_atoms (
            scene_id text not null,
            task_type text not null,
            atom_kind text not null,
            atom_key text not null,
            member_rank integer not null
        )
        """
    )
    await conn.execute(
        """
        create temporary table prompt_graph_node_atoms as
        select
            prompt_hash,
            task_type,
            micro_cluster_id,
            case
                when micro_cluster_id is not null then 'micro:' || micro_cluster_id
                else 'prompt:' || prompt_hash
            end as atom_id
        from analytics_prompt_graph_nodes
        where model_id = $1::text
          and normalization_version = $2::text
          and algorithm_version = $3::text
          and has_embedding
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    await conn.execute("create index prompt_graph_node_atoms_prompt_idx on prompt_graph_node_atoms(prompt_hash)")
    await conn.execute("create index prompt_graph_node_atoms_task_atom_idx on prompt_graph_node_atoms(task_type, atom_id)")
    await conn.execute("analyze prompt_graph_node_atoms")
    micro_rows = await conn.fetch(
        """
        select distinct task_type, atom_id
        from pg_temp.prompt_graph_node_atoms
        where micro_cluster_id is not null
        order by task_type, atom_id
        """
    )
    edge_rows = await conn.fetch(
        """
        select
            source_atom.task_type,
            least(source_atom.atom_id, target_atom.atom_id) as source_atom_id,
            greatest(source_atom.atom_id, target_atom.atom_id) as target_atom_id,
            e.similarity::float8 as similarity
        from analytics_prompt_similarity_edges e
        join pg_temp.prompt_graph_node_atoms source_atom on source_atom.prompt_hash = e.source_hash
        join pg_temp.prompt_graph_node_atoms target_atom on target_atom.prompt_hash = e.neighbor_hash
        where e.model_id = $1::text
          and e.normalization_version = $2::text
          and e.similarity >= $3::numeric
          and source_atom.task_type = target_atom.task_type
          and source_atom.task_type = e.task_type
          and source_atom.atom_id <> target_atom.atom_id
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        config.natural_scene_min_similarity,
    )
    atom_rows = build_natural_scene_atom_rows(
        [GraphAtom(str(row["task_type"] or "unknown"), str(row["atom_id"])) for row in micro_rows],
        [
            GraphAtomEdge(
                str(row["task_type"] or "unknown"),
                str(row["source_atom_id"]),
                str(row["target_atom_id"]),
                float(row["similarity"] or 0),
            )
            for row in edge_rows
        ],
    )
    if atom_rows:
        await conn.copy_records_to_table(
            "prompt_graph_scene_atoms",
            records=atom_rows,
            columns=["scene_id", "task_type", "atom_kind", "atom_key", "member_rank"],
        )
    return len(atom_rows)


async def _apply_natural_scene_atoms(conn: Any, config: PromptGraphConfig) -> None:
    await conn.execute(
        """
        update analytics_prompt_graph_nodes n
        set
            scene_id = atoms.scene_id,
            has_scene = true,
            node_status = case
                when not n.has_embedding then 'unembedded'
                when n.has_micro then 'clustered'
                else 'singleton'
            end,
            refreshed_at = now()
        from pg_temp.prompt_graph_scene_atoms atoms
        where n.model_id = $1::text
          and n.normalization_version = $2::text
          and n.algorithm_version = $3::text
          and atoms.atom_kind = 'micro'
          and atoms.task_type = n.task_type
          and atoms.atom_key = n.micro_cluster_id
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    await conn.execute(
        """
        update analytics_prompt_graph_nodes n
        set
            scene_id = atoms.scene_id,
            has_scene = true,
            node_status = case
                when not n.has_embedding then 'unembedded'
                when n.has_micro then 'clustered'
                else 'singleton'
            end,
            refreshed_at = now()
        from pg_temp.prompt_graph_scene_atoms atoms
        where n.model_id = $1::text
          and n.normalization_version = $2::text
          and n.algorithm_version = $3::text
          and atoms.atom_kind = 'prompt'
          and atoms.task_type = n.task_type
          and atoms.atom_key = n.prompt_hash
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )


async def _insert_scene_communities(conn: Any, config: PromptGraphConfig) -> None:
    await conn.execute(
        """
        insert into analytics_prompt_graph_communities (
            community_id,
            model_id,
            normalization_version,
            algorithm_version,
            community_type,
            parent_community_id,
            task_type,
            label,
            representative_hash,
            representative_prompt,
            member_count,
            micro_count,
            singleton_count,
            no_scene_count,
            min_similarity,
            avg_similarity,
            max_similarity,
            total_uses,
            total_users,
            quality_score,
            created_at,
            refreshed_at
        )
        with ranked as (
            select
                n.*,
                row_number() over (
                    partition by n.scene_id
                    order by n.quality_score desc, n.uses desc, n.users desc, n.prompt_hash
                ) as representative_rank
            from analytics_prompt_graph_nodes
            n
            where n.model_id = $1::text
              and n.normalization_version = $2::text
              and n.algorithm_version = $3::text
              and n.scene_id is not null
        ),
        scene_stats as (
            select
                scene_id,
                max(task_type) as task_type,
                count(*)::bigint as member_count,
                count(distinct micro_cluster_id) filter (where micro_cluster_id is not null)::bigint as micro_count,
                count(*) filter (where micro_cluster_id is null)::bigint as singleton_count,
                sum(uses)::bigint as total_uses,
                sum(users)::bigint as total_users,
                max(quality_score) as quality_score
            from ranked
            group by scene_id
        )
        select
            stats.scene_id,
            $1::text,
            $2::text,
            $3::text,
            'scene',
            null::text,
            stats.task_type,
            coalesce(rep.prompt, stats.scene_id),
            rep.prompt_hash,
            coalesce(rep.prompt, ''),
            stats.member_count,
            coalesce(stats.micro_count, 0),
            coalesce(stats.singleton_count, 0),
            0,
            null::numeric,
            null::numeric,
            null::numeric,
            stats.total_uses,
            stats.total_users,
            stats.quality_score,
            now(),
            now()
        from scene_stats stats
        left join ranked rep on rep.scene_id = stats.scene_id and rep.representative_rank = 1
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )


async def _insert_tail_communities(conn: Any, config: PromptGraphConfig) -> None:
    await conn.execute(
        """
        insert into analytics_prompt_graph_communities (
            community_id,
            model_id,
            normalization_version,
            algorithm_version,
            community_type,
            parent_community_id,
            task_type,
            label,
            representative_hash,
            representative_prompt,
            member_count,
            micro_count,
            singleton_count,
            no_scene_count,
            total_uses,
            total_users,
            quality_score,
            created_at,
            refreshed_at
        )
        with ranked as (
            select
                n.*,
                row_number() over (
                    partition by n.task_type
                    order by n.quality_score desc, n.uses desc, n.users desc, n.prompt_hash
                ) as representative_rank
            from analytics_prompt_graph_nodes n
            where n.model_id = $1::text
              and n.normalization_version = $2::text
              and n.algorithm_version = $3::text
              and n.node_status = 'no_scene'
        ),
        tail_stats as (
            select
                task_type,
                count(*)::bigint as member_count,
                sum(uses)::bigint as total_uses,
                sum(users)::bigint as total_users,
                max(quality_score) as quality_score
            from ranked
            group by task_type
        )
        select
            'tail-v2:' || md5(stats.task_type),
            $1::text,
            $2::text,
            $3::text,
            'scene',
            null::text,
            stats.task_type,
            stats.task_type || ' 长尾 / 未入场景',
            rep.prompt_hash,
            coalesce(rep.prompt, ''),
            stats.member_count,
            0,
            0,
            stats.member_count,
            stats.total_uses,
            stats.total_users,
            stats.quality_score,
            now(),
            now()
        from tail_stats stats
        left join ranked rep on rep.task_type = stats.task_type and rep.representative_rank = 1
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )


async def _insert_micro_communities(conn: Any, config: PromptGraphConfig) -> None:
    await conn.execute(
        """
        insert into analytics_prompt_graph_communities (
            community_id,
            model_id,
            normalization_version,
            algorithm_version,
            community_type,
            parent_community_id,
            task_type,
            label,
            representative_hash,
            representative_prompt,
            member_count,
            micro_count,
            singleton_count,
            no_scene_count,
            min_similarity,
            avg_similarity,
            max_similarity,
            total_uses,
            total_users,
            quality_score,
            created_at,
            refreshed_at
        )
        with parent_counts as (
            select
                micro_cluster_id as cluster_id,
                scene_id,
                count(*)::bigint as members,
                row_number() over (partition by micro_cluster_id order by count(*) desc, scene_id) as parent_rank
            from analytics_prompt_graph_nodes
            where model_id = $1::text
              and normalization_version = $2::text
              and algorithm_version = $3::text
              and micro_cluster_id is not null
              and scene_id is not null
            group by micro_cluster_id, scene_id
        )
        select
            'micro-v2:' || c.cluster_id,
            $1::text,
            $2::text,
            $3::text,
            'micro',
            parent.scene_id,
            c.task_type,
            c.representative_prompt,
            c.representative_hash,
            c.representative_prompt,
            c.member_count,
            0,
            0,
            0,
            c.min_similarity,
            c.avg_similarity,
            c.max_similarity,
            c.total_uses,
            c.total_users,
            c.quality_score,
            now(),
            now()
        from analytics_prompt_similarity_clusters c
        left join parent_counts parent on parent.cluster_id = c.cluster_id and parent.parent_rank = 1
        where c.model_id = $1::text
          and c.normalization_version = $2::text
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )


async def _insert_task_communities(conn: Any, config: PromptGraphConfig) -> None:
    await conn.execute(
        """
        insert into analytics_prompt_graph_communities (
            community_id,
            model_id,
            normalization_version,
            algorithm_version,
            community_type,
            task_type,
            label,
            member_count,
            micro_count,
            singleton_count,
            no_scene_count,
            total_uses,
            total_users,
            quality_score,
            created_at,
            refreshed_at
        )
        select
            'task-v2:' || md5(task_type),
            $1::text,
            $2::text,
            $3::text,
            'task',
            task_type,
            task_type,
            count(*)::bigint,
            count(distinct micro_cluster_id) filter (where micro_cluster_id is not null)::bigint,
            count(*) filter (where node_status = 'singleton')::bigint,
            count(*) filter (where node_status = 'no_scene')::bigint,
            sum(uses)::bigint,
            sum(users)::bigint,
            max(quality_score),
            now(),
            now()
        from analytics_prompt_graph_nodes
        where model_id = $1::text
          and normalization_version = $2::text
          and algorithm_version = $3::text
        group by task_type
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )


async def _insert_memberships(conn: Any, config: PromptGraphConfig) -> None:
    await conn.execute(
        """
        insert into analytics_prompt_graph_memberships (
            community_id,
            prompt_hash,
            model_id,
            normalization_version,
            algorithm_version,
            membership_type,
            task_type,
            confidence,
            confidence_band,
            member_rank,
            created_at
        )
        select
            n.scene_id,
            n.prompt_hash,
            $1::text,
            $2::text,
            $3::text,
            'scene',
            n.task_type,
            null::numeric,
            'unknown',
            row_number() over (
                partition by n.scene_id
                order by n.quality_score desc, n.uses desc, n.users desc, n.prompt_hash
            )::int,
            now()
        from analytics_prompt_graph_nodes n
        where n.model_id = $1::text
          and n.normalization_version = $2::text
          and n.algorithm_version = $3::text
          and n.scene_id is not null
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    await conn.execute(
        """
        insert into analytics_prompt_graph_memberships (
            community_id,
            prompt_hash,
            model_id,
            normalization_version,
            algorithm_version,
            membership_type,
            task_type,
            confidence,
            confidence_band,
            member_rank,
            created_at
        )
        select
            'tail-v2:' || md5(n.task_type),
            n.prompt_hash,
            $1::text,
            $2::text,
            $3::text,
            'scene',
            n.task_type,
            null::numeric,
            'unknown',
            row_number() over (
                partition by n.task_type
                order by n.quality_score desc, n.uses desc, n.users desc, n.prompt_hash
            )::int,
            now()
        from analytics_prompt_graph_nodes n
        where n.model_id = $1::text
          and n.normalization_version = $2::text
          and n.algorithm_version = $3::text
          and n.node_status = 'no_scene'
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    await conn.execute(
        """
        insert into analytics_prompt_graph_memberships (
            community_id,
            prompt_hash,
            model_id,
            normalization_version,
            algorithm_version,
            membership_type,
            task_type,
            confidence,
            confidence_band,
            member_rank,
            created_at
        )
        select
            'micro-v2:' || m.cluster_id,
            m.prompt_hash,
            $1::text,
            $2::text,
            $3::text,
            'micro',
            m.task_type,
            m.similarity_to_representative,
            case
                when m.similarity_to_representative >= 0.92 then 'high'
                when m.similarity_to_representative >= 0.86 then 'medium'
                else 'low'
            end,
            m.member_rank,
            now()
        from analytics_prompt_similarity_members m
        join analytics_prompt_similarity_clusters c on c.cluster_id = m.cluster_id
        where c.model_id = $1::text
          and c.normalization_version = $2::text
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )


async def _insert_similarity_edges(conn: Any, config: PromptGraphConfig) -> None:
    await conn.execute(
        """
        insert into analytics_prompt_graph_community_edges (
            model_id,
            normalization_version,
            algorithm_version,
            source_community_id,
            target_community_id,
            edge_type,
            source_task_type,
            target_task_type,
            weight,
            prompt_edge_count,
            duplicate_edge_count,
            similar_edge_count,
            avg_similarity,
            max_similarity,
            created_at
        )
        with mapped as (
            select
                least(source_node.scene_id, target_node.scene_id) as source_community_id,
                greatest(source_node.scene_id, target_node.scene_id) as target_community_id,
                source_node.task_type,
                e.similarity::float8 as similarity,
                e.band
            from analytics_prompt_similarity_edges e
            join analytics_prompt_graph_nodes source_node
              on source_node.prompt_hash = e.source_hash
             and source_node.model_id = $1::text
             and source_node.normalization_version = $2::text
             and source_node.algorithm_version = $3::text
            join analytics_prompt_graph_nodes target_node
              on target_node.prompt_hash = e.neighbor_hash
             and target_node.model_id = $1::text
             and target_node.normalization_version = $2::text
             and target_node.algorithm_version = $3::text
            where e.model_id = $1::text
              and e.normalization_version = $2::text
              and source_node.scene_id is not null
              and target_node.scene_id is not null
              and source_node.scene_id <> target_node.scene_id
              and source_node.task_type = target_node.task_type
              and source_node.task_type = e.task_type
        )
        select
            $1::text,
            $2::text,
            $3::text,
            m.source_community_id,
            m.target_community_id,
            'similarity',
            m.task_type,
            m.task_type,
            round(max(m.similarity)::numeric, 6),
            count(*)::bigint,
            count(*) filter (where m.band = 'duplicate')::bigint,
            count(*) filter (where m.band = 'similar')::bigint,
            round(avg(m.similarity)::numeric, 6),
            round(max(m.similarity)::numeric, 6),
            now()
        from mapped m
        group by m.source_community_id, m.target_community_id, m.task_type
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    await conn.execute(
        """
        insert into analytics_prompt_graph_community_edges (
            model_id,
            normalization_version,
            algorithm_version,
            source_community_id,
            target_community_id,
            edge_type,
            source_task_type,
            target_task_type,
            weight,
            prompt_edge_count,
            duplicate_edge_count,
            similar_edge_count,
            avg_similarity,
            max_similarity,
            created_at
        )
        select
            $1::text,
            $2::text,
            $3::text,
            child.parent_community_id,
            child.community_id,
            'scene_micro',
            coalesce(parent.task_type, 'unknown'),
            child.task_type,
            coalesce(child.avg_similarity, 0),
            child.member_count,
            0,
            0,
            child.avg_similarity,
            child.max_similarity,
            now()
        from analytics_prompt_graph_communities child
        join analytics_prompt_graph_communities parent
          on parent.community_id = child.parent_community_id
         and parent.task_type = child.task_type
        where child.model_id = $1::text
          and child.normalization_version = $2::text
          and child.algorithm_version = $3::text
          and child.community_type = 'micro'
          and child.parent_community_id is not null
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )


async def _fetch_graph_scenes(conn: Any, config: PromptGraphConfig) -> list[GraphScene]:
    rows = await conn.fetch(
        """
        select
            c.community_id,
            c.task_type,
            c.member_count,
            e.embedding_dim,
            e.embedding_f16
        from analytics_prompt_graph_communities c
        join analytics_prompt_embeddings e
          on e.prompt_hash = c.representative_hash
         and e.model_id = c.model_id
         and e.normalization_version = c.normalization_version
         and e.status = 'embedded'
        where c.model_id = $1::text
          and c.normalization_version = $2::text
          and c.algorithm_version = $3::text
          and c.community_type = 'scene'
        order by c.task_type, c.member_count desc, c.community_id
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    return [
        GraphScene(
            scene_id=str(row["community_id"]),
            task_type=str(row["task_type"] or "unknown"),
            member_count=int(row["member_count"] or 0),
            centroid=embedding_from_bytes(row["embedding_f16"], int(row["embedding_dim"])),
        )
        for row in rows
        if row["embedding_f16"] is not None and row["embedding_dim"] is not None
    ]


async def _insert_layout(conn: Any, config: PromptGraphConfig, scenes: list[GraphScene]) -> None:
    scene_rows = build_scene_layout_rows(config.model_id, PROMPT_NORMALIZATION_VERSION, scenes)
    if scene_rows:
        await conn.executemany(
            """
            insert into analytics_prompt_graph_layout (
                model_id,
                normalization_version,
                algorithm_version,
                community_type,
                community_id,
                layout_algorithm,
                x,
                y,
                radius,
                refreshed_at
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
            on conflict (model_id, normalization_version, algorithm_version, community_id, layout_algorithm) do update set
                community_type = excluded.community_type,
                x = excluded.x,
                y = excluded.y,
                radius = excluded.radius,
                refreshed_at = now()
            """,
            scene_rows,
        )
    parent_layout = {str(row[4]): (float(row[6]), float(row[7])) for row in scene_rows}
    micro_rows = [
        dict(row)
        for row in await conn.fetch(
            """
            select community_id, community_type, parent_community_id, member_count
            from analytics_prompt_graph_communities
            where model_id = $1::text
              and normalization_version = $2::text
              and algorithm_version = $3::text
              and community_type = 'micro'
              and parent_community_id is not null
            """,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_GRAPH_ALGORITHM_VERSION,
        )
    ]
    child_rows = build_child_layout_rows(config.model_id, PROMPT_NORMALIZATION_VERSION, micro_rows, parent_layout)
    if child_rows:
        await conn.executemany(
            """
            insert into analytics_prompt_graph_layout (
                model_id,
                normalization_version,
                algorithm_version,
                community_type,
                community_id,
                layout_algorithm,
                x,
                y,
                radius,
                refreshed_at
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
            on conflict (model_id, normalization_version, algorithm_version, community_id, layout_algorithm) do update set
                community_type = excluded.community_type,
                x = excluded.x,
                y = excluded.y,
                radius = excluded.radius,
                refreshed_at = now()
            """,
            child_rows,
        )


async def _graph_summary(conn: Any, config: PromptGraphConfig) -> dict[str, int]:
    row = await conn.fetchrow(
        """
        select
            (select count(*)::bigint from analytics_prompt_slim_candidates where quality_stage = 'candidate' and normalization_version = $2::text) as candidate_count,
            (select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text) as node_count,
            (select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and has_embedding) as embedded_count,
            (select count(*)::bigint from analytics_prompt_graph_communities where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and community_type = 'scene') as scene_count,
            (select count(*)::bigint from analytics_prompt_graph_communities where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and community_type = 'micro') as micro_count,
            (select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and node_status = 'singleton') as singleton_count,
            (select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and node_status = 'no_scene') as no_scene_count,
            (select count(*)::bigint from analytics_prompt_graph_community_edges where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text) as edge_count,
            0::bigint as centroid_bridge_count
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    return {key: int(row[key] or 0) for key in row.keys()}


async def refresh_prompt_graph(conn: Any, config: PromptGraphConfig) -> dict[str, Any]:
    await ensure_prompt_graph_schema(conn)
    started = time.monotonic()
    await set_graph_state(
        conn,
        config.model_id,
        {
            "model_id": config.model_id,
            "model_key": config.model_key,
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
            "algorithm_version": PROMPT_GRAPH_ALGORITHM_VERSION,
            "layout_algorithm": PROMPT_GRAPH_LAYOUT_ALGORITHM,
            "natural_scene_min_similarity": config.natural_scene_min_similarity,
            "duplicate_threshold": DEFAULT_DUPLICATE_THRESHOLD,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await _clear_graph(conn, config)
    await _insert_nodes(conn, config)
    natural_scene_atom_count = await _stage_natural_scene_atoms(conn, config)
    await _apply_natural_scene_atoms(conn, config)
    await _insert_scene_communities(conn, config)
    await _insert_tail_communities(conn, config)
    await _insert_micro_communities(conn, config)
    await _insert_task_communities(conn, config)
    await _insert_memberships(conn, config)
    await _insert_similarity_edges(conn, config)
    scenes = await _fetch_graph_scenes(conn, config)
    await _insert_layout(conn, config, scenes)
    summary = await _graph_summary(conn, config)
    seconds = round(time.monotonic() - started, 2)
    await set_graph_state(
        conn,
        config.model_id,
        {
            **summary,
            "natural_scene_atom_count": natural_scene_atom_count,
            "last_success_at": datetime.now(timezone.utc).isoformat(),
            "seconds": seconds,
        },
    )
    return {
        "model_id": config.model_id,
        "normalization_version": PROMPT_NORMALIZATION_VERSION,
        "algorithm_version": PROMPT_GRAPH_ALGORITHM_VERSION,
        "natural_scene_atom_count": natural_scene_atom_count,
        **summary,
        "seconds": seconds,
    }


def prompt_graph_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh prompt semantic graph projection from existing analytics tables.")
    parser.add_argument("--model-id", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_ID", DEFAULT_VECTOR_MODEL_ID))
    parser.add_argument("--model-key", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_KEY", DEFAULT_VECTOR_MODEL_KEY))
    parser.add_argument("--natural-scene-min-similarity", type=float, default=DEFAULT_NATURAL_SCENE_MIN_SIMILARITY)
    parser.add_argument("--statement-timeout-ms", type=int, default=3_600_000)
    return parser


def config_from_args(args: argparse.Namespace) -> PromptGraphConfig:
    return PromptGraphConfig(
        model_id=args.model_id,
        model_key=args.model_key,
        natural_scene_min_similarity=float(args.natural_scene_min_similarity),
    )


async def _run() -> None:
    from .main import _database_url

    parser = prompt_graph_arg_parser()
    args = parser.parse_args()
    conn = await asyncpg.connect(dsn=_database_url())
    try:
        await conn.execute(f"set statement_timeout = {int(args.statement_timeout_ms)}")
        status = await refresh_prompt_graph(conn, config_from_args(args))
        print(json.dumps(status, ensure_ascii=False, default=str, sort_keys=True))
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
