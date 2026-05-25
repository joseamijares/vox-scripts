# VOX System Cost Audit

## Current Monthly Costs

| Service | Tier | Cost/Month | Usage |
|---------|------|-----------|-------|
| **Polygon** | Starter (paid) | **$29** | Unlimited API calls, 15-min delayed |
| **OpenRouter** | Pay-as-you-go | **~$0-5** | Embeddings only (RAG) |
| **Vercel** | Hobby (free) | **$0** | Static sites, 100GB bandwidth |
| **Telegram Bot** | Free | **$0** | Unlimited messages |
| **ChromaDB** | Local | **$0** | Runs on your machine |
| **FMP** | Free tier | **$0** | 250 calls/day (not currently used) |
| **Hermes Cron** | Included | **$0** | Part of your setup |
| **TOTAL** | | **~$34/month** | |

## What Costs Money

### 1. Polygon API — $29/month (FIXED)
- You already pay this. It's a sunk cost.
- Used by: `vox_signal_enhancer.py` (options flow)
- **Worth it?** YES. You need market data.

### 2. OpenRouter — ~$0-5/month (VARIABLE)
- Used by: `vox_rag_system.py` (embeddings)
- Cost: ~$0.02 per 1K tokens embedded
- 119 vault files ≈ $0.50 to embed once
- Re-embedding monthly ≈ **$0.50/month**
- **Worth it?** YES. Negligible cost.

## What's FREE

| Component | Why Free |
|-----------|----------|
| AI Harness | Reads local JSON only |
| Autonomous Agent | Reads local JSON only |
| Self-Upgrade | Reads local JSON only |
| Signal Enhancer | Mostly local + Polygon (already paid) |
| Telegram Alerts | Bot API is free |
| Dashboard hosting | Vercel hobby tier |
| ChromaDB | Local vector DB |
| Cron jobs | Hermes built-in |

## Cost Optimization Options

### Option A: Keep Everything (Recommended)
**~$34/month**
- Full autonomous system
- Real-time alerts
- RAG intelligence
- Self-upgrading

### Option B: Disable RAG Embeddings
**~$29/month** (save $5)
- RAG page works with keyword search (no AI embeddings)
- Slightly less accurate semantic search
- Everything else stays the same

### Option C: Reduce Cron Frequency
**Same $34, less API usage**
- Change from every 15 min to every 1 hour
- Saves Polygon API calls (though unlimited on Starter)
- Less noise in Telegram

### Option D: Minimal Mode
**~$29/month**
- Keep: Harness + Agent + Telegram + Dashboard
- Disable: RAG embeddings, Signal enhancer cron
- Manual run signal enhancer when needed

## My Recommendation

**Keep Option A ($34/month).** Here's why:

1. **Polygon $29 is sunk cost** — you're already paying it
2. **OpenRouter is ~$0.50/month** — basically free
3. **Everything else is free**
4. **The system pays for itself** if it prevents one bad trade or catches one good one

Your portfolio is **$195K**. A 0.1% better decision = $195. The system costs $34/month.

**ROI breakeven: One 0.02% improvement per month.**

## What I Can Do Now

1. **Switch RAG to free local embeddings** (no OpenRouter cost)
2. **Add cost tracking** to the dashboard
3. **Add "cost per play" metric** so you see value
4. **Make signal enhancer manual-only** (not cron)

Want me to implement any of these?
