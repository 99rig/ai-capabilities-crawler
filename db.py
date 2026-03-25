"""
Database layer per AI Capabilities Crawler.
PostgreSQL con asyncpg.
"""
import asyncpg
import os

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://crawler:crawler@localhost:5432/ai_capabilities')


CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS domains (
    id          SERIAL PRIMARY KEY,
    domain      TEXT UNIQUE NOT NULL,
    found       BOOLEAN DEFAULT FALSE,
    protocol    TEXT,           -- mcp | a2a | plugin | unknown
    spec        TEXT,           -- draft-serra | sep-1649 | google-a2a | openai-plugin
    method      TEXT,           -- dns | well-known | direct
    endpoint    TEXT,
    name        TEXT,
    description TEXT,
    well_known_path TEXT,
    manifest    JSONB,
    latency_ms  FLOAT,
    first_seen  TIMESTAMPTZ DEFAULT NOW(),
    last_checked TIMESTAMPTZ DEFAULT NOW(),
    last_found  TIMESTAMPTZ,
    check_count  INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_domains_found    ON domains(found);
CREATE INDEX IF NOT EXISTS idx_domains_protocol ON domains(protocol);
CREATE INDEX IF NOT EXISTS idx_domains_spec     ON domains(spec);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id          SERIAL PRIMARY KEY,
    started_at  TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    domains_total   INTEGER DEFAULT 0,
    domains_found   INTEGER DEFAULT 0
);
"""


async def get_pool():
    return await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)


async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES)


async def upsert_result(pool, result):
    """Inserisce o aggiorna il risultato di un dominio."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO domains
                (domain, found, protocol, spec, method, endpoint, name,
                 description, well_known_path, manifest, latency_ms,
                 last_checked, last_found, check_count)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW(),
                CASE WHEN $2 THEN NOW() ELSE NULL END, 1)
            ON CONFLICT (domain) DO UPDATE SET
                found        = EXCLUDED.found,
                protocol     = EXCLUDED.protocol,
                spec         = EXCLUDED.spec,
                method       = EXCLUDED.method,
                endpoint     = EXCLUDED.endpoint,
                name         = EXCLUDED.name,
                description  = EXCLUDED.description,
                well_known_path = EXCLUDED.well_known_path,
                manifest     = EXCLUDED.manifest,
                latency_ms   = EXCLUDED.latency_ms,
                last_checked = NOW(),
                last_found   = CASE WHEN EXCLUDED.found THEN NOW()
                                    ELSE domains.last_found END,
                check_count  = domains.check_count + 1
        """,
        result.domain,
        result.found,
        result.protocol,
        result.spec,
        result.discovery_method,
        result.endpoint,
        result.name,
        result.description,
        result.well_known_path,
        __import__("json").dumps(result.manifest) if result.manifest else None,
        result.latency_ms,
        )


async def search(pool, q=None, protocol=None, spec=None, limit=10, offset=0):
    """Search API — cerca per testo, protocollo, spec."""
    conditions = ['found = TRUE']
    params = []
    i = 1

    if protocol:
        conditions.append(f'protocol = ${i}')
        params.append(protocol)
        i += 1
    if spec:
        conditions.append(f'spec = ${i}')
        params.append(spec)
        i += 1
    if q:
        conditions.append(f'(name ILIKE ${i} OR description ILIKE ${i} OR domain ILIKE ${i})')
        params.append(f'%{q}%')
        i += 1

    where = ' AND '.join(conditions)
    params += [limit, offset]

    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT domain, protocol, spec, method, endpoint,
                   name, description, well_known_path, latency_ms,
                   last_found, check_count
            FROM domains
            WHERE {where}
            ORDER BY last_found DESC NULLS LAST
            LIMIT ${i} OFFSET ${i+1}
        """, *params)

        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM domains WHERE {where}
        """, *params[:-2])

    return total, [dict(r) for r in rows]
