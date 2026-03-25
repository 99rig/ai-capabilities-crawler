#!/usr/bin/env python3
"""
MCP + AI Capabilities Crawler
Scansiona domini cercando endpoint MCP, A2A, ChatGPT Plugin e varianti.
Implements draft-serra-mcp-discovery-uri-04 (DNS-first).
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

# --- Tutti i path noti per AI capabilities ---

WELL_KNOWN_PATHS = [
    # MCP
    ('/.well-known/mcp-server',            'mcp',    'draft-serra'),
    ('/.well-known/mcp.json',              'mcp',    'sep-1649'),
    ('/.well-known/mcp/server-card.json',  'mcp',    'sep-2127'),
    # Google A2A
    ('/.well-known/agents.json',           'a2a',    'google-a2a'),
    # OpenAI ChatGPT Plugins
    ('/.well-known/ai-plugin.json',        'plugin', 'openai-plugin'),
]

DIRECT_MCP_PATHS = [
    '/mcp',
    '/mcp/v1',
]

DNS_RECORDS = [
    '_mcp',    # MCP standard
    '_agent',  # futuro A2A
]

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)
MAX_CONCURRENT = 100
USER_AGENT = 'MCPCrawler/1.0 (+https://mcpstandard.dev)'


@dataclass
class DiscoveryResult:
    domain: str
    found: bool = False
    protocol: Optional[str] = None        # mcp | a2a | plugin | unknown
    spec: Optional[str] = None            # draft-serra | sep-1649 | google-a2a | openai-plugin
    discovery_method: Optional[str] = None # dns | well-known | direct
    endpoint: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    manifest: Optional[dict] = None
    well_known_path: Optional[str] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


async def query_dns_txt(domain: str) -> Optional[dict]:
    """
    Query DNS TXT records per tutti i prefissi noti.
    Draft-04: DNS è il primitivo primario di discovery.
    """
    resolver = dns.asyncresolver.Resolver()
    resolver.timeout = 2
    resolver.lifetime = 2

    for prefix in DNS_RECORDS:
        try:
            answers = await resolver.resolve(f'{prefix}.{domain}', 'TXT')
            for rdata in answers:
                txt = b''.join(rdata.strings).decode('utf-8', errors='ignore')
                if 'v=mcp1' in txt:
                    fields = {'_prefix': prefix}
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
    Ritorna (path, protocol, spec, manifest) o None.
    Solo se il body è JSON valido.
    """
    for path, protocol, spec in WELL_KNOWN_PATHS:
        url = f'https://{domain}{path}'
        try:
            async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status == 200:
                    body = await resp.text()
                    body = body.strip()
                    if body.startswith('{'):
                        try:
                            data = json.loads(body)
                            return path, protocol, spec, data
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
    return None


async def check_direct_mcp(session: aiohttp.ClientSession, domain: str) -> Optional[str]:
    """
    Prova handshake MCP diretto.
    Ritorna l'endpoint URL se risponde correttamente.
    """
    for path in DIRECT_MCP_PATHS:
        url = f'https://{domain}{path}'
        try:
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "clientInfo": {"name": "MCPCrawler", "version": "1.0"},
                    "capabilities": {}
                }
            }
            async with session.post(url, json=payload, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status == 200:
                    body = await resp.text()
                    if body.strip().startswith('{'):
                        data = json.loads(body)
                        if data.get('result') or data.get('jsonrpc') == '2.0':
                            return url
        except Exception:
            pass
    return None


def extract_metadata(manifest: dict) -> tuple:
    """Estrae name e description dal manifest indipendentemente dal formato."""
    name = (
        manifest.get('name') or
        manifest.get('name_for_human') or
        manifest.get('serverInfo', {}).get('title') or
        manifest.get('serverInfo', {}).get('name')
    )
    description = (
        manifest.get('description') or
        manifest.get('description_for_human') or
        manifest.get('description_for_model')
    )
    endpoint = (
        manifest.get('endpoint') or
        manifest.get('url') or
        manifest.get('api', {}).get('url')
    )
    return name, description, endpoint


async def crawl_domain(session: aiohttp.ClientSession, domain: str) -> DiscoveryResult:
    """
    Discovery completa per un dominio.
    Ordine (draft-04):
      1. DNS TXT         — <10ms, primitivo primario
      2. Well-known      — metadata ricchi, tutti i protocolli
      3. Direct MCP      — last resort
    """
    result = DiscoveryResult(domain=domain)
    t0 = time.monotonic()

    # FASE 1 — DNS
    dns_fields = await query_dns_txt(domain)
    if dns_fields:
        result.discovery_method = 'dns'
        result.protocol = 'mcp'
        result.spec = 'draft-serra'
        result.endpoint = dns_fields.get('src') or dns_fields.get('registry')
        result.found = True

    # FASE 2 — Well-known
    wk = await fetch_well_known(session, domain)
    if wk:
        path, protocol, spec, manifest = wk
        result.found = True
        result.well_known_path = path
        result.manifest = manifest
        result.protocol = protocol
        result.spec = spec
        if not result.discovery_method:
            result.discovery_method = 'well-known'
        name, description, endpoint = extract_metadata(manifest)
        result.name = name
        result.description = description
        if not result.endpoint:
            result.endpoint = endpoint

    # FASE 3 — Direct MCP
    if not result.found:
        endpoint = await check_direct_mcp(session, domain)
        if endpoint:
            result.found = True
            result.discovery_method = 'direct'
            result.protocol = 'mcp'
            result.endpoint = endpoint

    result.latency_ms = round((time.monotonic() - t0) * 1000, 1)
    return result


async def crawl_domains(domains: list) -> list:
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
                log.info(f'✅ {result.domain} [{result.protocol}/{result.spec}] via {result.discovery_method} ({result.latency_ms}ms)')
            if (i + 1) % 100 == 0:
                log.info(f'Progress: {i+1}/{len(domains)}')

    return results


async def main():
    test_domains = [
        # Nostri
        'everywheredesign.it',
        'pcbuster.it',
        'mcpstandard.dev',
        # MCP (SEP-1649)
        'notion.so',
        # ChatGPT Plugins
        'slack.com',
        'zapier.com',
        # A2A e altri
        'google.com',
        'github.com',
        'openai.com',
        'anthropic.com',
        'stripe.com',
        'shopify.com',
    ]

    log.info(f'Crawling {len(test_domains)} domains...')
    results = await crawl_domains(test_domains)

    found = [r for r in results if r.found]
    log.info(f'\n=== Results: {len(found)}/{len(results)} domains with AI capabilities ===\n')

    for r in found:
        print(json.dumps({
            'domain': r.domain,
            'protocol': r.protocol,
            'spec': r.spec,
            'method': r.discovery_method,
            'name': r.name,
            'endpoint': r.endpoint,
            'path': r.well_known_path,
            'latency_ms': r.latency_ms,
        }, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
