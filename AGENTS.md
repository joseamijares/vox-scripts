# VOX / Hermes Agent Guide

**Read this first.** Control tower · not day-trading edge · no AI slop.

## One command

```bash
cd ~/.hermes/scripts
python3 vox.py status|ops|prices|secrets|test|morning|compound
```

## Daily human path
1. **06:15** Morning research pack (local file → context)
2. **07:45** Telegram **Ops Card** (embeds morning snip)
3. Breaking 09/12/16 if material
4. Execute ≤5 broker actions
5. Ask Hermes for extra X/`x_search` anytime

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

## Crons (lean — final 2026-07-16)
**Telegram (3):** `vox-daily-ops-card` · `vox-intel-breaking` (9/12/16) · weekend breaking  

**Local pricing:** held-intraday + EOD (canonical) · hybrid grades · etoro 4h  
**Local intel files:** brain · outside · weekly-grade  
**Plumbing:** FMP · health · housekeeper · compound · thesis · survival · obsidian  

Paused: price-history-sync (redundant w/ EOD UPSERT), councils, signal packs, etc.

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

## Architecture (audit)
See Obsidian `system/Architecture-Target-2026-07-16.md`:
- Grades = hygiene filter only
- Ops Card = single Decision Object
- Soft intel never ranks alone
- Target: one price owner · Bucket A/B only · confidence badge
- Next build when asked: Phase 1 (Top-N inside Ops, fail closed)
