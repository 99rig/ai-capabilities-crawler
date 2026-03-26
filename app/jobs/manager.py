import asyncio
import logging
from pathlib import Path

from app import db
from app.config import settings
from app.jobs.runner import run_list
from app.patterns.registry import discover_patterns

log = logging.getLogger(__name__)

_cancel_events: dict[str, asyncio.Event] = {}
_tasks: dict[str, asyncio.Task] = {}
_running = False


def scan_lists() -> list[dict]:
    data_dir = Path(settings.data_dir)
    if not data_dir.exists():
        return []
    return [
        {"list_name": f.stem, "file_path": str(f)}
        for f in sorted(data_dir.glob("*.txt"))
    ]


async def start(concurrency: int | None = None, list_names: list[str] | None = None):
    global _running
    if _running:
        return {"status": "already_running"}

    discover_patterns()
    max_concurrent = concurrency or settings.crawl_concurrency
    available = scan_lists()

    if list_names:
        available = [l for l in available if l["list_name"] in list_names]

    if not available:
        return {"status": "no_lists", "data_dir": settings.data_dir}

    _running = True
    log.info(f"Starting crawl: {len(available)} lists, concurrency={max_concurrent}")

    for lst in available:
        total = sum(1 for line in open(lst["file_path"]) if line.strip())
        await db.upsert_job(lst["list_name"], lst["file_path"], total)

    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_with_semaphore(lst):
        cancel_event = asyncio.Event()
        _cancel_events[lst["list_name"]] = cancel_event
        async with semaphore:
            if cancel_event.is_set():
                return
            await run_list(lst["list_name"], lst["file_path"], cancel_event)
        _cancel_events.pop(lst["list_name"], None)

    async def run_all():
        global _running
        tasks = [asyncio.create_task(run_with_semaphore(lst)) for lst in available]
        for name, task in zip([l["list_name"] for l in available], tasks):
            _tasks[name] = task
        await asyncio.gather(*tasks, return_exceptions=True)
        _tasks.clear()
        _cancel_events.clear()
        _running = False
        log.info("Crawl completed")

    asyncio.create_task(run_all())
    return {"status": "started", "lists": len(available), "concurrency": max_concurrent}


async def stop(list_name: str | None = None):
    if list_name:
        event = _cancel_events.get(list_name)
        if event:
            event.set()
            return {"status": "stopping", "list": list_name}
        return {"status": "not_found", "list": list_name}
    else:
        for event in _cancel_events.values():
            event.set()
        return {"status": "stopping_all", "lists": list(_cancel_events.keys())}


def is_running() -> bool:
    return _running
