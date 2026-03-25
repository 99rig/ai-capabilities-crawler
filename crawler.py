#!/usr/bin/env python3
"""
MCP + AI Capabilities Crawler
Scansiona domini cercando endpoint MCP, A2A e varianti.
Implements draft-serra-mcp-discovery-uri-04 (DNS-first).

Stack:
  - asyncio + aiohttp  per HTTP concorrente
  - dnspython          per query DNS TXT
  - asyncpg            per PostgreSQL
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
import aiohttp
import dns.asyncresolver
import dns.exception

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

# --- Configurazione ---

# Tutti gli endpoint da provare per ogni dominio
WELL_KNOWN_PATHS = [
    '/.well-known/mcp-server',           # draft-serra-mcp-discovery-uri
    '/.well-known/mcp.json',             # SEP-1649 (Anthropic)
    '/.well-known/mcp/server-card.json', # SEP-2127
    '/.well-known/agents.json',          # Google A2A
]

DIRECT_MCP_PATHS = [
    '/mcp',
    '/mcp/v1',
]

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)
MAX_CONCURRENT = 100
USER_AGENT = 'MCPCrawler/1.0 (+https://mcpstandard.dev)'


@dataclass
class DiscoveryResult:
    domain: str
    found: bool = False
    protocol: Optional[str] = None        # mcp | a2a | unknown
    discovery_method: Optional[str] = None # dns | well-known | direct
    endpoint: Optional[str] = None
    manifest: Optional[dict] = None
    well_known_path: Optional[str] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


async def query_dns(domain: str) -> Optional[dict]:
    """
    Query DNS TXT record _mcp.{domain}.
    Returns parsed fields or None.
    Draft-04: DNS è il primitivo primario di discovery.
    """
    try:
        resolver = dns.asyncresolver.Resolver()
        resolver.timeout = 2
        resolver.lifetime = 2
        answers = await resolver.resolve(f'_mcp.{domain}', 'TXT')
        for rdata in answers:
            txt = b''.join(rdata.strings).decode('utf-8', errors='ignore')
            if 'v=mcp1' in txt:
                fields = {}
                for part in txt.split(';'):
                    part = part.strip()
                    if '=' in part:
                        k, v = part.split('=', 1)
                        fields[k.strip()] = v.strip()
                return fields
    except (dns.exception.DNSException, Exception):
        pass
    return None


async def fetch_well_known(session: aiohttp.ClientSession, domain: str) -> Optional[tuple]:
    """
    Prova tutti i well-known path noti.
    Ritorna (path, manifest_dict) o None.
    """
    for path in WELL_KNOWN_PATHS:
        url = f'https://{domain}{path}'
        try:
            async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status == 200:
                    ct = resp.headers.get('Content-Type', '')
                    if 'json' in ct:
                        try:
                            data = await resp.json(content_type=None)
                            return path, data
                        except Exception:
                            pass
        except Exception:
            pass
    return None


async def detect_protocol(path: str, manifest: dict) -> str:
    """Rileva il protocollo dal path e dal contenuto del manifest."""
    if 'agents.json' in path:
        return 'a2a'
    if 'mcp' in path or manifest.get('mcp_version') or manifest.get('protocolVersion'):
        return 'mcp'
    return 'unknown'


async def crawl_domain(session: aiohttp.ClientSession, domain: str) -> DiscoveryResult:
    """
    Logica di discovery completa per un singolo dominio.
    Ordine (draft-04):
      1. DNS TXT _mcp.{domain}   — <10ms
      2. Well-known paths         — se DNS positivo o come fallback
      3. Direct MCP endpoint      — last resort
    """
    result = DiscoveryResult(domain=domain)
    t0 = time.monotonic()

    # FASE 1 — DNS (draft-04: primitivo primario)
    dns_fields = await query_dns(domain)
    if dns_fields:
        result.discovery_method = 'dns'
        result.endpoint = dns_fields.get('src') or dns_fields.get('registry')
        result.found = True
        result.protocol = 'mcp'

    # FASE 2 — Well-known (metadata ricchi)
    wk = await fetch_well_known(session, domain)
    if wk:
        path, manifest = wk
        result.found = True
        result.well_known_path = path
        result.manifest = manifest
        result.protocol = await detect_protocol(path, manifest)
        if not result.discovery_method:
            result.discovery_method = 'well-known'
        # endpoint dal manifest se non già trovato via DNS
        if not result.endpoint:
            result.endpoint = manifest.get('endpoint') or manifest.get('url')

    # FASE 3 — Direct MCP handshake (last resort)
    if not result.found:
        for path in DIRECT_MCP_PATHS:
            url = f'https://{domain}{path}'
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "clientInfo": {"name": "MCPCrawler", "version": "1.0"},
                        "capabilities": {}
                    }
                }
                async with session.post(url, json=payload, timeout=REQUEST_TIMEOUT) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data.get('result') or data.get('jsonrpc'):
                            result.found = True
                            result.discovery_method = 'direct'
                            result.protocol = 'mcp'
                            result.endpoint = url
                            break
            except Exception:
                pass

    result.latency_ms = round((time.monotonic() - t0) * 1000, 1)
    return result


async def crawl_domains(domains: list[str]) -> list[DiscoveryResult]:
    """Crawla una lista di domini con concorrenza controllata."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    results = []

    connector = aiohttp.TCPConnector(ssl=False, limit=MAX_CONCURRENT)
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:

        async def bounded_crawl(domain):
            async with semaphore:
                return await crawl_domain(session, domain)

        tasks = [bounded_crawl(d) for d in domains]
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            result = await coro
            results.append(result)
            if result.found:
                log.info(f'✅ {result.domain} — {result.protocol} via {result.discovery_method} ({result.latency_ms}ms)')
            if (i + 1) % 100 == 0:
                log.info(f'Progress: {i+1}/{len(domains)}')

    return results


async def main():
    # Test su domini noti
    test_domains = [
        'everywheredesign.it',
        'pcbuster.it',
        'mcpstandard.dev',
        'google.com',
        'github.com',
        'shopify.com',
        'wordpress.com',
    ]

    log.info(f'Crawling {len(test_domains)} domains...')
    results = await crawl_domains(test_domains)

    found = [r for r in results if r.found]
    log.info(f'\n=== Results: {len(found)}/{len(results)} domains with AI capabilities ===')
    for r in found:
        print(json.dumps({
            'domain': r.domain,
            'protocol': r.protocol,
            'method': r.discovery_method,
            'endpoint': r.endpoint,
            'path': r.well_known_path,
            'latency_ms': r.latency_ms,
        }, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
