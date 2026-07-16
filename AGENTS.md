# VOX / Hermes Agent Guide

**Read this first.** Control tower · not day-trading edge · no AI slop.

## One command

```bash
cd ~/.hermes/scripts
python3 vox.py status|ops|prices|secrets|test|compound
```

## Daily human path
1. **Telegram:** Daily Ops Card (07:45 CT M–F) + Breaking only when material  
2. Execute ≤5 broker actions  
3. Dashboard for book truth  
4. Ask Hermes for X research (`x_search`) or deep dives on demand  

## Models
| Role | Stack |
|------|--------|
| Chat / research | **Grok 4.5 · xai-oauth** |
| X research | **`x_search`** (same stack; no X MCP required) |
| Batch scripts | DeepSeek v4 via OpenRouter |
| Subagents | Kimi k2.6 |
| Councils | **Dead** |

## Data
| Source | Status |
|--------|--------|
| Secrets | Vault **Vox Hermes Vault** → env |
| Alpaca | **Live keys OK** (dual-check / US marks) |
| FMP | Free mega; Starter optional mid-caps |
| Yahoo chart | Primary free prices / history UPSERT |

## Crons (lean — 2026-07-16)
**Telegram (3):** `vox-daily-ops-card` · `vox-intel-breaking` · `vox-intel-breaking-weekend`  

**Local:** brain, outside, grades, pricing×, hybrid, etoro, FMP, health, housekeeper, compound, thesis, survival, obsidian  

See `Obsidian/system/Cron-Audit-2026-07-16.md`.

## Pipelines
```
vault→env → prices → FMP free → brain/outside/breaking (files)
  → Ops Card (Telegram) → you execute → weekly compound (real breaks)
```

## Rules
- Multi-broker never a sell reason  
- Grades = hygiene  
- Material SELL ≥2.5% AUM  
- Anti-chase  
- Soft X intel never overrides book  
- No token-rotate nags unless you ask  

## Ready
**YES — use daily.** Optional: FMP Starter, merge price jobs later.
