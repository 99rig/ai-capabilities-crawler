"""Primo crawl reale — lista domini da testare."""
import asyncio
import sys
sys.path.insert(0, '/app')
import db
from crawler import crawl_domains

DOMAINS = [
    # Nostri
    'everywheredesign.it', 'pcbuster.it', 'mcpstandard.dev',
    # MCP noti
    'notion.so', 'linear.app', 'vercel.com',
    # ChatGPT Plugins
    'slack.com', 'zapier.com', 'shopify.com',
    # Big tech
    'google.com', 'github.com', 'openai.com',
    'anthropic.com', 'stripe.com', 'cloudflare.com',
    'atlassian.com', 'salesforce.com', 'hubspot.com',
    # E-commerce
    'woocommerce.com', 'magento.com', 'prestashop.com',
    # Dev tools
    'github.com', 'gitlab.com', 'bitbucket.org',
    # AI
    'cohere.com', 'mistral.ai', 'groq.com',
]

async def main():
    pool = await db.get_pool()
    await db.init_db(pool)

    print(f'Crawling {len(DOMAINS)} domains...')
    results = await crawl_domains(DOMAINS)

    for r in results:
        await db.upsert_result(pool, r)

    found = [r for r in results if r.found]
    print(f'\nDone: {len(found)}/{len(results)} found')
    for r in found:
        print(f'  ✅ {r.domain} [{r.protocol}/{r.spec}] via {r.discovery_method}')

    await pool.close()

asyncio.run(main())
