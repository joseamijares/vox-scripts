# Vox Auto-Trading Research — JOS-24

## Executive Summary

**Recommendation: Use Lumibot framework + Alpaca broker for auto-trading.**

For Phase 1 (now): Manual alerts with our custom scripts.
For Phase 2 (next): Paper trade via Lumibot + Alpaca.
For Phase 3 (future): Live auto-trading with kill switches.

---

## Framework Comparison

| Framework | Stars | Options | Stocks | Crypto | Backtest | Live | AI Agents | Best For |
|-----------|-------|---------|--------|--------|----------|------|-----------|----------|
| **Lumibot** | 1.6k | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ Native | **Our use case** |
| Backtrader | 12k | ❌ | ✅ | Limited | ✅ | ✅ | ❌ | Stocks only, no options |
| Freqtrade | 40k | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ ML | Crypto only |
| Zipline | 18k | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | Research/Quantopian |
| Jesse | 5k | ❌ | ❌ | ✅ | ✅ | Paid | ❌ | Crypto only |
| Custom (ib_insync) | N/A | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | Max control, max work |

**Winner: Lumibot** — Only framework that supports ALL our needs:
- Options trading (single + multi-leg)
- Stocks, crypto, futures
- Same code for backtest → paper → live
- Built-in AI agent runtime (perfect for LLM Council!)
- Supports Alpaca, IBKR, Tradier, Schwab

---

## Broker Comparison for Auto-Trading

| Broker | Options API | Commission | Paper Trading | Python SDK | Best For |
|--------|-------------|------------|---------------|------------|----------|
| **Alpaca** | ✅ Full REST | $0.35/contract | ✅ Level 3 auto | alpaca-py | **Our use case** |
| IBKR | ✅ TWS API | $0.65/contract | ✅ | ib_insync | Large accounts |
| Tradier | ✅ REST | $0.35/contract | ✅ | Official | Options-focused |
| Schwab | ⚠️ Limited | $0.65/contract | ❌ | schwab-py | Manual preferred |

**Winner: Alpaca** for automation because:
- Pure REST API (no desktop app needed)
- Paper trading identical to live
- Level 3 options pre-approved on paper
- Best Python SDK documentation
- Commission-free stocks, cheap options

---

## Architecture Recommendation

```
┌─────────────────────────────────────────────────────────────┐
│                    VOX FINANCE COMMAND CENTER                │
├─────────────────────────────────────────────────────────────┤
│  DATA LAYER                                                 │
│  ├── Polygon.io (market data)                               │
│  ├── X API (sentiment, Trump tweets)                        │
│  └── Alpaca (broker data, positions)                        │
├─────────────────────────────────────────────────────────────┤
│  INTELLIGENCE LAYER (Our Scripts)                           │
│  ├── Grade System (0-100 scoring)                           │
│  ├── Position Sizer (Kelly + risk)                          │
│  ├── Trump Tracker (policy alerts)                          │
│  └── Swing Screener (setup finder)                          │
├─────────────────────────────────────────────────────────────┤
│  DECISION LAYER                                             │
│  ├── LLM Council (Claude + GPT + Grok debate)               │
│  └── Risk Gate (max loss/day, position limits)              │
├─────────────────────────────────────────────────────────────┤
│  EXECUTION LAYER (Lumibot)                                  │
│  ├── Paper Trading (Phase 2)                                │
│  └── Live Trading (Phase 3)                                 │
├─────────────────────────────────────────────────────────────┤
│  ALERT LAYER                                                │
│  ├── Telegram alerts (manual confirmation)                  │
│  └── One-click execute (Phase 2+)                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Manual Alerts (NOW — June 2026)
- Grade system generates scores
- Telegram alerts for Grade 85+ and Grade <50
- Jose executes manually
- Track in trade journal

### Phase 2: Paper Trading (July-August 2026)
- Set up Alpaca paper account
- Integrate Lumibot with our grade system
- Paper trade based on grades
- Validate performance vs backtests
- Build confidence in system

### Phase 3: Live Auto-Trading (September+ 2026)
- Fund Alpaca live account
- Start with $500/month DCA
- Auto-execute Grade 90+ with confirmation
- Kill switches: max 1 trade/day, max $2K risk/day
- Gradually increase automation

---

## Cost Analysis

| Item | Cost | Notes |
|------|------|-------|
| Alpaca paper trading | FREE | Level 3 options included |
| Alpaca live trading | FREE (stocks) | Options $0.35/contract |
| Polygon.io free tier | FREE | 5 calls/min (sufficient for alerts) |
| Polygon.io paid | $49/mo | 100 calls/min for live trading |
| Lumibot | FREE | Open source MIT license |
| OpenRouter/Grok | Pay-per-use | ~$0.01-0.10 per query |
| **Monthly total** | **~$50-100** | Mostly Polygon + API costs |

For $500/month capital + $1K trades:
- Options round trip (4 contracts): ~$2.80
- Stock trades: FREE
- Very cost-effective

---

## Risk Management (Non-Negotiable)

Before ANY auto-trading:

1. **Max daily loss**: $500 (1 day = 1 month's capital)
2. **Max position size**: $2,000 (10% of portfolio)
3. **Max open positions**: 5
4. **Options max**: $500 per options trade
5. **Kill switch**: Auto-pause after 2 consecutive losses
6. **Market conditions**: No new trades if VIX > 30
7. **Earnings blackout**: No trades 2 days before/after earnings

---

## Next Steps

1. **Jose**: Create Alpaca account + paper trading
2. **Vox**: Install Lumibot, test with paper account
3. **Vox**: Build alert system (JOS-26)
4. **Together**: Paper trade for 4-6 weeks
5. **Together**: Decide on live automation level

---

## GitHub Repos to Study

1. **Lumibot**: https://github.com/Lumiwealth/lumibot
   - `pip install lumibot`
   - Start with: `examples/options/` folder

2. **Alpaca Python SDK**: https://github.com/alpacahq/alpaca-py
   - `pip install alpaca-py`
   - Examples: `examples/options/`

3. **IBKR API (backup)**: https://github.com/ib-api-reloaded/ib_async
   - `pip install ib-async`
   - Only if Alpaca doesn't work out

4. **Our Vox System** (this repo):
   - `grade_system.py` → Lumibot strategy
   - `position_sizer.py` → Lumibot position sizing
   - `trump_tracker.py` → Lumibot macro filter
