#!/usr/bin/env python3
"""
VOX Agent Cost Monitor
Tracks API spending across all agents and data sources.
Sources: Polygon.io, Finnhub, OpenWeather, News APIs, LLM calls
Free sources: Open-Meteo, TradingEconomics, RSS feeds
"""

import json, os, re
from pathlib import Path
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
COST_LOG = SCRIPT_DIR / "vox_cost_log.json"

# Cost per API call (USD)
API_COSTS = {
    "polygon": {
        "prev_day": 0.0001,      # $0.0001 per aggregate call
        "ticker_details": 0.0001,
        "news": 0.0001,
        "grouped_daily": 0.0001,
        "free_tier_limit": 5,     # 5 calls/minute free
        "monthly_limit": 100000,  # 100K calls/month free on basic plan
    },
    "finnhub": {
        "quote": 0.0,             # Free tier
        "news": 0.0,              # Free tier
        "congressional": 0.0,     # Free tier
        "monthly_limit": 60,      # 60 calls/minute free
    },
    "openweather": {
        "current": 0.0,           # Free tier (1000 calls/day)
        "forecast": 0.0,          # Free tier
        "daily_limit": 1000,
    },
    "open_meteo": {
        "forecast": 0.0,          # Completely free, no limits
    },
    "tradingeconomics": {
        "scrape": 0.0,            # Free web scraping
    },
    "rss_feeds": {
        "fetch": 0.0,             # Free RSS
    },
    "llm": {
        "claude_haiku": 0.00025,  # $0.25 per 1M input tokens
        "claude_sonnet": 0.003,   # $3 per 1M input tokens
        "gpt4o_mini": 0.00015,    # $0.15 per 1M input tokens
        "per_call_estimate": 0.005, # Rough estimate per LLM-enhanced alert
    }
}

# Agent definitions with their API usage
AGENTS = {
    "vox_weather_agent": {
        "apis": [("open_meteo", "forecast", 10)],  # 10 regions
        "llm_calls": 0,
        "frequency_per_day": 6,  # every 4h
    },
    "vox_geopolitical_agent": {
        "apis": [("rss_feeds", "fetch", 3)],  # 3 RSS feeds
        "llm_calls": 0,
        "frequency_per_day": 6,
    },
    "vox_supply_chain_agent": {
        "apis": [
            ("polygon", "prev_day", 9),   # 9 commodity futures
            ("polygon", "prev_day", 7),   # 7 supply chain equities
            ("tradingeconomics", "scrape", 6),  # 6 TE commodities
        ],
        "llm_calls": 0,
        "frequency_per_day": 6,
    },
    "vox_macro_agent": {
        "apis": [("polygon", "prev_day", 3)],  # VIX, 10Y, DXY
        "llm_calls": 0,
        "frequency_per_day": 6,
    },
    "vox_sector_agent": {
        "apis": [("polygon", "prev_day", 11)],  # 11 sector ETFs
        "llm_calls": 0,
        "frequency_per_day": 6,
    },
    "vox_trump_agent": {
        "apis": [("rss_feeds", "fetch", 2)],
        "llm_calls": 0,
        "frequency_per_day": 6,
    },
    "vox_reddit_agent": {
        "apis": [],  # Web scraping
        "llm_calls": 0,
        "frequency_per_day": 6,
    },
    "vox_x_agent": {
        "apis": [],  # Web scraping / cached
        "llm_calls": 0,
        "frequency_per_day": 6,
    },
    "vox_research_orchestrator": {
        "apis": [
            ("polygon", "prev_day", 50),  # Portfolio prices
            ("finnhub", "quote", 50),
        ],
        "llm_calls": 1,  # One LLM call per run for analysis
        "frequency_per_day": 6,
    },
    "vox_smart_alerts": {
        "apis": [
            ("polygon", "prev_day", 52),  # All positions
            ("polygon", "news", 10),
        ],
        "llm_calls": 1,
        "frequency_per_day": 3,  # 9/12/15 CT
    },
    "vox_premarket": {
        "apis": [
            ("polygon", "prev_day", 52),
            ("polygon", "grouped_daily", 1),
        ],
        "llm_calls": 1,
        "frequency_per_day": 1,
    },
    "vox_broker_sync": {
        "apis": [("polygon", "prev_day", 52)],
        "llm_calls": 0,
        "frequency_per_day": 2,
    },
}

def calculate_daily_cost():
    """Calculate estimated daily API cost."""
    total_cost = 0.0
    agent_costs = {}
    
    for agent_name, config in AGENTS.items():
        agent_cost = 0.0
        
        # API calls
        for api_name, endpoint, count in config["apis"]:
            cost_per_call = API_COSTS.get(api_name, {}).get(endpoint, 0)
            daily_calls = count * config["frequency_per_day"]
            api_cost = daily_calls * cost_per_call
            agent_cost += api_cost
        
        # LLM calls
        if config["llm_calls"] > 0:
            llm_cost = config["llm_calls"] * config["frequency_per_day"] * API_COSTS["llm"]["per_call_estimate"]
            agent_cost += llm_cost
        
        agent_costs[agent_name] = agent_cost
        total_cost += agent_cost
    
    return total_cost, agent_costs

def load_cost_history():
    """Load historical cost data."""
    if COST_LOG.exists():
        with open(COST_LOG) as f:
            return json.load(f)
    return {"entries": [], "total_all_time": 0.0}

def save_cost_history(history):
    """Save cost history."""
    with open(COST_LOG, 'w') as f:
        json.dump(history, f, indent=2)

def run_cost_monitor():
    """Main cost monitoring function."""
    daily_cost, agent_costs = calculate_daily_cost()
    monthly_cost = daily_cost * 30
    yearly_cost = daily_cost * 365
    
    # Load history
    history = load_cost_history()
    
    # Add today's entry
    entry = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "daily_cost_usd": round(daily_cost, 4),
        "agent_breakdown": {k: round(v, 6) for k, v in agent_costs.items()},
        "total_api_calls": sum(count * cfg["frequency_per_day"] for cfg in AGENTS.values() for _, _, count in cfg["apis"]),
    }
    
    # Update history (keep last 30 days)
    history["entries"] = [e for e in history["entries"] if e["date"] >= (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")]
    history["entries"].append(entry)
    history["total_all_time"] = round(history.get("total_all_time", 0) + daily_cost, 4)
    
    save_cost_history(history)
    
    # Build output
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "daily_cost_usd": round(daily_cost, 4),
        "monthly_estimate_usd": round(monthly_cost, 2),
        "yearly_estimate_usd": round(yearly_cost, 2),
        "total_all_time_usd": history["total_all_time"],
        "agent_breakdown": {k: round(v, 6) for k, v in agent_costs.items()},
        "free_sources": ["Open-Meteo", "TradingEconomics", "RSS Feeds", "Finnhub (free tier)"],
        "paid_sources": ["Polygon.io"],
        "recommendations": []
    }
    
    # Recommendations
    if monthly_cost > 50:
        output["recommendations"].append("Consider Polygon.io paid plan for higher rate limits")
    if monthly_cost > 100:
        output["recommendations"].append("Review agent frequency — some may run too often")
    
    # Save snapshot
    with open(SCRIPT_DIR / "vox_cost_snapshot.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    # Print summary (always print this one, it's useful)
    print(f"💰 VOX COST MONITOR")
    print(f"   Daily: ${daily_cost:.4f} | Monthly: ${monthly_cost:.2f} | Yearly: ${yearly_cost:.2f}")
    print(f"   All-time: ${history['total_all_time']:.4f}")
    
    # Show top spenders
    sorted_agents = sorted(agent_costs.items(), key=lambda x: x[1], reverse=True)
    if sorted_agents[0][1] > 0:
        print(f"   Top costs:")
        for name, cost in sorted_agents[:3]:
            if cost > 0:
                print(f"      {name}: ${cost:.4f}/day")
    else:
        print(f"   All agents using free tier — $0 cost")
    
    return output

if __name__ == "__main__":
    run_cost_monitor()
