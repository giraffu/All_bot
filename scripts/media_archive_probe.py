#!/usr/bin/env python3
"""Probe every registered historical source and record auditable attempts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncpg
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from scripts.media_archive_worker import (
    clear_proxy_environment,
    validate_direct_route,
    _candidate_keys,
)


def s3_client(source):
    return boto3.client(
        "s3",
        endpoint_url=source["endpoint"],
        aws_access_key_id=source["access_key"],
        aws_secret_access_key=source["secret_key"],
        region_name=source.get("region", "auto"),
        verify=source.get("ca_file", True),
        config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 1},
        ),
    )


def probe_s3(asset, source):
    client = s3_client(source)
    attempts = []
    for key in _candidate_keys(asset["original_ref"], asset["task_id"]):
        try:
            head = client.head_object(Bucket=source["bucket"], Key=key)
            attempts.append(
                (
                    source["name"],
                    key,
                    "found",
                    None,
                    json.dumps(
                        {"size": head.get("ContentLength"), "etag": head.get("ETag")}
                    ),
                )
            )
            return attempts
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                attempts.append((source["name"], key, "not_found", code, None))
                continue
            attempts.append(
                (
                    source["name"],
                    key,
                    "error",
                    code or type(exc).__name__,
                    str(exc)[:500],
                )
            )
            return attempts
        except (EndpointConnectionError, BotoCoreError, OSError) as exc:
            attempts.append(
                (
                    source["name"],
                    key,
                    "source_offline",
                    type(exc).__name__,
                    str(exc)[:500],
                )
            )
            return attempts
    return attempts


def probe_filesystem(asset, source):
    attempts = []
    for root_value in source.get("roots", []):
        root = Path(root_value).resolve()
        for key in _candidate_keys(asset["original_ref"], asset["task_id"]):
            candidate = (root / key).resolve()
            if root not in candidate.parents and candidate != root:
                continue
            status = "found" if candidate.is_file() else "not_found"
            detail = (
                json.dumps({"size": candidate.stat().st_size})
                if status == "found"
                else None
            )
            attempts.append((source["name"], str(candidate), status, None, detail))
            if status == "found":
                return attempts
    if not source.get("roots"):
        attempts.append(
            (
                source["name"],
                "(no roots configured)",
                "source_offline",
                "NOT_CONFIGURED",
                None,
            )
        )
    return attempts


async def run(args) -> None:
    clear_proxy_environment()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    sources = config["sources"]
    for source in sources:
        if source.get("type", "s3") == "s3":
            validate_direct_route(urlparse(source["endpoint"]).hostname)
    db_url = os.getenv("LOCAL_ANALYTICS_DATABASE_URL", "").replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )
    if not db_url:
        raise SystemExit("LOCAL_ANALYTICS_DATABASE_URL is required")
    conn = await asyncpg.connect(db_url)
    run_id = uuid.uuid4()
    try:
        registered = {
            row["source"]
            for row in await conn.fetch(
                "select source from analytics_media_sources where enabled"
            )
        }
        configured = {source["name"] for source in sources}
        unknown = configured - registered
        if unknown:
            raise RuntimeError(
                f"sources are not registered in analytics_media_sources: {sorted(unknown)}"
            )
        await conn.execute(
            "insert into analytics_media_runs(id,run_type,status,cursor) values($1,'probe','running',jsonb_build_object('start',$2,'end',$3))",
            run_id,
            args.start_id,
            args.end_id,
        )
        assets = await conn.fetch(
            """select id,task_id,original_ref from analytics_media_asset_catalog
               where history_id between $1 and $2 and status not in ('archived_verified','external_unmanaged')
               order by history_id,role,ordinal limit $3""",
            args.start_id,
            args.end_id,
            args.limit,
        )
        semaphore = asyncio.Semaphore(args.concurrency)

        async def probe_asset(record):
            asset = dict(record)
            results = []
            for source in sources:
                async with semaphore:
                    func = (
                        probe_filesystem
                        if source.get("type") == "filesystem"
                        else probe_s3
                    )
                    values = await asyncio.to_thread(func, asset, source)
                results.extend((asset["id"], *value) for value in values)
            return results

        all_attempts = []
        for values in await asyncio.gather(*(probe_asset(asset) for asset in assets)):
            all_attempts.extend(values)
        await conn.executemany(
            """insert into analytics_media_source_attempts
               (run_id,asset_id,source,candidate_key,status,error_code,detail)
               values($1,$2,$3,$4,$5,$6,$7)""",
            [(run_id, *row) for row in all_attempts],
        )
        await conn.execute(
            """update analytics_media_asset_catalog a set status='found',found_source=x.source,
               source_key=x.candidate_key,last_checked_at=now(),last_error=null
               from (select distinct on(asset_id) asset_id,source,candidate_key
                     from analytics_media_source_attempts where run_id=$1 and status='found'
                     order by asset_id,id) x where x.asset_id=a.id""",
            run_id,
        )
        await conn.execute(
            """update analytics_media_asset_catalog a set status='source_offline',last_checked_at=now(),
               last_error='one or more registered sources are offline'
               where status<>'found' and exists(select 1 from analytics_media_source_attempts x
               where x.run_id=$1 and x.asset_id=a.id and x.status='source_offline')""",
            run_id,
        )
        await conn.execute(
            """with absent as (
                 select x.asset_id from analytics_media_source_attempts x
                 join analytics_media_sources s on s.source=x.source and s.enabled where x.run_id=$1
                 group by x.asset_id having bool_and(x.status='not_found')
                   and count(distinct x.source)=(select count(*) from analytics_media_sources where enabled)
               ) update analytics_media_asset_catalog a set
                 status=case when a.missing_rounds+1>=2 and a.first_missing_at<=now()-interval '24 hours'
                   then 'confirmed_lost' else 'provisional_missing' end,
                 missing_rounds=a.missing_rounds+1,first_missing_at=coalesce(a.first_missing_at,now()),last_checked_at=now()
               from absent where absent.asset_id=a.id""",
            run_id,
        )
        await conn.execute(
            "update analytics_media_runs set status='completed',stats=jsonb_build_object('assets',$2,'attempts',$3),completed_at=now() where id=$1",
            run_id,
            len(assets),
            len(all_attempts),
        )
        print(f"probe run={run_id} assets={len(assets)} attempts={len(all_attempts)}")
    except Exception as exc:
        await conn.execute(
            "update analytics_media_runs set status='failed',error=$2,completed_at=now() where id=$1",
            run_id,
            str(exc)[:2000],
        )
        raise
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--start-id", type=int, required=True)
    parser.add_argument("--end-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=8)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
