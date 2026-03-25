# mcp-crawler

AI Capabilities Crawler — scansiona domini cercando server MCP, A2A e varianti.

Implements [draft-serra-mcp-discovery-uri-04](https://datatracker.ietf.org/doc/draft-serra-mcp-discovery-uri/) — DNS-first discovery.

## Discovery stack

```
FASE 1 — DNS TXT _mcp.{domain}         <10ms — draft-04 primario
FASE 2 — Well-known paths               HTTP — metadata ricchi
  /.well-known/mcp-server               draft-serra
  /.well-known/mcp.json                 SEP-1649 (Anthropic)
  /.well-known/mcp/server-card.json     SEP-2127
  /.well-known/agents.json              Google A2A
FASE 3 — Direct MCP handshake          last resort
```

## Usage

```bash
pip install -r requirements.txt
python crawler.py
```

## Links

- [mcpstandard.dev](https://mcpstandard.dev)
- [IETF Draft](https://datatracker.ietf.org/doc/draft-serra-mcp-discovery-uri/)
- [GitHub Discussion #2462](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2462)
