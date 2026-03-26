import json
from typing import Optional

import aiohttp

from app.config import settings
from app.models import DiscoveryResult
from app.patterns.base import BasePattern


class OpenaiPlugin(BasePattern):
    name = "openai-plugin"
    protocol = "plugin"

    async def check(self, session: aiohttp.ClientSession, domain: str) -> Optional[DiscoveryResult]:
        url = f"https://{domain}/.well-known/ai-plugin.json"
        try:
            timeout = aiohttp.ClientTimeout(total=settings.http_timeout)
            async with session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                body = await resp.text()
                if not body.strip().startswith("{"):
                    return None
                data = json.loads(body)
                if not (data.get("api") or data.get("name_for_model") or data.get("schema_version")):
                    return None
                name = data.get("name_for_human") or data.get("name_for_model")
                description = data.get("description_for_human") or data.get("description_for_model")
                endpoint = data.get("api", {}).get("url")
                return self._make_result(
                    domain, method="well-known",
                    well_known_path="/.well-known/ai-plugin.json",
                    manifest=data, name=name,
                    description=description, endpoint=endpoint,
                )
        except Exception:
            return None
