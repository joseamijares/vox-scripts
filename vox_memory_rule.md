# VOX DATA INTEGRITY RULE — PERMANENT

## THE PROBLEM
I keep giving inconsistent portfolio totals because I:
- Calculate on the fly instead of reading actual data
- Derive totals by summing positions (which are aggregated across brokers, causing duplicates)
- Forget confirmed broker values between sessions
- Use stale data without checking freshness

## THE SOLUTION
**dashboard_positions.json is the ONLY source of truth.**

### Broker-Confirmed Values (from you):
| Broker | Value | Status |
|--------|-------|--------|
| eToro | $84,937 | ✅ LIVE |
| GBM Main | 1,292,571.72 MXN (~$74,672) | ⚠️ STALE |
| GBM USA | $14,932 | ⚠️ STALE |
| Schwab | $1,630 | ✅ LIVE |
| IBKR | $1,260 | ⚠️ STALE |
| Binance | $20,146 | ✅ LIVE |
| Bitso | 4,175.83 MXN (~$241) | ✅ LIVE |
| **TOTAL** | **$197,818** | **3 stale** |

### MXN/USD Rate
- Current: ~17.31 (check daily)
- GBM values stored in MXN, must convert to USD for totals

## RULES I MUST FOLLOW

1. **NEVER derive total by summing positions** — positions are aggregated and have duplicates
2. **ALWAYS use broker_breakdown.total for AUM** — this is the confirmed value
3. **ALWAYS check data freshness** — stale brokers flagged in broker_status
4. **ALWAYS run validate() before analysis** — forces me to read actual data
5. **NEVER hallucinate portfolio values** — if file missing, say so

## MANDATORY PROCEDURE

Before ANY portfolio analysis:
```python
from vox_data_integrity import validate, get_truth

# Step 1: Validate (prints summary, saves log)
truth = validate()

# Step 2: Use ONLY these values
total_aum = truth['total_aum']  # $197,818.36
positions = truth['positions']   # 141 positions
broker_values = truth['broker_breakdown']  # Per-broker confirmed
```

## CONSEQUENCES OF BREAKING THIS RULE
- Inconsistent recommendations
- Wrong position sizing
- Bad trade decisions
- Loss of trust

## REMINDER
When user says "review in depth" or asks about portfolio:
1. Run validate() FIRST
2. Use truth['total_aum'] for all totals
3. Flag stale data
4. Never calculate totals myself
