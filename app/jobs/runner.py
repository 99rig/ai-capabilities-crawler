import asyncio
import logging
import os

from app import db
from app.config import settings
from app.crawler.engine import crawl_batch

log = logging.getLogger(__name__)


async def count_lines(filepath: str) -> int:
    count = 0
    with open(filepath) as f:
        for _ in f:
            count += 1
    return count


async def stream_file(filepath: str, skip: int = 0):
    batch = []
    skipped = 0
    with open(filepath) as f:
        for line in f:
            domain = line.strip()
            if not domain:
                continue
            if skipped < skip:
                skipped += 1
                continue
            batch.append(domain)
            if len(batch) >= settings.crawl_batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


async def run_list(list_name: str, file_path: str, cancel_event: asyncio.Event):
    if not os.path.exists(file_path):
        log.error(f"[{list_name}] File not found: {file_path}")
        await db.update_job(list_name, 0, 0, "error")
        return

    total = await count_lines(file_path)
    await db.upsert_job(list_name, file_path, total)

    job = await db.get_job(list_name)
    skip = job["checked"] if job and job["status"] == "paused" else 0

    await db.update_job(list_name, skip, job["found"] if job else 0, "running")
    checked = skip
    found_total = job["found"] if job and skip > 0 else 0

    log.info(f"[{list_name}] Starting from {skip}/{total}")

    async for batch in stream_file(file_path, skip=skip):
        if cancel_event.is_set():
            log.info(f"[{list_name}] Paused at {checked}/{total}")
            await db.update_job(list_name, checked, found_total, "paused")
            return

        to_skip = await db.get_domains_to_skip(batch)
        to_crawl = [d for d in batch if d not in to_skip]

        if to_crawl:
            results = await crawl_batch(to_crawl)
            await db.batch_upsert_seen(results)
            await db.batch_upsert_discoveries(results)
            found_total += sum(1 for r in results if r.found)

        checked += len(batch)
        await db.update_job(list_name, checked, found_total, "running")

        if checked % 10000 < settings.crawl_batch_size:
            log.info(f"[{list_name}] {checked:,}/{total:,} | found={found_total}")

    await db.update_job(list_name, checked, found_total, "done")
    log.info(f"[{list_name}] DONE — {found_total} found in {checked:,} domains")
