from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel


@dataclass
class DiscoveryResult:
    domain: str
    found: bool = False
    protocol: Optional[str] = None
    spec: Optional[str] = None
    method: Optional[str] = None
    endpoint: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    manifest: Optional[dict] = None
    well_known_path: Optional[str] = None
    latency_ms: Optional[float] = None


class SearchQuery(BaseModel):
    q: Optional[str] = None
    protocol: Optional[str] = None
    spec: Optional[str] = None
    limit: int = 20
    offset: int = 0


class CrawlStartRequest(BaseModel):
    concurrency: Optional[int] = None
    lists: Optional[list[str]] = None


class JobStatus(BaseModel):
    list_name: str
    file_path: str
    total: int
    checked: int
    found: int
    status: str
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
