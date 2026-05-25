#!/usr/bin/env python3
"""
Finance Research Runner — unified multi-source research for Hermes Agent.
Loads API keys from ~/.hermes/.env and orchestrates research across:
- Polygon (company profile, market data)
- Perplexity (AI-powered deep research)
- Firecrawl (web search)
- Exa (semantic search)
- Tavily (structured search)
- OpenRouter (AI synthesis with Claude/GPT)
- Composio CLI (1000+ app integrations)

Usage: python3 finance_research.py <TICKER>
Example: python3 finance_research.py NVDA
"""
import os, sys, json, urllib.request, subprocess, textwrap

# ── Load keys from ~/.hermes/.env ─────────────────────────────────────
ENV_PATH = os.path.expanduser("~/.hermes/.env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if '=' in line and not line.startswith('#') and not line.startswith(' '):
                k, v = line.strip().split('=', 1)
                os.environ.setdefault(k, v)

# ── Config ────────────────────────────────────────────────────────────
POLYGON_KEY = os.environ.get("POLYGON_API_KEY", "")
PERPLEXITY_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
FIRECRAWL_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
EXA_KEY = os.environ.get("EXA_API_KEY", "")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
COMPOSIO_PATH = os.path.expanduser("~/.composio")

def polygon_profile(ticker):
    req = urllib.request.Request(
        f'https://api.polygon.io/v3/reference/tickers/{ticker}',
        headers={'Authorization': f'Bearer {POLYGON_KEY}'}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)['results']

def perplexity_research(query):
    req = urllib.request.Request(
        'https://api.perplexity.ai/chat/completions',
        data=json.dumps({
            'model': 'sonar',
            'messages': [{'role': 'user', 'content': query}],
            'max_tokens': 300
        }).encode(),
        headers={'Authorization': f'Bearer {PERPLEXITY_KEY}', 'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
        return d['choices'][0]['message']['content']

def firecrawl_search(query, limit=3):
    req = urllib.request.Request(
        'https://api.firecrawl.dev/v1/search',
        data=json.dumps({'query': query, 'limit': limit}).encode(),
        headers={'Authorization': f'Bearer {FIRECRAWL_KEY}', 'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get('data', [])

def exa_search(query, num=2):
    req = urllib.request.Request(
        'https://api.exa.ai/search',
        data=json.dumps({'query': query, 'numResults': num, 'type': 'auto'}).encode(),
        headers={'Authorization': f'Bearer {EXA_KEY}', 'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get('results', [])

def tavily_search(query, max_results=2):
    req = urllib.request.Request(
        'https://api.tavily.com/search',
        data=json.dumps({'query': query, 'api_key': TAVILY_KEY, 'max_results': max_results}).encode(),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get('results', [])

def openrouter_synthesize(prompt, model='anthropic/claude-sonnet-4'):
    req = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=json.dumps({
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'You are a senior equity analyst. Be concise and actionable.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 200
        }).encode(),
        headers={
            'Authorization': f'Bearer {OPENROUTER_KEY}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://hermes-agent.local',
            'X-Title': 'Hermes Finance Agent'
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
        return d['choices'][0]['message']['content']

def composio_execute(tool_slug, args_dict):
    """Execute a Composio tool via CLI."""
    env = os.environ.copy()
    env['PATH'] = f"{COMPOSIO_PATH}:{env.get('PATH', '')}"
    cmd = ['composio', 'execute', tool_slug, '-d', json.dumps(args_dict)]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {"error": result.stderr}

def composio_search(query, limit=5):
    """Search Composio tools."""
    env = os.environ.copy()
    env['PATH'] = f"{COMPOSIO_PATH}:{env.get('PATH', '')}"
    cmd = ['composio', 'search', query, '--limit', str(limit), '--human']
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    return result.stdout if result.returncode == 0 else result.stderr

# ── Main Research Orchestrator ────────────────────────────────────────
def research(ticker):
    print(f"\n{'='*60}")
    print(f"🚀 MULTI-SOURCE RESEARCH: {ticker}")
    print(f"{'='*60}")
    
    # 1. Polygon Profile
    print(f"\n📊 1. COMPANY PROFILE (Polygon)")
    try:
        p = polygon_profile(ticker)
        print(f"   Name: {p['name']}")
        print(f"   Market Cap: ${p.get('market_cap', 0)/1e9:.1f}B")
        print(f"   Employees: {p.get('total_employees', 'N/A'):,}")
        print(f"   Listed: {p.get('list_date', 'N/A')}")
        print(f"   Exchange: {p.get('primary_exchange', 'N/A')}")
    except Exception as e:
        print(f"   ❌ {e}")
    
    # 2. Perplexity Deep Research
    print(f"\n🔍 2. AI RESEARCH (Perplexity)")
    try:
        result = perplexity_research(
            f'What are the top 3 bullish and top 3 bearish factors for {ticker} stock? Be concise.'
        )
        for line in result.split('\n')[:8]:
            if line.strip():
                print(f"   {line[:75]}")
    except Exception as e:
        print(f"   ❌ {e}")
    
    # 3. Firecrawl News
    print(f"\n🌐 3. LATEST NEWS (Firecrawl)")
    try:
        results = firecrawl_search(f'{ticker} stock news today', 3)
        for i, item in enumerate(results, 1):
            title = item.get('title', 'N/A')[:60]
            print(f"   {i}. {title}...")
    except Exception as e:
        print(f"   ❌ {e}")
    
    # 4. Exa Semantic Search
    print(f"\n🧠 4. INVESTMENT THESIS (Exa)")
    try:
        results = exa_search(f'{ticker} investment thesis 2026', 2)
        for i, item in enumerate(results, 1):
            title = item.get('title', item.get('url', 'N/A'))[:60]
            print(f"   {i}. {title}...")
    except Exception as e:
        print(f"   ❌ {e}")
    
    # 5. Tavily Structured Search
    print(f"\n📰 5. EARNINGS & GUIDANCE (Tavily)")
    try:
        results = tavily_search(f'{ticker} earnings revenue guidance', 2)
        for i, item in enumerate(results, 1):
            title = item.get('title', 'N/A')[:60]
            print(f"   {i}. {title}...")
    except Exception as e:
        print(f"   ❌ {e}")
    
    # 6. Claude Synthesis
    print(f"\n🤖 6. AI SYNTHESIS (Claude via OpenRouter)")
    try:
        result = openrouter_synthesize(
            f'Based on current market conditions, give a 1-paragraph investment thesis for {ticker}. '
            f'Include rating (Buy/Hold/Sell), confidence 1-10, and key risk.'
        )
        wrapped = textwrap.fill(result, width=70, initial_indent='   ', subsequent_indent='   ')
        print(wrapped)
    except Exception as e:
        print(f"   ❌ {e}")
    
    print(f"\n{'='*60}")
    print(f"✅ RESEARCH COMPLETE: {ticker}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 finance_research.py <TICKER>")
        print("Example: python3 finance_research.py NVDA")
        sys.exit(1)
    
    ticker = sys.argv[1].upper()
    research(ticker)
