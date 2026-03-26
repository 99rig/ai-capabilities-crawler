from abc import ABC, abstractmethod
from typing import Optional

import aiohttp

from app.models import DiscoveryResult


class BasePattern(ABC):
    name: str = ""
    protocol: str = ""

    @abstractmethod
    async def check(self, session: aiohttp.ClientSession, domain: str) -> Optional[DiscoveryResult]:
        pass

    def _make_result(self, domain: str, **kwargs) -> DiscoveryResult:
        return DiscoveryResult(
            domain=domain,
            found=True,
            protocol=self.protocol,
            spec=self.name,
            **kwargs,
        )

    @staticmethod
    def extract_metadata(manifest: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
        name = (
            manifest.get("name")
            or manifest.get("name_for_human")
            or manifest.get("serverInfo", {}).get("title")
            or manifest.get("serverInfo", {}).get("name")
        )
        description = (
            manifest.get("description")
            or manifest.get("description_for_human")
            or manifest.get("description_for_model")
        )
        endpoint = (
            manifest.get("endpoint")
            or manifest.get("url")
            or manifest.get("api", {}).get("url")
        )
        return name, description, endpoint
