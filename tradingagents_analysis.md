# TradingAgents Deep Dive — Adaptation for Vox

**Repo:** https://github.com/TauricResearch/TradingAgents  
**Stars:** 78.6K | **License:** Apache-2.0 | **Language:** Python 3.13

---

## Architecture Overview

TradingAgents simulates a **professional trading firm** with 7 specialized LLM agents across 5 stages:

```
Stage I:   Analyst Team (4 parallel agents)
Stage II:  Research Team (Bull vs Bear debate)
Stage III: Trader Agent (timing & sizing)
Stage IV:  Risk Management (volatility, liquidity)
Stage V:   Fund Manager (approve & execute)
```

### Agent Roles

| Agent | Data Sources | Purpose |
|-------|-------------|---------|
| **Fundamental Analyst** | Company financials, SEC filings | Value assessment |
| **Sentiment Analyst** | Yahoo News, StockTwits, Reddit | Market mood |
| **News Analyst** | Global news, macro indicators | Event prediction |
| **Technical Analyst** | MACD, RSI, patterns | Price forecasting |
| **Bullish Researcher** | Analyst outputs | Highlight positives |
| **Bearish Researcher** | Analyst outputs | Highlight risks |
| **Trader** | Research consensus | Entry/exit timing |
| **Risk Manager** | Volatility, liquidity | Position sizing |
| **Fund Manager** | All above | Final approval |

---

## Key Innovations

1. **Structured + Natural Language Hybrid**
   - Analysts use structured reports (preserves data)
   - Researchers use natural dialogue (deeper reasoning)

2. **ReAct Prompting Framework**
   - All agents use reasoning + action loops
   - Transparent decision-making (explainable AI)

3. **Dual Model Strategy**
   - Quick-thinking models for data retrieval
   - Deep-thinking models for analysis/decisions
   - **GPU-free operation**

4. **Memory & Recovery**
   - Decision log: `~/.tradingagents/memory/trading_memory.md`
   - Fetches realized returns on next same-ticker run
   - Generates one-paragraph reflection

---

## Performance (Paper Results)

| Stock | Baseline | TradingAgents | Sharpe |
|-------|---------|---------------|--------|
| AAPL | 2.05% | **26.62%** | **8.21** |
| GOOGL | 7.78% | **24.36%** | **6.39** |
| AMZN | 17.1% | **23.21%** | **5.60** |

**Key:** Superior risk-adjusted returns with lower drawdowns.

---

## What We Can Adapt for Vox

### ✅ Immediate Wins

| Feature | TradingAgents Approach | Vox Adaptation |
|---------|----------------------|----------------|
| Multi-agent debate | Bull vs Bear researchers | **LLM Council v2** — expand our 3-model council to 5+ specialized agents |
| Structured reports | Analysts output JSON/markdown | **Grade system v2** — each pillar gets its own agent |
| Memory log | `trading_memory.md` with reflections | **Trade journal v2** — auto-reflect on past trades |
| Risk management | Dedicated risk agent | **Position sizer v2** — dynamic risk adjustment |
| Explainability | Natural language reasoning | **Alert v2** — detailed reasoning in every alert |

### 🔧 Technical Integration

**TradingAgents uses:**
- LangGraph for agent orchestration
- Multiple LLM providers (OpenAI, Anthropic, Google, xAI, DeepSeek, etc.)
- Alpha Vantage for market data
- Docker for deployment

**Vox already has:**
- ✅ OpenRouter (multi-model access)
- ✅ Polygon.io (market data)
- ✅ Alpaca (broker integration)
- ✅ Cron jobs (scheduling)

**Gap:** TradingAgents uses LangGraph — we'd need to add it or build our own orchestration.

---

## Installation for Vox

```bash
# Option 1: Full install (heavy)
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
pip install .

# Option 2: Docker
cp .env.example .env  # add API keys
docker compose run --rm tradingagents

# Option 3: Study-only (what we did)
git clone --depth 1 https://github.com/TauricResearch/TradingAgents.git
# Read code, adapt patterns to Vox
```

---

## Recommendation

**Don't install TradingAgents directly** — it's a research framework, not production-ready for our use case.

**Instead:**
1. ✅ **Adopt its architecture** — 5-stage pipeline with specialized agents
2. ✅ **Use its prompting patterns** — ReAct framework, structured outputs
3. ✅ **Build v2 of our LLM Council** — Expand from 3 to 5+ agents
4. ✅ **Add memory/reflection** — Auto-learn from past trades
5. ❌ **Don't use its data layer** — We have Polygon + Alpaca already

---

## Next Steps for Vox

1. **LLM Council v2** — Add Fundamental, Technical, Sentiment, Risk agents
2. **Grade System v2** — Each pillar gets dedicated agent reasoning
3. **Trade Journal v2** — Auto-reflection with realized returns
4. **Memory System** — Persistent learning from decisions
