from fastapi import APIRouter, Query

from app import db

router = APIRouter(prefix="/v1", tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(None),
    protocol: str = Query(None),
    spec: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    total, results = await db.search_discoveries(
        q=q, protocol=protocol, spec=spec, limit=limit, offset=offset
    )
    return {"query": q, "total": total, "limit": limit, "offset": offset, "results": results}


@router.get("/stats")
async def stats():
    return await db.get_stats()
