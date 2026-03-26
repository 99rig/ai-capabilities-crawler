import json
from typing import Optional

import aiohttp
import dns.asyncresolver
import dns.exception

from app.config import settings
from app.models import DiscoveryResult
from app.patterns.base import BasePattern


class McpDraftSerra(BasePattern):
    name = "draft-serra"
    protocol = "mcp"

    async def check(self, session: aiohttp.ClientSession, domain: str) -> Optional[DiscoveryResult]:
        dns_result = await self._check_dns(domain)
        wk_result = await self._check_well_known(session, domain)

        if not dns_result and not wk_result:
            return None

        result = self._make_result(domain, method="dns" if dns_result else "well-known")
        if dns_result:
            result.endpoint = dns_result.get("src") or dns_result.get("registry")
        if wk_result:
            path, manifest = wk_result
            result.well_known_path = path
            result.manifest = manifest
            name, description, endpoint = self.extract_metadata(manifest)
            result.name = name
            result.description = description
            if not result.endpoint:
                result.endpoint = endpoint
        return result

    async def _check_dns(self, domain: str) -> Optional[dict]:
        resolver = dns.asyncresolver.Resolver()
        resolver.timeout = 2
        resolver.lifetime = 2
        try:
            answers = await resolver.resolve(f"_mcp.{domain}", "TXT")
            for rdata in answers:
                txt = b"".join(rdata.strings).decode("utf-8", errors="ignore")
                if "v=mcp1" in txt:
                    fields = {}
                    for part in txt.split(";"):
                        part = part.strip()
                        if "=" in part:
                            k, v = part.split("=", 1)
                            fields[k.strip()] = v.strip()
                    return fields
        except (dns.exception.DNSException, Exception):
            pass
        return None

    async def _check_well_known(self, session: aiohttp.ClientSession, domain: str) -> Optional[tuple]:
        url = f"https://{domain}/.well-known/mcp-server"
        try:
            timeout = aiohttp.ClientTimeout(total=settings.http_timeout)
            async with session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                body = await resp.text()
                if not body.strip().startswith("{"):
                    return None
                data = json.loads(body)
                if data.get("endpoint") or data.get("mcp_version") or data.get("protocolVersion") or data.get("serverInfo"):
                    return "/.well-known/mcp-server", data
        except Exception:
            pass
        return None
