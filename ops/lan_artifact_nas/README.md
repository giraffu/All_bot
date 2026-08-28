# LAN artifact stores on NAS

This directory owns the stable deployment contract for moving the LAN OCI
registry, LAN model-cache MinIO, and model source registry to NAS Btrfs. It does
not move Docker's data root, active databases, container volumes, or GPU model
workspaces.

## Stable topology

- NAS-local Docker stores Registry v2 data in
  `/volume1/AllBotInfra/docker-registry` and model-cache MinIO data in
  `/volume1/AllBotInfra/model-cache-lan`.
- NAS exports only `/volume1/AllBotInfra/model-registry` to the dedicated main
  server address `10.250.150.1`.
- The main server preserves `127.0.0.1/192.168.1.115:5000` and `:9010` with
  socket-activated TCP proxies to the NAS direct-link backends.
- The compatibility `.socket` units start directly from `sockets.target` and use
  `FreeBind=true`; they must not order themselves after `network-online.target`,
  which would create a boot ordering cycle. Network readiness belongs to the
  triggered proxy `.service` units.
- GPU nodes keep their local exact-digest images and verified model workspaces.
  NAS loss blocks new pulls, warm-cache and profile changes, but does not make a
  healthy current runtime read models over NFS.
- `AllBotInfra` is separate from `AllBotArchive`; credentials, buckets,
  snapshots and lifecycle policies are never shared.

## Migration transaction

1. Record local disk usage, model-cache object count/bytes/manifests, Registry
   catalog/tag/digests, model source tree size, fleet status and unfinished
   operations. Stop if catalog, ledger and live state drift.
2. Offline-import exact Registry/MinIO/MC image identities to NAS. Create the
   three Btrfs subvolumes and private `.env`, then run `preflight.sh` and
   `bootstrap.sh` with their exact confirmations.
3. Install and start the temporary migration-source socket on the main server.
   Run `mirror-model-cache.sh` on NAS. It never uses `--remove`; execute succeeds
   only when `mc diff` is empty.
4. Pre-copy model source and Registry filesystem trees with `rsync -aH` over the
   dedicated link. A final quiesced Registry delta must make `rsync --dry-run
   --delete --itemize-changes` empty. Run `verify-registry.sh` before cutover.
5. Wait for model upload/build/push operations to stop. Stop only the two old
   central store containers, start the compatibility proxy sockets, and verify
   the established endpoints. Do not drain or restart GPU runtimes.
6. Move the local model source directory to an exact rollback path, install the
   managed `model-registry.fstab` entry, mount the dedicated NFSv4 `fsid=0`
   export at the original path, and
   verify the complete source tree and model import dry-run.
7. Pull a pinned Registry manifest and run one existing-slot model-cache
   preflight through the fleet helper. Verify current image/profile identities
   and Central/ComfyUI health remain unchanged.
8. Create a readonly NAS snapshot. Only after all checks pass may the exact old
   local store directories be retired. Before retirement, rollback stops proxy
   sockets, unmounts NFS, restores the exact local source path and recreates the
   original two Compose services. Retirement closes that fast rollback path:
   afterwards recovery is NAS-first, and any local re-materialization is a new
   controlled copy/probe/switch from the NAS service or readonly snapshot.

## Steady-state observation and recovery

- Read overall capacity from `df`/`btrfs filesystem usage`, then classify
  `model-registry`, `model-cache-lan` and `docker-registry` separately. Current
  bytes, object counts and snapshot counts are runtime evidence and never Git
  facts.
- Use `btrfs filesystem du -s` to distinguish `Exclusive` from `Set shared`.
  Do not add an active subvolume and its readonly snapshot as independent
  physical usage, and do not mistake allocated data-chunk utilization for the
  whole-volume percentage.
- `AllBotInfra` artifact capacity is separate from permanent media in
  `AllBotArchive`. Model source is protected by its readonly snapshot;
  Registry and model-cache data remain rebuildable stores with independent
  lifecycle policy.
- Verify both NAS backends, both established main-server endpoints, the NFSv4
  source/mount options and an exact Registry manifest/model-cache preflight.
  Observe GPU current/queue state without draining or restarting healthy
  runtimes.
- After installing proxy unit changes, run `systemctl daemon-reload`, restart only
  the two compatibility socket units, and verify they remain enabled and active.
  A real host reboot is a separate maintenance-window check; journal evidence must
  show both sockets joined the boot transaction without an ordering cycle.
- After local retirement, never promise an instant local rollback. A NAS
  outage is recovered in place or from the readonly snapshot; rebuilding local
  stores requires a newly scoped migration with its own capacity check,
  consistency proof and cutover authorization.

Repository files never contain the private `.env`, NAS sudo password or model
credentials. Runtime evidence belongs in `logs/` and is not committed.
