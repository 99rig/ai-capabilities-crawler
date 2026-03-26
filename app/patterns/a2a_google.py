import json
from typing import Optional

import aiohttp

from app.config import settings
from app.models import DiscoveryResult
from app.patterns.base import BasePattern


class A2aGoogle(BasePattern):
    name = "google-a2a"
    protocol = "a2a"

    async def check(self, session: aiohttp.ClientSession, domain: str) -> Optional[DiscoveryResult]:
        url = f"https://{domain}/.well-known/agents.json"
        try:
            timeout = aiohttp.ClientTimeout(total=settings.http_timeout)
            async with session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                body = await resp.text()
                if not body.strip().startswith(("{", "[")):
                    return None
                data = json.loads(body)
                if isinstance(data, list):
                    data = data[0] if data else {}
                if not (data.get("capabilities") or data.get("agentId") or data.get("name")):
                    return None
                name = data.get("name") or data.get("agentId")
                description = data.get("description")
                endpoint = data.get("url") or data.get("endpoint")
                return self._make_result(
                    domain, method="well-known",
                    well_known_path="/.well-known/agents.json",
                    manifest=data, name=name,
                    description=description, endpoint=endpoint,
                )
        except Exception:
            return None
