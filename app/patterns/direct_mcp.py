import json
from typing import Optional

import aiohttp

from app.config import settings
from app.models import DiscoveryResult
from app.patterns.base import BasePattern


class DirectMcp(BasePattern):
    name = "direct-mcp"
    protocol = "mcp"

    PATHS = ["/mcp", "/mcp/v1"]

    async def check(self, session: aiohttp.ClientSession, domain: str) -> Optional[DiscoveryResult]:
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "clientInfo": {"name": "MCPCrawler", "version": "2.0"},
                "capabilities": {},
            },
        }
        timeout = aiohttp.ClientTimeout(total=settings.http_timeout)
        for path in self.PATHS:
            url = f"https://{domain}{path}"
            try:
                async with session.post(url, json=payload, timeout=timeout) as resp:
                    if resp.status != 200:
                        continue
                    body = await resp.text()
                    if not body.strip().startswith("{"):
                        continue
                    data = json.loads(body)
                    if data.get("result") or data.get("jsonrpc") == "2.0":
                        return self._make_result(
                            domain, method="direct",
                            endpoint=url, manifest=data,
                        )
            except Exception:
                continue
        return None
