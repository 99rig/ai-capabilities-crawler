import json
from typing import Optional

import aiohttp

from app.config import settings
from app.models import DiscoveryResult
from app.patterns.base import BasePattern


class McpSep1649(BasePattern):
    name = "sep-1649"
    protocol = "mcp"

    async def check(self, session: aiohttp.ClientSession, domain: str) -> Optional[DiscoveryResult]:
        url = f"https://{domain}/.well-known/mcp.json"
        try:
            timeout = aiohttp.ClientTimeout(total=settings.http_timeout)
            async with session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                body = await resp.text()
                if not body.strip().startswith("{"):
                    return None
                data = json.loads(body)
                if not (data.get("endpoint") or data.get("mcp_version") or data.get("protocolVersion") or data.get("serverInfo")):
                    return None
                name, description, endpoint = self.extract_metadata(data)
                return self._make_result(
                    domain, method="well-known",
                    well_known_path="/.well-known/mcp.json",
                    manifest=data, name=name,
                    description=description, endpoint=endpoint,
                )
        except Exception:
            return None
