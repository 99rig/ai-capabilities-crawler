"""
AI Capabilities Search API — FastAPI
GET /v1/search?q=notion&protocol=mcp&limit=10
GET /v1/stats
GET /  → dashboard HTML
"""
from fastapi import FastAPI, Query
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import db

pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await db.get_pool()
    await db.init_db(pool)
    yield
    await pool.close()

app = FastAPI(title='AI Capabilities Search API', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['GET'])

DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Capabilities Crawler</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #FAF9F5; color: #2c2c2c; }
  header { border-bottom: 1px solid #e2dfd8; padding: 1rem 2rem;
           display: flex; align-items: center; gap: 1rem; }
  header h1 { font-size: 1rem; font-weight: 600; }
  header a { color: #2c2c2c; text-decoration: none; font-size: 0.85rem; color: #999; }
  .container { max-width: 1100px; margin: 0 auto; padding: 2rem; }
  .stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px,1fr));
           gap: 1rem; margin-bottom: 2rem; }
  .stat { background: #fff; border: 1px solid #e2dfd8; border-radius: 6px;
          padding: 1rem; text-align: center; }
  .stat-n { font-size: 2rem; font-weight: 700; }
  .stat-l { font-size: 0.75rem; color: #999; margin-top: 0.2rem; }
  .filters { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
  .filters input, .filters select {
    padding: 6px 10px; border: 1px solid #dedad2; border-radius: 4px;
    background: #fff; font-size: 0.85rem; }
  .filters input { flex: 1; min-width: 200px; }
  .filters button { padding: 6px 16px; background: #2c2c2c; color: #fff;
    border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
  table { width: 100%; border-collapse: collapse; background: #fff;
          border: 1px solid #e2dfd8; border-radius: 6px; overflow: hidden; }
  th { background: #f5f3ee; text-align: left; padding: 8px 12px;
       font-size: 0.75rem; font-weight: 600; color: #666;
       border-bottom: 1px solid #e2dfd8; }
  td { padding: 8px 12px; font-size: 0.82rem; border-bottom: 1px solid #f0ede8; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #faf8f4; }
  .badge { display: inline-block; padding: 2px 7px; border-radius: 3px;
           font-size: 0.7rem; font-weight: 600; }
  .badge-mcp    { background: #e8f0f7; color: #2d6a9f; }
  .badge-a2a    { background: #e8f7ee; color: #1a7a3f; }
  .badge-plugin { background: #fdf6e3; color: #7a5c00; }
  .badge-dns    { background: #f0e8f7; color: #6a2d9f; }
  .total { font-size: 0.8rem; color: #999; margin-bottom: 0.8rem; }
  a.endpoint { color: #2d6a9f; text-decoration: none; font-size: 0.78rem; }
  a.endpoint:hover { text-decoration: underline; }
</style>
</head>
<body>
<header>
  <div>
    <h1>AI Capabilities Crawler</h1>
    <a href="https://mcpstandard.dev" target="_blank">mcpstandard.dev</a>
  </div>
</header>
<div class="container">
  <div class="stats" id="stats"></div>
  <div id="progress-bar" style="margin-bottom:1.5rem;display:none">
    <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.8rem;color:#666;margin-bottom:4px">
      <span id="progress-label">Crawling...</span>
      <div style="display:flex;align-items:center;gap:0.8rem">
        <span id="progress-pct"></span>
        <button id="stop-btn" onclick="stopCrawl()" style="padding:2px 10px;background:#c0392b;color:#fff;border:none;border-radius:3px;cursor:pointer;font-size:0.75rem">Stop</button>
      </div>
    </div>
    <div style="background:#e2dfd8;border-radius:4px;height:6px">
      <div id="progress-fill" style="background:#2c2c2c;height:6px;border-radius:4px;transition:width 0.5s"></div>
    </div>
  </div>
  <div class="filters">
    <input id="q" type="text" placeholder="Search domain, name, description...">
    <select id="protocol">
      <option value="">All protocols</option>
      <option value="mcp">MCP</option>
      <option value="a2a">A2A</option>
      <option value="plugin">ChatGPT Plugin</option>
    </select>
    <select id="spec">
      <option value="">All specs</option>
      <option value="draft-serra">draft-serra</option>
      <option value="sep-1649">SEP-1649</option>
      <option value="google-a2a">Google A2A</option>
      <option value="openai-plugin">OpenAI Plugin</option>
    </select>
    <button onclick="search()">Search</button>
  </div>
  <div class="total" id="total"></div>
  <table>
    <thead>
      <tr>
        <th>Domain</th>
        <th>Name</th>
        <th>Protocol</th>
        <th>Spec</th>
        <th>Method</th>
        <th>Endpoint</th>
        <th>Latency</th>
      </tr>
    </thead>
    <tbody id="results"></tbody>
  </table>
</div>
<script>
async function loadStats() {
  const r = await fetch('/v1/stats');
  const d = await r.json();
  const el = document.getElementById('stats');
  el.innerHTML = `
    <div class="stat"><div class="stat-n">${d.total_domains_checked||0}</div><div class="stat-l">Checked</div></div>
    <div class="stat"><div class="stat-n">${d.total_found||0}</div><div class="stat-l">Found</div></div>
    ${(d.by_protocol||[]).map(p=>`<div class="stat"><div class="stat-n">${p.count}</div><div class="stat-l">${p.protocol}</div></div>`).join('')}
  `;
}
async function search() {
  const q = document.getElementById('q').value;
  const protocol = document.getElementById('protocol').value;
  const spec = document.getElementById('spec').value;
  let url = `/v1/search?limit=50`;
  if (q) url += `&q=${encodeURIComponent(q)}`;
  if (protocol) url += `&protocol=${protocol}`;
  if (spec) url += `&spec=${spec}`;
  const r = await fetch(url);
  const d = await r.json();
  document.getElementById('total').textContent = `${d.total} results`;
  const BADGE = {mcp:'badge-mcp', a2a:'badge-a2a', plugin:'badge-plugin'};
  const METHOD = {dns:'badge-dns'};
  document.getElementById('results').innerHTML = d.results.map(row => `
    <tr>
      <td>${row.domain}</td>
      <td>${row.name||''}</td>
      <td><span class="badge ${BADGE[row.protocol]||''}">${row.protocol||''}</span></td>
      <td><span class="badge">${row.spec||''}</span></td>
      <td><span class="badge ${METHOD[row.method]||''}">${row.method||''}</span></td>
      <td>${row.endpoint?`<a class="endpoint" href="${row.endpoint}" target="_blank">${row.endpoint.replace('https://','').substring(0,40)}</a>`:''}</td>
      <td>${row.latency_ms||''}ms</td>
    </tr>
  `).join('');
}
loadStats();
search();
async function stopCrawl() {
  if (!confirm('Stop the crawl?')) return;
  document.getElementById('stop-btn').textContent = 'Stopping...';
  document.getElementById('stop-btn').disabled = true;
  await fetch('/v1/crawl/stop');
}
async function pollProgress() {
  try {
    const r = await fetch('/v1/progress');
    const d = await r.json();
    const bar = document.getElementById('progress-bar');
    if (d.status === 'running') {
      bar.style.display = 'block';
      document.getElementById('progress-label').textContent =
        `Crawling batch ${d.batch}/${d.batches_total} — ${d.checked.toLocaleString()}/${d.total.toLocaleString()} domains`;
      document.getElementById('progress-pct').textContent = `${d.pct}%`;
      document.getElementById('progress-fill').style.width = `${d.pct}%`;
      loadStats();
      search();
    } else if (d.status === 'stopped') {
      bar.style.display = 'block';
      document.getElementById('progress-label').textContent = `Crawl stopped — ${(d.checked||0).toLocaleString()}/${(d.total||0).toLocaleString()} domains scanned`;
      document.getElementById('progress-pct').textContent = `${d.pct||0}%`;
      document.getElementById('progress-fill').style.width = `${d.pct||0}%`;
      if (document.getElementById('stop-btn')) document.getElementById('stop-btn').style.display='none';
      loadStats(); search();
  } else if (d.status === 'done') {
      bar.style.display = 'block';
      document.getElementById('progress-label').textContent = `Crawl completed — ${d.total.toLocaleString()} domains scanned`;
      document.getElementById('progress-pct').textContent = `100%`;
      document.getElementById('progress-fill').style.width = `100%`;
      loadStats();
      search();
    } else {
      bar.style.display = 'none';
    }
  } catch(e) { console.error('progress error', e); }
  setTimeout(pollProgress, 3000);
}
pollProgress();
</script>
</body>
</html>"""

@app.get('/', response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD

import signal
import subprocess

@app.get('/v1/crawl/stop')
async def stop_crawl():
    """Ferma il crawl in corso."""
    try:
        result = subprocess.run(
            ['pkill', '-f', 'crawl_1m.py'],
            capture_output=True, text=True
        )
        # Aggiorna il file di progress
        import json, os
        if os.path.exists('/app/crawl_progress.json'):
            with open('/app/crawl_progress.json') as f:
                progress = json.load(f)
            progress['status'] = 'stopped'
            with open('/app/crawl_progress.json', 'w') as f:
                json.dump(progress, f)
        return {'status': 'stopped'}
    except Exception as e:
        return {'status': 'error', 'detail': str(e)}

@app.get('/v1/progress')
async def progress():
    """Stato del crawl in corso."""
    path = '/app/crawl_progress.json'
    try:
        if os.path.exists(path):
            import json
            with open(path) as f:
                return json.load(f)
    except:
        pass
    return {'status': 'idle'}

@app.get('/v1/search')
async def search_api(
    q:        str = Query(None),
    protocol: str = Query(None),
    spec:     str = Query(None),
    limit:    int = Query(10, ge=1, le=50),
    offset:   int = Query(0, ge=0),
):
    total, results = await db.search(pool, q=q, protocol=protocol,
                                     spec=spec, limit=limit, offset=offset)
    return {'query': q, 'total': total, 'limit': limit,
            'offset': offset, 'results': results}

@app.get('/v1/stats')
async def stats():
    async with pool.acquire() as conn:
        total    = await conn.fetchval('SELECT COUNT(*) FROM domains')
        found    = await conn.fetchval('SELECT COUNT(*) FROM domains WHERE found=TRUE')
        by_proto = await conn.fetch("""
            SELECT protocol, COUNT(*) as count FROM domains
            WHERE found=TRUE GROUP BY protocol ORDER BY count DESC""")
        by_spec  = await conn.fetch("""
            SELECT spec, COUNT(*) as count FROM domains
            WHERE found=TRUE GROUP BY spec ORDER BY count DESC""")
    return {'total_domains_checked': total, 'total_found': found,
            'by_protocol': [dict(r) for r in by_proto],
            'by_spec':     [dict(r) for r in by_spec]}
