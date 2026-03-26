import asyncio
import logging
import time

import aiohttp

from app.config import settings
from app.models import DiscoveryResult
from app.patterns.registry import get_patterns

log = logging.getLogger(__name__)

USER_AGENT = "MCPCrawler/2.0 (+https://mcpstandard.dev)"


async def crawl_domain(session: aiohttp.ClientSession, domain: str) -> DiscoveryResult:
    t0 = time.monotonic()
    for pattern in get_patterns():
        try:
            result = await pattern.check(session, domain)
            if result:
                result.latency_ms = round((time.monotonic() - t0) * 1000, 1)
                return result
        except Exception as e:
            log.debug(f"Pattern {pattern.name} error on {domain}: {e}")
    return DiscoveryResult(
        domain=domain,
        found=False,
        latency_ms=round((time.monotonic() - t0) * 1000, 1),
    )


async def crawl_batch(domains: list[str], max_concurrent: int | None = None) -> list[DiscoveryResult]:
    workers = max_concurrent or settings.crawl_workers
    semaphore = asyncio.Semaphore(workers)
    connector = aiohttp.TCPConnector(ssl=False, limit=workers)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:

        async def bounded(domain: str) -> DiscoveryResult:
            async with semaphore:
                return await crawl_domain(session, domain)

        tasks = [bounded(d) for d in domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    out = []
    for r in results:
        if isinstance(r, Exception):
            log.error(f"Crawl error: {r}")
            continue
        if r.found:
            log.info(f"Found: {r.domain} [{r.protocol}/{r.spec}] via {r.method} ({r.latency_ms}ms)")
        out.append(r)
    return out
