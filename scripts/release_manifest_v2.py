#!/usr/bin/env python3
"""Validation and selection primitives for AllBot release schema v2.

The artifact manifests are deliberately environment-neutral.  Runtime plans
select a track and a subset of artifacts; credentials and test/prod settings
remain outside this bundle.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


TRACKS = ("control-plane", "test-execution", "gpu-execution")
RELEASE_CHANNEL_REFS = {
    "main": "refs/heads/main",
    "test-candidate": "refs/heads/codex/test-train",
}
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DIGEST_REF_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
CHECKSUM_RE = re.compile(r"^[0-9a-f]{64}$")


class ManifestV2Error(RuntimeError):
    """A release bundle violates the immutable artifact contract."""


class LoadedRelease:
    def __init__(
        self, *, index_path: Path, index: dict[str, Any], manifests: dict[str, dict[str, Any]]
    ) -> None:
        self.index_path = index_path
        self.index = index
        self.manifests = manifests


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestV2Error(f"invalid release JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ManifestV2Error(f"release JSON must be an object: {path.name}")
    return value


def _validate_sha(value: Any, *, field: str) -> str:
    text = str(value)
    if not FULL_SHA_RE.fullmatch(text):
        raise ManifestV2Error(f"{field} must be a full Git SHA")
    return text


def _validate_common_artifact(
    name: str,
    artifact: Mapping[str, Any],
    *,
    source_sha: str,
    track: str,
    require_source: bool = True,
) -> None:
    if require_source:
        _validate_sha(artifact.get("source_sha"), field=f"{track}/{name} source_sha")
    closure = artifact.get("dependency_closure")
    if not isinstance(closure, list) or not all(isinstance(item, str) for item in closure):
        raise ManifestV2Error(f"{track}/{name} dependency_closure must be a string list")
    if any("/" in item or ":" in item for item in closure):
        raise ManifestV2Error(f"{track}/{name} has a cross-track dependency reference")


def _validate_image(name: str, artifact: Mapping[str, Any], *, track: str) -> None:
    ref = str(artifact.get("ref", ""))
    digest = str(artifact.get("digest", ""))
    if not DIGEST_REF_RE.fullmatch(ref):
        raise ManifestV2Error(f"{track}/{name} image ref must be digest-pinned")
    if not DIGEST_RE.fullmatch(digest) or not ref.endswith("@" + digest):
        raise ManifestV2Error(f"{track}/{name} digest does not match image ref")
    if not FULL_SHA_RE.fullmatch(str(artifact.get("oci_revision", ""))):
        raise ManifestV2Error(f"{track}/{name} oci_revision is invalid")
    if artifact.get("oci_revision") != artifact.get("source_sha"):
        raise ManifestV2Error(f"{track}/{name} OCI revision must match artifact source_sha")
    base = artifact.get("base_image_digest")
    if base is not None and not DIGEST_RE.fullmatch(str(base)):
        raise ManifestV2Error(f"{track}/{name} base_image_digest is invalid")


def _validate_gpu_profile(name: str, artifact: Mapping[str, Any]) -> None:
    required = (
        "task_types",
        "baked_agent_revision",
        "baked_workflow_revision",
        "model_manifest",
        "target_gpu",
        "startup_args",
    )
    for field in required:
        if field not in artifact:
            raise ManifestV2Error(f"gpu-execution/{name} requires {field}")
    if not artifact["task_types"] or not all(
        isinstance(value, str) for value in artifact["task_types"]
    ):
        raise ManifestV2Error(f"gpu-execution/{name} task_types are invalid")
    for field in ("baked_agent_revision", "baked_workflow_revision"):
        _validate_sha(artifact[field], field=f"gpu-execution/{name} {field}")
    model = artifact["model_manifest"]
    if (
        not isinstance(model, Mapping)
        or not str(model.get("key", ""))
        or not isinstance(model.get("size"), int)
        or model["size"] <= 0
        or not CHECKSUM_RE.fullmatch(str(model.get("sha256", "")))
    ):
        raise ManifestV2Error(f"gpu-execution/{name} model_manifest is invalid")
    if not isinstance(artifact["target_gpu"], list) or not artifact["target_gpu"]:
        raise ManifestV2Error(f"gpu-execution/{name} target_gpu is invalid")
    if not isinstance(artifact["startup_args"], list):
        raise ManifestV2Error(f"gpu-execution/{name} startup_args is invalid")
    # Bundles produced before risk-based release gates had no explicit level;
    # they were only publishable after the full business canary, so preserve
    # that stronger interpretation for compatibility.
    validation_level = str(artifact.get("validation_level", "canary-verified"))
    attestation = str(artifact.get("artifact_attestation", "verified"))
    canary = str(artifact.get("canary_evidence", "verified"))
    if validation_level not in {"attested", "canary-verified"}:
        raise ManifestV2Error(f"gpu-execution/{name} validation_level is invalid")
    if attestation != "verified":
        raise ManifestV2Error(
            f"gpu-execution/{name} artifact_attestation must be verified"
        )
    expected_canary = "waived" if validation_level == "attested" else "verified"
    if canary != expected_canary:
        raise ManifestV2Error(
            f"gpu-execution/{name} canary_evidence does not match validation_level"
        )


def _validate_manifest(
    manifest: Mapping[str, Any], *, track: str, expected_sha: str
) -> None:
    if manifest.get("schema_version") != 2:
        raise ManifestV2Error(f"{track} manifest schema_version must be 2")
    if manifest.get("track") != track:
        raise ManifestV2Error(f"{track} manifest track mismatch")
    if "environment" in manifest:
        raise ManifestV2Error(f"{track} manifest must be environment-neutral")
    if manifest.get("source_sha") != expected_sha:
        raise ManifestV2Error(f"{track} manifest source_sha mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ManifestV2Error(f"{track} manifest has no artifacts")
    if track == "gpu-execution":
        completeness = manifest.get("completeness", "complete")
        missing = manifest.get("missing_artifacts", [])
        if completeness not in {"complete", "incomplete"}:
            raise ManifestV2Error("gpu-execution completeness is invalid")
        if (
            not isinstance(missing, list)
            or not all(isinstance(name, str) and name for name in missing)
            or len(missing) != len(set(missing))
        ):
            raise ManifestV2Error("gpu-execution missing_artifacts is invalid")
        if set(missing) & set(artifacts):
            raise ManifestV2Error("gpu-execution available and missing artifacts overlap")
        if completeness == "complete" and missing:
            raise ManifestV2Error("complete gpu-execution manifest lists missing artifacts")
        if completeness == "incomplete" and not missing:
            raise ManifestV2Error("incomplete gpu-execution manifest must list missing artifacts")
        if not artifacts and completeness != "incomplete":
            raise ManifestV2Error("gpu-execution manifest has no artifacts")
    elif not artifacts:
        raise ManifestV2Error(f"{track} manifest has no artifacts")
    for name, raw_artifact in artifacts.items():
        if not isinstance(raw_artifact, Mapping):
            raise ManifestV2Error(f"{track}/{name} artifact must be an object")
        artifact = raw_artifact
        kind = artifact.get("kind")
        _validate_common_artifact(
            name,
            artifact,
            source_sha=expected_sha,
            track=track,
            require_source=kind != "external-image",
        )
        if kind == "image":
            _validate_image(name, artifact, track=track)
        elif kind == "external-image":
            ref = str(artifact.get("ref", ""))
            digest = str(artifact.get("digest", ""))
            if not DIGEST_REF_RE.fullmatch(ref) or not ref.endswith("@" + digest):
                raise ManifestV2Error(f"{track}/{name} external image must be digest-pinned")
        elif kind == "tar":
            if not CHECKSUM_RE.fullmatch(str(artifact.get("sha256", ""))):
                raise ManifestV2Error(f"{track}/{name} tar sha256 is invalid")
        else:
            raise ManifestV2Error(f"{track}/{name} kind must be image, external-image, or tar")
        if track == "gpu-execution":
            if kind != "image":
                raise ManifestV2Error(f"gpu-execution/{name} must be an image")
            _validate_gpu_profile(name, artifact)


def load_release_index(path: Path, *, expected_sha: str) -> LoadedRelease:
    expected_sha = _validate_sha(expected_sha, field="expected_sha")
    path = path.resolve()
    index = _read_object(path)
    if index.get("schema_version") != 2:
        raise ManifestV2Error("release index schema_version must be 2")
    if "environment" in index:
        raise ManifestV2Error("release index must be environment-neutral")
    if index.get("source_sha") != expected_sha:
        raise ManifestV2Error("release index source_sha mismatch")
    if not str(index.get("ci_run", "")).startswith("https://github.com/"):
        raise ManifestV2Error("release index ci_run is invalid")
    release_channel = str(index.get("release_channel", "main"))
    source_ref = str(
        index.get("source_ref", RELEASE_CHANNEL_REFS.get(release_channel, ""))
    )
    if release_channel not in RELEASE_CHANNEL_REFS:
        raise ManifestV2Error("release index release_channel is invalid")
    if source_ref != RELEASE_CHANNEL_REFS[release_channel]:
        raise ManifestV2Error("release index source_ref does not match release_channel")
    validation = index.get("validation", {"mode": "full", "tests": "passed"})
    if not isinstance(validation, Mapping):
        raise ManifestV2Error("release index validation metadata is invalid")
    validation_mode = str(validation.get("mode", ""))
    validation_tests = str(validation.get("tests", ""))
    expected_tests = {
        "full": "passed",
        "build-only": "skipped",
        "promoted": "candidate-passed",
    }
    if expected_tests.get(validation_mode) != validation_tests:
        raise ManifestV2Error("release index validation metadata is inconsistent")
    promotion = index.get("promotion")
    if validation_mode == "promoted":
        if release_channel != "main" or not isinstance(promotion, Mapping):
            raise ManifestV2Error("promoted release requires main-channel promotion metadata")
        candidate_sha = _validate_sha(
            promotion.get("candidate_sha"), field="promotion candidate_sha"
        )
        bundle_digest = str(promotion.get("candidate_bundle_digest", ""))
        if not DIGEST_RE.fullmatch(bundle_digest):
            raise ManifestV2Error("promotion candidate bundle digest is invalid")
        if (
            promotion.get("mode") != "candidate-digest-reuse"
            or promotion.get("tree_equivalent") is not True
        ):
            raise ManifestV2Error("promotion mode or tree equivalence is invalid")
        approval_relative = Path(str(promotion.get("approval_path", "")))
        if (
            not approval_relative.name
            or approval_relative.is_absolute()
            or ".." in approval_relative.parts
        ):
            raise ManifestV2Error("promotion approval path is unsafe")
        approval_path = path.parent / approval_relative
        try:
            approval_bytes = approval_path.read_bytes()
        except OSError as exc:
            raise ManifestV2Error("promotion approval is unavailable") from exc
        if hashlib.sha256(approval_bytes).hexdigest() != str(
            promotion.get("approval_sha256", "")
        ):
            raise ManifestV2Error("promotion approval checksum does not match")
        approval = _read_object(approval_path)
        if (
            approval.get("schema_version") != 1
            or approval.get("status") != "approved"
            or approval.get("candidate_sha") != candidate_sha
            or approval.get("candidate_bundle_digest") != bundle_digest
        ):
            raise ManifestV2Error("promotion approval identity is invalid")
        approval_artifacts = approval.get("artifacts")
        if not isinstance(approval_artifacts, Mapping):
            raise ManifestV2Error("promotion approval artifacts are invalid")
        for name, artifact in approval_artifacts.items():
            if not isinstance(artifact, Mapping):
                raise ManifestV2Error(f"promotion approval artifact is invalid: {name}")
            digest = str(artifact.get("digest", ""))
            if not (DIGEST_RE.fullmatch(digest) or CHECKSUM_RE.fullmatch(digest)):
                raise ManifestV2Error(f"promotion approval digest is invalid: {name}")
            _validate_sha(
                artifact.get("source_sha"),
                field=f"promotion approval {name} source_sha",
            )
            if artifact.get("status") not in {"verified", "approved-direct"}:
                raise ManifestV2Error(f"promotion approval status is invalid: {name}")
        index = dict(index)
        index["promotion_approval"] = approval
    elif promotion is not None:
        raise ManifestV2Error("non-promoted release cannot contain promotion metadata")
    index = dict(index)
    index["release_channel"] = release_channel
    index["source_ref"] = source_ref
    index["validation"] = {
        "mode": validation_mode,
        "tests": validation_tests,
    }
    references = index.get("manifests")
    if not isinstance(references, Mapping) or set(references) != set(TRACKS):
        raise ManifestV2Error("release index must reference exactly the three release tracks")
    manifests: dict[str, dict[str, Any]] = {}
    for track in TRACKS:
        relative = Path(str(references[track]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ManifestV2Error(f"unsafe {track} manifest reference")
        manifest = _read_object(path.parent / relative)
        _validate_manifest(manifest, track=track, expected_sha=expected_sha)
        manifests[track] = manifest

    image_digests = {
        str(artifact["digest"])
        for manifest in manifests.values()
        for artifact in manifest["artifacts"].values()
        if artifact.get("kind") in {"image", "external-image"}
    }
    for track, manifest in manifests.items():
        for name, artifact in manifest["artifacts"].items():
            base = artifact.get("base_image_digest")
            if base is not None and base not in image_digests:
                raise ManifestV2Error(f"{track}/{name} references an unknown base digest")
    return LoadedRelease(index_path=path, index=index, manifests=manifests)


def select_artifacts(
    release: LoadedRelease, track: str, requested: Iterable[str]
) -> dict[str, dict[str, Any]]:
    if track not in TRACKS:
        raise ManifestV2Error(f"unknown release track: {track}")
    artifacts = release.manifests[track]["artifacts"]
    if not artifacts:
        raise ManifestV2Error(f"{track} track has no available artifacts")
    names = list(dict.fromkeys(requested))
    if not names:
        return dict(artifacts)
    missing = sorted(set(names) - set(artifacts))
    if missing:
        raise ManifestV2Error(f"unknown {track} artifacts: {', '.join(missing)}")
    selected = set(names)
    pending = list(names)
    while pending:
        name = pending.pop()
        for dependency in artifacts[name].get("dependency_closure", []):
            if dependency not in artifacts:
                raise ManifestV2Error(f"{track}/{name} has an unknown dependency: {dependency}")
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    return {name: artifacts[name] for name in artifacts if name in selected}


def validate_promotion(
    track: str,
    selected: Mapping[str, Mapping[str, Any]],
    verified_record: Mapping[str, Any],
) -> None:
    if verified_record.get("track") != track:
        raise ManifestV2Error(f"verified record track does not match {track}")
    verified = verified_record.get("artifacts")
    if not isinstance(verified, Mapping):
        raise ManifestV2Error("verified record has no artifacts")
    for name, artifact in selected.items():
        evidence = verified.get(name)
        expected = artifact.get("digest") or artifact.get("sha256")
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("status") != "verified"
            or evidence.get("digest") != expected
        ):
            raise ManifestV2Error(f"{name} was not verified with the promoted digest")


def expand_base_rebuilds(
    catalog: Mapping[str, Mapping[str, Any]], changed: Iterable[str]
) -> set[str]:
    selected = set(changed)
    unknown = selected - set(catalog)
    if unknown:
        raise ManifestV2Error("unknown build artifacts: " + ", ".join(sorted(unknown)))
    added = True
    while added:
        added = False
        for name, metadata in catalog.items():
            if name not in selected and metadata.get("base") in selected:
                selected.add(name)
                added = True
    return selected
