from fastapi import APIRouter

from app import db
from app.jobs import manager
from app.models import CrawlStartRequest

router = APIRouter(prefix="/v1/crawl", tags=["crawl"])


@router.post("/start")
async def start_crawl(req: CrawlStartRequest = CrawlStartRequest()):
    return await manager.start(concurrency=req.concurrency, list_names=req.lists)


@router.post("/stop")
async def stop_crawl():
    return await manager.stop()


@router.post("/stop/{list_name}")
async def stop_list(list_name: str):
    return await manager.stop(list_name=list_name)


@router.get("/progress")
async def progress():
    jobs = await db.get_jobs()
    total = sum(j["total"] for j in jobs)
    checked = sum(j["checked"] for j in jobs)
    found = sum(j["found"] for j in jobs)
    pct = round(checked / total * 100, 1) if total > 0 else 0
    running = any(j["status"] == "running" for j in jobs)
    return {
        "status": "running" if running else ("idle" if not manager.is_running() else "done"),
        "total": total,
        "checked": checked,
        "found": found,
        "pct": pct,
        "jobs": jobs,
    }


@router.get("/lists")
async def available_lists():
    return {"lists": manager.scan_lists()}
