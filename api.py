"""
Search API REST — FastAPI
GET /v1/search?q=notion&protocol=mcp&limit=10
"""
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import db

pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await db.get_pool()
    await db.init_db(pool)
    yield
    await pool.close()

app = FastAPI(title='AI Capabilities Search API', lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['GET'])


@app.get('/v1/search')
async def search(
    q:        str  = Query(None, description='Testo libero'),
    protocol: str  = Query(None, description='mcp | a2a | plugin'),
    spec:     str  = Query(None, description='draft-serra | sep-1649 | openai-plugin'),
    limit:    int  = Query(10, ge=1, le=50),
    offset:   int  = Query(0, ge=0),
):
    total, results = await db.search(pool, q=q, protocol=protocol,
                                     spec=spec, limit=limit, offset=offset)
    return {
        'query': q,
        'total': total,
        'limit': limit,
        'offset': offset,
        'results': results,
    }


@app.get('/v1/stats')
async def stats():
    async with pool.acquire() as conn:
        total     = await conn.fetchval('SELECT COUNT(*) FROM domains')
        found     = await conn.fetchval('SELECT COUNT(*) FROM domains WHERE found=TRUE')
        by_proto  = await conn.fetch("""
            SELECT protocol, COUNT(*) as count
            FROM domains WHERE found=TRUE
            GROUP BY protocol ORDER BY count DESC
        """)
        by_spec   = await conn.fetch("""
            SELECT spec, COUNT(*) as count
            FROM domains WHERE found=TRUE
            GROUP BY spec ORDER BY count DESC
        """)
    return {
        'total_domains_checked': total,
        'total_found': found,
        'by_protocol': [dict(r) for r in by_proto],
        'by_spec':     [dict(r) for r in by_spec],
    }
