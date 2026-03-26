import json
import logging

import asyncpg

from app.config import settings
from app.models import DiscoveryResult

log = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_domains (
    domain       TEXT PRIMARY KEY,
    last_checked TIMESTAMPTZ DEFAULT NOW(),
    found        BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS discoveries (
    id              SERIAL PRIMARY KEY,
    domain          TEXT UNIQUE NOT NULL,
    protocol        TEXT NOT NULL,
    spec            TEXT NOT NULL,
    method          TEXT NOT NULL,
    endpoint        TEXT,
    name            TEXT,
    description     TEXT,
    well_known_path TEXT,
    manifest        JSONB,
    latency_ms      FLOAT,
    first_seen      TIMESTAMPTZ DEFAULT NOW(),
    last_found      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discoveries_protocol ON discoveries(protocol);
CREATE INDEX IF NOT EXISTS idx_discoveries_spec ON discoveries(spec);
CREATE INDEX IF NOT EXISTS idx_seen_domains_checked ON seen_domains(last_checked);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id          SERIAL PRIMARY KEY,
    list_name   TEXT UNIQUE NOT NULL,
    file_path   TEXT NOT NULL,
    total       INTEGER DEFAULT 0,
    checked     INTEGER DEFAULT 0,
    found       INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'pending',
    started_at  TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
"""


async def init(dsn: str | None = None):
    global pool
    pool = await asyncpg.create_pool(dsn or settings.database_url, min_size=2, max_size=20)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
    log.info("Database initialized")


async def close():
    global pool
    if pool:
        await pool.close()
        pool = None


async def get_domains_to_skip(domains: list[str]) -> set[str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT domain FROM seen_domains
            WHERE domain = ANY($1)
            AND (
                (found = TRUE  AND last_checked > NOW() - make_interval(hours => $2))
                OR
                (found = FALSE AND last_checked > NOW() - make_interval(days => $3))
            )
        """, domains, settings.dedup_found_hours, settings.dedup_notfound_days)
    return {r["domain"] for r in rows}


async def batch_upsert_seen(results: list[DiscoveryResult]):
    if not results:
        return
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO seen_domains (domain, last_checked, found)
            VALUES ($1, NOW(), $2)
            ON CONFLICT (domain) DO UPDATE SET
                last_checked = NOW(),
                found = CASE WHEN EXCLUDED.found THEN TRUE ELSE seen_domains.found END
        """, [(r.domain, r.found) for r in results])


async def batch_upsert_discoveries(results: list[DiscoveryResult]):
    found = [r for r in results if r.found]
    if not found:
        return
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO discoveries
                (domain, protocol, spec, method, endpoint, name,
                 description, well_known_path, manifest, latency_ms)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (domain) DO UPDATE SET
                protocol = EXCLUDED.protocol,
                spec = EXCLUDED.spec,
                method = EXCLUDED.method,
                endpoint = EXCLUDED.endpoint,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                well_known_path = EXCLUDED.well_known_path,
                manifest = EXCLUDED.manifest,
                latency_ms = EXCLUDED.latency_ms,
                last_found = NOW()
        """, [
            (r.domain, r.protocol, r.spec, r.method, r.endpoint,
             r.name, r.description, r.well_known_path,
             json.dumps(r.manifest) if r.manifest else None,
             r.latency_ms)
            for r in found
        ])


async def upsert_job(list_name: str, file_path: str, total: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO crawl_jobs (list_name, file_path, total, status)
            VALUES ($1, $2, $3, 'pending')
            ON CONFLICT (list_name) DO UPDATE SET
                file_path = $2, total = $3,
                updated_at = NOW()
        """, list_name, file_path, total)


async def update_job(list_name: str, checked: int, found: int, status: str = "running"):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE crawl_jobs SET
                checked = $2, found = $3, status = $4,
                started_at = COALESCE(started_at, NOW()),
                updated_at = NOW()
            WHERE list_name = $1
        """, list_name, checked, found, status)


async def get_jobs() -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM crawl_jobs ORDER BY list_name")
    result = []
    for r in rows:
        d = dict(r)
        for k in ("started_at", "updated_at"):
            if d.get(k):
                d[k] = d[k].isoformat()
        result.append(d)
    return result


async def get_job(list_name: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM crawl_jobs WHERE list_name = $1", list_name
        )
    if not row:
        return None
    d = dict(row)
    for k in ("started_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


async def search_discoveries(q=None, protocol=None, spec=None, limit=20, offset=0):
    conditions = []
    params = []
    i = 1
    if protocol:
        conditions.append(f"protocol = ${i}")
        params.append(protocol)
        i += 1
    if spec:
        conditions.append(f"spec = ${i}")
        params.append(spec)
        i += 1
    if q:
        conditions.append(f"(name ILIKE ${i} OR description ILIKE ${i} OR domain ILIKE ${i})")
        params.append(f"%{q}%")
        i += 1
    where = " AND ".join(conditions) if conditions else "TRUE"
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM discoveries WHERE {where}", *params
        )
        rows = await conn.fetch(
            f"""SELECT domain, protocol, spec, method, endpoint,
                       name, description, well_known_path, latency_ms, last_found
                FROM discoveries WHERE {where}
                ORDER BY last_found DESC NULLS LAST
                LIMIT ${i} OFFSET ${i+1}""",
            *params, limit, offset
        )
    return total, [dict(r) for r in rows]


async def get_stats():
    async with pool.acquire() as conn:
        total_seen = await conn.fetchval("SELECT COUNT(*) FROM seen_domains")
        total_found = await conn.fetchval("SELECT COUNT(*) FROM discoveries")
        by_proto = await conn.fetch(
            "SELECT protocol, COUNT(*) as count FROM discoveries GROUP BY protocol ORDER BY count DESC"
        )
        by_spec = await conn.fetch(
            "SELECT spec, COUNT(*) as count FROM discoveries GROUP BY spec ORDER BY count DESC"
        )
    return {
        "total_domains_checked": total_seen,
        "total_found": total_found,
        "by_protocol": [dict(r) for r in by_proto],
        "by_spec": [dict(r) for r in by_spec],
    }
