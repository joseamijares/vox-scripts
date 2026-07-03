# VOX Investment Intelligence System
## System Architecture & Documentation

**Version:** 2.1  
**Last Updated:** 2026-06-22  
**Author:** VOX AI (Hermes/Kimi)

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Database Schema](#database-schema)
3. [Grading Engine](#grading-engine)
4. [Cron Jobs](#cron-jobs)
5. [Stock Universe](#stock-universe)
6. [Watchlists](#watchlists)
7. [Investor Tracking](#investor-tracking)
8. [Recent Fixes](#recent-fixes)
9. [Deployment Log](#deployment-log)

---

## System Overview

VOX is a multi-layered investment intelligence system that grades stocks across technical, fundamental, and macro dimensions. It produces a unified grade (0-100) and action recommendation for each stock.

### Core Philosophy
- **Single Source of Truth:** `vox_grades` is the master table
- **Unified grades** mirror vox_grades directly (no blending)
- **Aggressive growth focus:** Targets 25-50% yearly returns
- **Thematic investing:** AI, quantum, nuclear, EM fintech, space

### Data Flow
```
yfinance / Alpha Vantage / Web Research
    ↓
vox_grades (algorithmic grading)
    ↓
unified_grades (direct mirror)
    ↓
RAG context layer → Recommendations
```

---

## Database Schema

### Primary Tables

#### `vox_grades` — Master Grading Table
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| ticker | VARCHAR(10) | Stock symbol |
| name | VARCHAR(100) | Company name |
| vox_grade | INTEGER | 0-100 composite score |
| previous_grade | INTEGER | Prior grade for comparison |
| action | VARCHAR(20) | STRONG_BUY / BUY / HOLD / WEAK_HOLD / SELL |
| current_price | NUMERIC | Last price |
| technical_score | INTEGER | 0-100 technical analysis |
| fundamental_score | INTEGER | 0-100 fundamentals |
| macro_score | INTEGER | 0-100 macro environment |
| sector_score | INTEGER | 0-100 sector strength |
| generated_at | TIMESTAMP | Grade timestamp |

#### `sp500_grades` — S&P 500 Universe
| Column | Type | Description |
|--------|------|-------------|
| ticker | VARCHAR(10) | S&P 500 symbol |
| vox_grade | INTEGER | Grade for S&P 500 stock |
| computed_at | TIMESTAMP | Last computation |

#### `unified_grades` — Single Source of Truth
| Column | Type | Description |
|--------|------|-------------|
| ticker | VARCHAR(10) | Stock symbol |
| unified_grade | INTEGER | Final grade (direct vox copy) |
| action | VARCHAR(20) | Recommended action |
| vox_grade | INTEGER | Source grade |
| sp500_grade | INTEGER | S&P grade (if applicable) |
| contradiction | TEXT | Any grade mismatches |

#### `positions` — Portfolio Holdings
| Column | Type | Description |
|--------|------|-------------|
| ticker | VARCHAR(20) | Symbol (supports spaces) |
| grade | INTEGER | Current VOX grade |
| council | VARCHAR(20) | HOLD / BUY / SELL |
| brokers | TEXT[] | Broker list |
| live_value | NUMERIC | Position value |

#### `watchlist_entries` — Thematic Watchlists
| Column | Type | Description |
|--------|------|-------------|
| ticker | VARCHAR(10) | Symbol |
| list_name | VARCHAR(50) | Watchlist category |
| reason | TEXT | Why it's on the list |
| target_price | NUMERIC | Price target |
| source | VARCHAR(50) | Discovery source |

#### `investor_tracking` — Smart Money Tracking
| Column | Type | Description |
|--------|------|-------------|
| investor_name | VARCHAR(100) | Investor/institution |
| ticker | VARCHAR(10) | Symbol |
| action | VARCHAR(20) | BUY / SELL / HOLD |
| shares | NUMERIC | Position size |
| value | NUMERIC | Dollar value |
| date | TIMESTAMP | Transaction date |
| source | VARCHAR(100) | Filing/source |

#### `pattern_alerts` — Technical Pattern Detection
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | GENERATED ALWAYS AS IDENTITY |
| ticker | VARCHAR(10) | Symbol |
| pattern_type | VARCHAR(50) | Pattern name |
| conviction | INTEGER | 0-100 confidence |
| detected_at | TIMESTAMP | Detection time |

---

## Grading Engine

### Grade Formula (v2.1)
```
vox_grade = 0.40 * technical_score + 0.35 * fundamental_score + 0.25 * macro_score
```

### Score Ranges
| Grade | Action | Meaning |
|-------|--------|---------|
| 80-100 | STRONG_BUY | Exceptional opportunity |
| 65-79 | BUY | Good opportunity |
| 50-64 | HOLD | Neutral, keep watching |
| 35-49 | WEAK_HOLD | Deteriorating, consider exit |
| 0-34 | SELL | Exit position |

### Technical Score Components
- Price vs 50 SMA / 200 SMA
- 30-day momentum
- RSI levels
- Volume trends
- 52-week range position

### Fundamental Score Components
- P/E ratio (trailing & forward)
- Revenue growth (YoY)
- Profit margins
- Debt/equity ratio
- ROE / ROA

### Macro Score Components
- Sector tailwinds (AI, quantum, nuclear = higher)
- Interest rate environment
- Geopolitical risk
- Commodity prices (for energy/materials)

---

## Cron Jobs

| Job ID | Name | Schedule | Purpose | Status |
|--------|------|----------|---------|--------|
| eb50e71aee2a | vox-unified-rebuilder | Daily 8:00 AM CT | Rebuild unified grades from vox_grades | ✅ Active |
| 84ccf3a36b9e | grade-improvement-alert | Daily 2:00 PM CT | Alert on grade improvements | ✅ Active |
| cb8d50ff2e38 | market-monitor | Daily 9:00 AM CT | Market open monitoring | ✅ Active |
| a39dd7d39aac | vox-daily-health-check | Daily 6:00 AM CT | System health validation | ✅ Fixed |
| ca4917b4aa02 | vox-pattern-scanner | Daily 7:00 AM CT | Technical pattern detection | ✅ Fixed |
| c58bdd581376 | vox-regrade-sp500-weekly | Sundays 4:00 AM CT | Re-grade all 503 S&P 500 stocks | ✅ New |
| 857122e105ed | vox-broker-reminder-friday | Fridays 9:00 AM CT | Remind Jose to send broker statements | ✅ Active |
| ... | ... | ... | ... | ... |
| **Total: 41 crons** | | | | |

---

## Stock Universe

### Coverage
- **Total unique tickers:** 1,349
- **vox_grades records:** 13,696
- **S&P 500 covered:** 503
- **Positions tracked:** 72
- **Unified grades:** 1,348

### Thematic Sectors
| Sector | Tickers | Description |
|--------|---------|-------------|
| Quantum Computing | IONQ, QBTS, RGTI, QUBT, QSI | Pure-play quantum |
| Nuclear / SMR | OKLO, SMR, CEG, BWXT, NNE | Small modular reactors |
| Hydrogen / Clean Energy | PLUG, BE, CLNE, ICLN, NEE | Green hydrogen, fuel cells |
| Space | RKLB, ASTS, SPIR, RDW | Launch, satellites |
| AI Infrastructure | VRT, APLD, NBIS, COHR | Data center power, cooling |
| EM Fintech | MELI, STNE, PAGS, DLO, SE | LatAm, Asia payments |
| Cybersecurity | CRWD, S, NET, FTNT | Endpoint, network security |
| Biotech / Gene Editing | NTLA, EDIT, BEAM, VRTX, CRSP | CRISPR, precision medicine |
| Crypto Infrastructure | MSTR, COIN, CLSK, WULF | Bitcoin, mining, exchanges |
| Autonomous / Robotics | AUR, LIDR, MBLY, SERV | Self-driving, LiDAR |
| Defense / Geopolitical | LMT, RTX, NOC, BA | Aerospace, missiles |
| Uranium / Energy Transition | CCJ, URA, LEU, DNN | Nuclear fuel, mining |
| Rare Earths / Critical Minerals | MP, LYSCF, REMX | Magnet materials |
| AI Memory / Semiconductors | MU, NVDA, AMD, AVGO | DRAM, GPUs, custom silicon |
| EM E-commerce | PDD, BABA, JD, TCEHY | China, Asia online retail |

---

## Watchlists

### Active Watchlists (19)
| Watchlist | Count | Focus |
|-----------|-------|-------|
| nuclear_leaders | 3 | SMR, nuclear power |
| crypto_leaders | 2 | Bitcoin, exchanges |
| em_fintech | 2 | Emerging market payments |
| hydrogen_watch | 2 | Fuel cells, green H2 |
| quantum_watch | 2 | D-Wave, Rigetti |
| quantum_leaders | 1 | IONQ (pure-play) |
| fintech_disruption | 1 | HOOD |
| ai_infrastructure | 1 | VRT |
| autonomous_watch | 1 | AUR |
| rare_earths | 1 | MP |
| space_watch | 1 | ASTS |
| clean_energy | 1 | NEE |
| uranium_leaders | 1 | CCJ |
| cybersecurity | 1 | CRWD |
| ai_power | 1 | GE |
| ai_memory | 1 | MU |
| space_leaders | 1 | RKLB |
| defense_leaders | 1 | LMT |
| em_ecommerce | 1 | PDD |

---

## Investor Tracking

### Tracked Investors (9)
| Investor | Positions | Style |
|----------|-----------|-------|
| Cathie Wood ARK | 10 | Disruptive innovation, high growth |
| Jose Mijares | 5 | Aggressive, thematic, 25-50% targets |
| Warren Buffett | 4 | Value, dividend, moats |
| Chamath Palihapitiya | 3 | SPACs, fintech, space |
| David Tepper | 3 | Hedge fund, tech mega-caps |
| Stanley Druckenmiller | 3 | Macro, growth, mega-caps |
| Nancy Pelosi | 2 | Tech, AI (congressional trades) |
| Bill Ackman | 2 | Concentrated, activist |
| Michael Burry | 2 | Contrarian, value |

---

## Recent Fixes

### 2026-06-22 — Major System Update

#### 1. pattern_alerts.id Fix
- **Problem:** `pattern_alerts` table had broken SERIAL — inserts failed
- **Fix:** `ALTER TABLE pattern_alerts ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY`
- **Status:** ✅ Verified — test inserts working

#### 2. NAFTRAC ISHRS Position Fix
- **Problem:** `$0 value` position triggering health check alert
- **Fix:** Set `live_price = avg_cost`, `live_value = shares × avg_cost`
- **Result:** ~$772 MXN value now recorded

#### 3. S&P 500 Regrade Cron
- **Problem:** Stale S&P 500 grades (4 days old)
- **Fix:** Created `vox-regrade-sp500-weekly` (Sundays 4 AM CT)
- **Status:** 503 tickers, weekly refresh

#### 4. Unified Pipeline v2 (Single Source of Truth)
- **Problem:** Competing systems causing contradictions (IONQ 90→55→83)
- **Fix:** `unified_grades = direct copy of vox_grades ONLY`
- **Removed:** watchlist/sp500 blending
- **Result:** 0 inflation, 0 mismatches, 1,345 records

#### 5. Mass Re-Grading
- **Scope:** 79 priority stocks re-graded with updated algorithm
- **New algorithm:** Better technical momentum weighting, sector-adjusted macro scores
- **Top grades:** DUOL (86), QLYS (82), ESTC (80), TSM (77)

#### 6. Universe Expansion
- **Added:** 3 new tickers (SERV, URA, REMX)
- **Confirmed:** 61 thematic tickers already existed
- **Total universe:** 1,349 unique tickers

#### 7. Watchlist & Investor Tracking
- **New tables:** `watchlist_entries`, `investor_tracking`
- **Watchlists:** 19 thematic lists, 25 entries
- **Investors:** 9 tracked, 34 position records

---

## Deployment Log

| Date | Change | Status |
|------|--------|--------|
| 2026-06-21 | Unified pipeline v2 (SSOT) | ✅ Deployed |
| 2026-06-21 | Grade improvement alert cron | ✅ Deployed |
| 2026-06-22 | pattern_alerts id fix | ✅ Deployed |
| 2026-06-22 | NAFTRAC ISHRS position fix | ✅ Deployed |
| 2026-06-22 | S&P 500 regrade weekly cron | ✅ Deployed |
| 2026-06-22 | Mass re-grading (79 stocks) | ✅ Deployed |
| 2026-06-22 | Universe expansion | ✅ Deployed |
| 2026-06-22 | Watchlist system | ✅ Deployed |
| 2026-06-22 | Investor tracking | ✅ Deployed |
| 2026-06-22 | Documentation update | ✅ This file |

---

## User Preferences

| Preference | Value |
|------------|-------|
| Risk tolerance | Aggressive / Speculative |
| Target return | 25-50% yearly |
| Rejected sectors | Utilities, REITs, consumer staples (PG, KO, VZ, JNJ) |
| Preferred themes | AI, quantum, nuclear, hydrogen, EM fintech, space |
| Grade threshold | 60+ for consideration, 70+ for aggressive plays |
| Output style | ONE consolidated message |
| Verification | Always query LIVE database, never rely on memory |
| Broker sync | Weekly Friday 9 AM reminder |

---

## Contact

**System:** VOX Investment Intelligence  
**Platform:** Hermes Agent (Nous Research) / Kimi  
**Database:** PostgreSQL on Railway (acela.proxy.rlwy.net:35577)  
**Scripts:** `/Users/jos/.hermes/scripts/vox_cron/`  
**Documentation:** This file

---

*End of Document — VOX System v2.1*
