# VOX / Hermes Agent Guide

**Read this first.** Control tower · not day-trading edge · no AI slop.

## One command

```bash
cd ~/.hermes/scripts
python3 vox.py status|ops|prices|secrets|test|morning|advisor|bakeoff|compound|log|help

# Soft advisor (never Ops SSOT)
python3 vox.py advisor                  # Kimi k3 — DeepSeek fallback if 403
python3 vox.py advisor --model sonnet5  # best hard critique (bakeoff winner)
python3 vox.py advisor --model glm52    # draft only
python3 vox.py advisor --model all
python3 vox.py bakeoff                  # full A/B rubric

# Decision log (you execute — JOS-269)
python3 vox.py log
python3 vox.py log did "ACTION" --ticker TICKER --broker BROKER
python3 vox.py log thesis TICKER --side long|short
```

## Daily human path
1. **06:15** Morning research pack (local)
2. **07:45** Telegram **Ops Card** (Decision Object)
3. `python3 vox.py log` — seed decision log from Ops
4. Breaking 09/12/16 if material
5. Execute ≤5 broker actions → `vox.py log did …` + thesis on material/short
6. Ask Hermes for X/`x_search` anytime
7. Hard review: `vox.py advisor --model sonnet5` (optional)
8. **Sunday ~08:00 CT** broadcast bot **Weekly Monitor**
9. Radar Board = panels only — **not** a decision council; Ops Decision Object stays SSOT

## Models
| Role | Stack |
|------|--------|
| Chat / research | **Grok 4.5 · xai-oauth** |
| X research | **`x_search`** (no X MCP required) |
| Soft advisor **cron** | **Kimi Coding `k3`** (KIMI_API_KEY) M/W/F |
| Soft advisor **hard** | **Claude Sonnet 5** via OpenRouter on demand |
| Soft advisor draft | GLM 5.2 via OpenRouter — never sole |
| Subagents | Kimi Coding **k3** |
| Batch scripts | DeepSeek via OpenRouter (pinned) |
| Councils / openrouter auto | **Dead** for decisions |

**Bakeoff 2026-07-20:** Sonnet5 > k3 > GLM5.2. Keep k3 cron; Sonnet for hard critique.

## Data
| Source | Status |
|--------|--------|
| Secrets | Vault **Vox Hermes Vault** → env |
| Alpaca | Live US marks (price owner) |
| FMP free | Mega fund; mid = `fund=unknown`; **news endpoint often 402** |
| Finnhub | Earnings calendar + general/company news (morning + radar) |
| Yahoo chart | History + global/crypto + MXN FX |
| Breaking | Google News RSS + DeepSeek distill (09/12/16 CT) |
| MXN (NAFTRAC) | Live MXNUSD; day% native bars; USD marks |

## Crons (Phase 4 allowlist)
**Telegram Hermes (3):** Ops Card · Breaking · Breaking weekend  

**Telegram broadcast bot (1):** `vox-weekly-monitor` — Sunday AUM + best plays + Radar snips via `TELEGRAM_BROADCAST_*`

**Local:** morning · **radar-board** · **intel-ingest/distill** · **earnings-desk** · **k3-advisor** (soft) · outside · brain-daily · obsidian · pricing held/EOD · etoro adapter · **binance+bitso daily** · FMP · weekly-grade · health · housekeeper · compound · survival  

**Paused:** hybrid-full · brain-weekly · thesis-stubs · councils · master-data · price-history-sync · …

Monthly: `vox_cron_survival.py` fails if anything off-allowlist is enabled.

## Pipelines
```
vault→env → pricing_refresh (owner) → FMP free
  → radar-board + **intel-ingest → distill** + morning + outside + brain
  → **earnings-desk** (report window)
  → k3 soft advisor (M/W/F local)
  → Ops Card Decision Object (Telegram)  # EVENT earnings + Intel snip + AI veto
  → you execute → weekly compound (real breaks)
  → Sun weekly-monitor broadcast (pulls Radar A–E + digest)
```

## Rules
- Multi-broker never a sell reason  
- Grades = hygiene only (low grade ≠ auto-sell)  
- Material SELL ≥2.5% AUM  
- Anti-chase; soft intel never ranks alone  
- fund=unknown when FMP missing  
- Soft advisor never overrides Ops / price owner  
- No new cron without allowlist + this file  

## Architecture
Phases 1–5 done. Dashboard `/architecture` · `Price-Owner-Phase2.md` · bakeoff LATEST in brain.

## Ready
**YES — use daily.**
