# VOX / Hermes Agent Guide

**Read this first.** Control tower · not day-trading edge · no AI slop.

## One command

```bash
cd ~/.hermes/scripts
python3 vox.py status|ops|prices|secrets|test|morning|advisor|compound
```

## Daily human path
1. **06:15** Morning research pack (local)
2. **07:45** Telegram **Ops Card** (Decision Object)
3. Breaking 09/12/16 if material
4. Execute ≤5 broker actions
5. Ask Hermes for X/`x_search` anytime

## Models
| Role | Stack |
|------|--------|
| Chat / research | **Grok 4.5 · xai-oauth** |
| X research | **`x_search`** (no X MCP required) |
| Batch scripts | DeepSeek via OpenRouter |
| Subagents | Kimi k2.6 |
| Councils | **Dead** |

## Data
| Source | Status |
|--------|--------|
| Secrets | Vault **Vox Hermes Vault** → env |
| Alpaca | Live US marks (price owner) |
| FMP free | Mega fund; mid = `fund=unknown` |
| Yahoo chart | History + global/crypto |

## Crons (Phase 4 allowlist)
**Telegram (3):** Ops Card · Breaking · Breaking weekend  

**Local:** morning · **k3-advisor** (soft) · · outside · brain-daily · obsidian · pricing held/EOD · etoro adapter · FMP · weekly-grade · health · housekeeper · compound · survival  

**Paused:** hybrid-full · brain-weekly · thesis-stubs · councils · master-data · price-history-sync · …

Monthly: `vox_cron_survival.py` fails if anything off-allowlist is enabled.

## Pipelines
```
vault→env → pricing_refresh (owner) → FMP free
  → morning + outside + brain (files)
  → Ops Card Decision Object (Telegram)
  → you execute → weekly compound (real breaks)
```

## Rules
- Multi-broker never a sell reason  
- Grades = hygiene only  
- Material SELL ≥2.5% AUM  
- Anti-chase; soft intel never ranks alone  
- fund=unknown when FMP missing  
- No new cron without allowlist + this file  

## Architecture
Phases 1–4 done. See `Architecture-Target-2026-07-16.md` · `Price-Owner-Phase2.md` · `Cron-Survival-LATEST.md`

## Ready
**YES — use daily.**
