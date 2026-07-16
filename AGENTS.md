# VOX / Hermes Agent Guide

**Read this first.** Control tower · not day-trading edge · no AI slop.

## One command

```bash
cd ~/.hermes/scripts
python3 vox.py status      # health snapshot
python3 vox.py ops         # Daily Ops Card
python3 vox.py prices      # refresh held prices
python3 vox.py secrets     # vault → env
python3 vox.py test        # smoke
python3 vox.py compound    # weekly real-issues loop (quiet if clean)
```

## Models (Hermes)

| Role | Provider | Model | Use |
|------|----------|-------|-----|
| **Main brain (this chat)** | xai-oauth | **grok-4.5** | Decisions, research synthesis, agent work |
| **Subagents** | kimi-coding | kimi-k2.6 | Delegation children (config) |
| **VOX batch LLM** | OpenRouter | **deepseek/deepseek-v4-pro** (workhorse) | Cheap scripted analysis in `call_openrouter` |
| **OpenRouter Grok** | OpenRouter | x-ai/grok-4.3 / 4.5 | When scripts need Grok via OR |
| **Fallback** | not configured | — | Optional: enable openrouter fallback |

**Not used for decisions:** AI councils, multi-LLM vote theater, signal packs with negative edge.

### MCP
| Server | Status | Notes |
|--------|--------|-------|
| **x** (`@xdevplatform/xurl`) | **disabled** | Placeholder CLIENT_ID/SECRET — do not enable until real X OAuth |
| Grok MCP | **none installed** | Research via xai-oauth main model + web tools, not a separate MCP |

### Research with agents
- Main agent: **Grok 4.5** (xai-oauth) + web/browser tools  
- Batch/cost path: **DeepSeek v4-pro/flash** via OpenRouter in `vox_utils.call_openrouter`  
- Subagents: Kimi (delegation) — not for portfolio “councils”

## Source of truth

| Surface | Where |
|---------|--------|
| Book | Postgres `positions` |
| Prices | `price_history` + `live_price` / `price_asof` / `day_chg_pct` |
| Secrets | 1Password **Vox Hermes Vault** → `vault_to_env.py` |
| Daily briefing | `Daily-Ops-LATEST.md` + Telegram `vox-daily-ops-card` |
| Book plan | `Brain-LATEST.md` |
| New ideas | `Outside-Ideas-LATEST.md` |
| Dashboard | https://web-production-9e321.up.railway.app |
| This guide | `~/.hermes/scripts/AGENTS.md` |

## Pipelines (real)

```
[Secrets vault→env]
        ↓
[Prices: held intraday + EOD UPSERT + hybrid/eToro]
        ↓
[FMP free fund enrich — mega only]
        ↓
[Brain / Outside / Breaking / Weekly grade]
        ↓
[Daily Ops Card → Telegram]
        ↓
[You execute ≤5 actions]
        ↓
[Weekly compound: real issues only]
```

## Crons (~18 enabled)

**Telegram decision:** ops-card · breaking · outside-ideas · brain daily/weekly · weekly-grade  

**Local plumbing:** pricing held/EOD/history · hybrid · etoro · FMP · health · housekeeper · obsidian-compound · thesis · survival  

**Paused forever unless proven:** councils, signal packs, top10-claude theater, master-data spam, multi-intel noise.

## Councils / advisors / “agents”

| Name | Status |
|------|--------|
| AI council / LLM council | **Dead / archived** — do not revive |
| Claude double-layer | **Not running** as decision cron |
| Autonomous agent / commander | **Archived** |
| Advisors | **None** as separate bots — Hermes is the advisor |
| Skills (vox-*) | Optional load for deep work; Ops Card is daily path |

## Rules

- Multi-broker never a sell reason  
- Grades = hygiene only  
- Material SELL ≥2.5% AUM / junk ≥~$500  
- Anti-chase thresholds  
- Day% from bars not bad previousClose  
- Never paste `ops_` tokens in chat  

## Compound loop (real issues only)

See `vox_cron/vox_compound_loop.py` and Obsidian `system/Compound-Loop.md`.

Triggers that count as **real**:
- Health/pricing/secrets fail  
- Stale prices on material holdings  
- Cron job failed  
- Dashboard API down  
- Book data integrity (ghost positions, AUM discontinuity)

**Not** real: new signal ideas, “should we add another LLM”, regime cosplay, influencer notes.

## Ready to use?

**YES** for daily control-tower use (Ops Card + dashboard + execute).  
Optional later: FMP Starter, fix Alpaca 401, enable X MCP with real keys, OpenRouter fallback.
