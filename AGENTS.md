# VOX / Hermes Agent Guide

**Read this first.** Control tower, not day-trading edge.

## One command

```bash
cd ~/.hermes/scripts
python3 vox.py status      # health snapshot
python3 vox.py ops        # Daily Ops Card (Telegram-ready)
python3 vox.py prices     # refresh held prices
python3 vox.py secrets    # vault → env refresh
python3 vox.py test       # core smoke tests
```

## Source of truth

| Surface | Path / system |
|---------|----------------|
| Book | Railway Postgres `positions` |
| Prices | `price_history` + `positions.live_price/price_asof/day_chg_pct` |
| Secrets | 1Password vault **Vox Hermes Vault** → `vault_to_env.py` |
| Daily briefing | Obsidian `memory/brain/Daily-Ops-LATEST.md` + Telegram cron |
| Book plan | `Brain-LATEST.md` |
| New ideas | `Outside-Ideas-LATEST.md` |
| Dashboard | https://web-production-9e321.up.railway.app |

## Decision Telegram (only these)

1. `vox-daily-ops-card` (primary)
2. `vox-intel-breaking` (+ weekend)
3. `vox-outside-ideas`
4. `vox-portfolio-brain-daily` (+ weekly / weekly-grade)

Everything else → local plumbing.

## Rules (never violate)

- Multi-broker ownership is **never** a sell reason
- Grades = **hygiene**, not auto-trade
- Material SELL ≥ **2.5%** AUM (or junk ≥ ~$500)
- Anti-chase: don’t market-buy 3m≥50% / 1w≥12% runners
- Day% from **bars**, not broken Yahoo previousClose
- Secrets: **never** paste `ops_` tokens in chat

## Secrets

```bash
python3 vault_to_env.py --write --replace-env   # after changing vault items
# scripts: import hermes_secrets_bootstrap
```

`op` hangs after success → always use `op_wrap.py` / vault_to_env.

## Layout

```
~/.hermes/scripts/
  vox.py                    # CLI entry
  AGENTS.md                 # this file
  hermes_secrets_bootstrap.py
  vault_to_env.py
  op_wrap.py
  vox_cron/                 # active jobs only (prefer)
    vox_daily_ops_card.py
    vox_pricing_refresh*.py
    vox_portfolio_brain*.py
    vox_outside_ideas*.py
    vox_intel_*.py
    vox_fmp*.py
  _archive/                 # dead weight — do not run
```

## After changes

1. `python3 vox.py test`
2. `python3 vox.py ops`
3. Commit scripts if durable

## Product identity

Portfolio **operating system**: honest book, L/M/S, hygiene grades, outside ideas, dark dashboard.  
Not: signal pack theater, AI council spam, FOMO chase lists.
