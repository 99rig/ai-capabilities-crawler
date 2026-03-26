# AI Capabilities Crawler

Scansiona liste di domini cercando server **MCP**, **A2A** e **OpenAI Plugin** con architettura modulare FastAPI.

Implements [draft-serra-mcp-discovery-uri-04](https://datatracker.ietf.org/doc/draft-serra-mcp-discovery-uri/) — DNS-first discovery.

## Architecture

```
app/
├── main.py              # FastAPI app + lifespan
├── config.py            # Pydantic settings (env vars)
├── db.py                # PostgreSQL pool + batch ops
├── models.py            # Pydantic schemas
├── patterns/            # Discovery patterns (plugin system)
│   ├── base.py          # BasePattern ABC
│   ├── mcp_draft_serra.py
│   ├── mcp_sep1649.py
│   ├── mcp_sep2127.py
│   ├── a2a_google.py
│   ├── openai_plugin.py
│   ├── direct_mcp.py
│   └── registry.py      # Auto-discovery via pkgutil
├── crawler/
│   └── engine.py         # Async crawl engine
├── jobs/
│   ├── manager.py        # Job queue + concurrency control
│   └── runner.py         # Streaming list processor
├── api/
│   ├── search.py         # GET /v1/search, /v1/stats
│   ├── jobs.py           # POST /v1/crawl/start|stop, GET progress
│   └── patterns.py       # GET /v1/patterns
└── static/
    └── index.html        # Dashboard
```

## Discovery Patterns

| Pattern | Method | Path / Record |
|---------|--------|---------------|
| draft-serra | DNS TXT | `_mcp.{domain}` + `/.well-known/mcp-server` |
| SEP-1649 | HTTP | `/.well-known/mcp.json` |
| SEP-2127 | HTTP | `/.well-known/mcp/server-card.json` |
| Google A2A | HTTP | `/.well-known/agents.json` |
| OpenAI Plugin | HTTP | `/.well-known/ai-plugin.json` |
| Direct MCP | JSON-RPC | `/mcp`, `/mcp/v1` |

Adding a new pattern = create a Python file in `app/patterns/` extending `BasePattern`. Auto-discovered at startup.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard |
| GET | `/v1/search` | Search discoveries (`?q=&protocol=&spec=&limit=`) |
| GET | `/v1/stats` | Total counters |
| GET | `/v1/patterns` | Active patterns |
| POST | `/v1/crawl/start` | Start crawl (`{concurrency?, lists[]?}`) |
| POST | `/v1/crawl/stop` | Stop all |
| POST | `/v1/crawl/stop/{list}` | Stop single list |
| GET | `/v1/crawl/progress` | Per-list progress |
| GET | `/v1/crawl/lists` | Available .txt lists |

## Setup

```bash
# Place domain lists in data/
data/domains_it.txt
data/domains_com.txt

# Start with Docker Compose
docker compose up -d
```

Dashboard available at `http://localhost:8000`.

## Configuration

Environment variables (prefix `CRAWL_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `CRAWL_DATABASE_URL` | `postgresql://crawler:crawler@postgres:5432/ai_capabilities` | PostgreSQL connection |
| `CRAWL_CONCURRENCY` | `2` | Max lists processed in parallel |
| `CRAWL_BATCH_SIZE` | `1000` | Domains per batch |
| `CRAWL_WORKERS` | `300` | Concurrent HTTP workers per list |
| `CRAWL_HTTP_TIMEOUT` | `3.0` | HTTP timeout (seconds) |
| `CRAWL_DATA_DIR` | `/data` | Directory with .txt domain lists |
| `CRAWL_DEDUP_FOUND_HOURS` | `24` | Skip found domains if checked within N hours |
| `CRAWL_DEDUP_NOTFOUND_DAYS` | `7` | Skip not-found domains if checked within N days |

## Features

- **Streaming** — reads domain lists in chunks, no full file load in memory
- **Batch DB** — bulk upsert operations on PostgreSQL with asyncpg
- **Resume/Pause** — stop and resume individual lists from where they left off
- **Deduplication** — skips recently checked domains (configurable intervals)
- **Extensible** — add new discovery patterns by dropping a Python file

## Links

- [mcpstandard.dev](https://mcpstandard.dev)
- [IETF Draft](https://datatracker.ietf.org/doc/draft-serra-mcp-discovery-uri/)
- [GitHub Discussion #2462](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2462)
