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
_semaphore: asyncio.Semaphore | None = None


def scan_lists() -> list[dict]:
    data_dir = Path(settings.data_dir)
    if not data_dir.exists():
        return []
    return [
        {"list_name": f.stem, "file_path": str(f)}
        for f in sorted(data_dir.glob("*.txt"))
    ]


async def _run_one(lst: dict):
    """Run a single list with semaphore control."""
    cancel_event = asyncio.Event()
    _cancel_events[lst["list_name"]] = cancel_event
    try:
        async with _semaphore:
            if cancel_event.is_set():
                return
            await run_list(lst["list_name"], lst["file_path"], cancel_event)
    finally:
        _cancel_events.pop(lst["list_name"], None)
        _tasks.pop(lst["list_name"], None)


async def start(concurrency: int | None = None, list_names: list[str] | None = None):
    global _semaphore

    discover_patterns()
    max_concurrent = concurrency or settings.crawl_concurrency
    available = scan_lists()

    if list_names:
        available = [l for l in available if l["list_name"] in list_names]

    if not available:
        return {"status": "no_lists", "data_dir": settings.data_dir}

    # Filter out lists already running
    already_running = []
    to_start = []
    for lst in available:
        if lst["list_name"] in _tasks:
            already_running.append(lst["list_name"])
        else:
            to_start.append(lst)

    if not to_start:
        return {"status": "already_running", "lists": already_running}

    # Create or update semaphore
    if _semaphore is None or concurrency:
        _semaphore = asyncio.Semaphore(max_concurrent)

    log.info(f"Starting crawl: {len(to_start)} new lists, concurrency={max_concurrent}")

    for lst in to_start:
        total = sum(1 for line in open(lst["file_path"]) if line.strip())
        await db.upsert_job(lst["list_name"], lst["file_path"], total)

    # Launch each list as independent task
    started = []
    for lst in to_start:
        task = asyncio.create_task(_run_one(lst))
        _tasks[lst["list_name"]] = task
        started.append(lst["list_name"])

    return {
        "status": "started",
        "started": started,
        "already_running": already_running,
        "concurrency": max_concurrent,
    }


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
    return len(_tasks) > 0
