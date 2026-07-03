#!/usr/bin/env python3
"""
VOX shared utilities: DB access, fresh technical scoring, OpenRouter calls, cost logging.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import subprocess
import json
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERMES_HOME = Path.home() / ".hermes"
SCRIPT_DIR = HERMES_HOME / "scripts" / "vox_cron"
CACHE_DIR = SCRIPT_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR = HERMES_HOME / "cron" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load 1Password service account token for headless cron runs if available.
_SERVICE_ACCOUNT_FILE = HERMES_HOME / "secrets" / "1password_service_account"
if _SERVICE_ACCOUNT_FILE.exists() and not os.getenv("OP_SERVICE_ACCOUNT_TOKEN"):
    with open(_SERVICE_ACCOUNT_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _value = _line.split("=", 1)
                if _key == "OP_SERVICE_ACCOUNT_TOKEN" and _value.startswith("ops_"):
                    os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = _value
                    break


def load_env():
    """Load secrets from ~/.hermes/.env as fallback."""
    env_path = HERMES_HOME / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key, value)


def get_secret_1password(item: str, field: str, vault: str = "Vox Hermes") -> Optional[str]:
    """Read a secret from 1Password CLI. Returns None if not available."""
    try:
        result = subprocess.run(
            ["op", "item", "get", item, "--vault", vault, "--field", field, "--reveal"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_secret(item: str, field: str, env_var: Optional[str] = None, vault: str = "vox Hermes") -> Optional[str]:
    """
    Read a secret from 1Password first, then fall back to env var / .env.
    item: 1Password item name (e.g. 'OpenRouter')
    field: field name inside the item (e.g. 'api_key')
    env_var: fallback environment variable name (e.g. 'OPENROUTER_API_KEY')
    """
    value = get_secret_1password(item, field, vault)
    if value:
        return value
    if env_var:
        load_env()
        return os.getenv(env_var)
    return None


VALID_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


# ---------------------------------------------------------------------------
# LLM cost tracking
# ---------------------------------------------------------------------------
# Per-token pricing in USD. Override by setting OPENROUTER_PRICING_JSON in env.
_DEFAULT_PRICING = {
    "anthropic/claude-sonnet-5": {"input": 3.00, "output": 15.00},  # per 1M tokens
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "anthropic/claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "deepseek/deepseek-v4-pro": {"input": 0.80, "output": 1.20},
    "deepseek/deepseek-chat": {"input": 0.10, "output": 0.25},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


def _get_openrouter_pricing() -> Dict[str, Dict[str, float]]:
    """Load pricing from env JSON or use defaults."""
    env = os.environ.get("OPENROUTER_PRICING_JSON", "")
    if env:
        try:
            return json.loads(env)
        except Exception:
            pass
    return _DEFAULT_PRICING


def _db_password() -> str:
    pw = get_secret("Railway DB", "password", "DB_PASSWORD")
    if not pw:
        load_env()
        pw = os.environ.get("DB_PASSWORD", os.environ.get("PGPASSWORD", ""))
    return pw


def _ensure_llm_cost_table():
    """Create the vox_llm_costs table if it doesn't exist."""
    pw = _db_password()
    if not pw:
        return
    env = os.environ.copy()
    env["PGPASSWORD"] = pw
    subprocess.run([
        "psql", "-h", "acela.proxy.rlwy.net", "-p", "35577",
        "-U", "postgres", "-d", "railway", "-c", """
            CREATE TABLE IF NOT EXISTS vox_llm_costs (
                id SERIAL PRIMARY KEY,
                run_at TIMESTAMP NOT NULL DEFAULT NOW(),
                script_name TEXT,
                model TEXT NOT NULL,
                prompt_tokens INT NOT NULL DEFAULT 0,
                completion_tokens INT NOT NULL DEFAULT 0,
                total_tokens INT NOT NULL DEFAULT 0,
                input_cost NUMERIC(12,8),
                output_cost NUMERIC(12,8),
                total_cost NUMERIC(12,8),
                request_id TEXT,
                notes TEXT
            )
        """
    ], capture_output=True, text=True, env=env)


def log_llm_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    script_name: str = "",
    request_id: str = "",
    notes: str = "",
) -> Dict[str, float]:
    """Compute and record OpenRouter cost for a completion. Returns cost breakdown."""
    _ensure_llm_cost_table()
    pricing = _get_openrouter_pricing()
    p = pricing.get(model, pricing.get("anthropic/claude-sonnet-5", {"input": 3.00, "output": 15.00}))
    input_cost = (prompt_tokens / 1_000_000) * p["input"]
    output_cost = (completion_tokens / 1_000_000) * p["output"]
    total_cost = input_cost + output_cost

    pw = _db_password()
    if pw:
        env = os.environ.copy()
        env["PGPASSWORD"] = pw
        subprocess.run([
            "psql", "-h", "acela.proxy.rlwy.net", "-p", "35577",
            "-U", "postgres", "-d", "railway", "-c",
            f"""
            INSERT INTO vox_llm_costs
                (run_at, script_name, model, prompt_tokens, completion_tokens, total_tokens,
                 input_cost, output_cost, total_cost, request_id, notes)
            VALUES
                (NOW(), '{script_name.replace("'", "''")}', '{model.replace("'", "''")}',
                 {int(prompt_tokens)}, {int(completion_tokens)}, {int(prompt_tokens + completion_tokens)},
                 {input_cost:.8f}, {output_cost:.8f}, {total_cost:.8f},
                 '{request_id.replace("'", "''")}', '{notes.replace("'", "''")}')
            """
        ], capture_output=True, text=True, env=env)

    return {
        "input_cost": round(input_cost, 8),
        "output_cost": round(output_cost, 8),
        "total_cost": round(total_cost, 8),
    }


def query_db(sql: str) -> List[Tuple]:
    """Execute SQL via psql and return tuples."""
    password = _db_password()

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    result = subprocess.run(
        [
            "psql", "-h", "acela.proxy.rlwy.net", "-p", "35577",
            "-U", "postgres", "-d", "railway", "-t", "-c", sql,
        ],
        capture_output=True, text=True, env=env,
    )

    if result.returncode != 0:
        print(f"SQL Error: {result.stderr}")
        return []

    lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    return [tuple(l.split("|")) for l in lines]


# ---------------------------------------------------------------------------
# Grades / technical analysis
# ---------------------------------------------------------------------------
def get_unified_grades(limit: int = 100) -> Dict[str, Dict]:
    """Fetch latest unified grades from DB, filtering to valid US equity tickers."""
    result = query_db(f"""
        SELECT DISTINCT ON (ticker) ticker, unified_grade, action, computed_at
        FROM unified_grades
        WHERE computed_at > NOW() - INTERVAL '24 hours'
        ORDER BY ticker, computed_at DESC
        LIMIT {limit * 3}
    """)
    grades = {}
    for row in result:
        t = row[0].strip().upper().replace("$", "")
        if not VALID_TICKER_RE.match(t):
            continue
        try:
            g = int(row[1])
        except Exception:
            continue
        if g <= 0:
            continue
        if t in grades:
            continue
        grades[t] = {
            "ticker": t,
            "unified_grade": g,
            "action": row[2].strip() if len(row) > 2 else "N/A",
            "computed_at": row[3].strip() if len(row) > 3 else "",
        }
        if len(grades) >= limit:
            break
    return grades


def _ema(prices: List[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    mult = 2 / (period + 1)
    e = prices[0]
    for p in prices[1:]:
        e = (p - e) * mult + e
    return e


def _rsi(prices: List[float], period: int = 14) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        ch = prices[i] - prices[i-1]
        gains.append(max(ch, 0))
        losses.append(abs(min(ch, 0)))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return 100 - (100 / (1 + avg_g / avg_l))


def compute_fresh_technical(ticker: str) -> Optional[Dict]:
    """Compute a 0-100 technical score from yfinance price data."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        hist = tk.history(period="1y", auto_adjust=True)
        if hist.empty or len(hist) < 50:
            return None

        closes = hist["Close"].tolist()
        vols = hist["Volume"].tolist()
        current = closes[-1]
        ema21 = _ema(closes, 21)
        ema50 = _ema(closes, 50)
        rsi = _rsi(closes)

        # Trend 0-40
        trend = 20
        if ema21 and ema50:
            if current > ema21 > ema50:
                trend = 36
            elif current > ema21:
                trend = 28
            elif current < ema21 < ema50:
                trend = 8
            elif current < ema21:
                trend = 12
        if ema50:
            pct = (current - ema50) / ema50 * 100
            if pct > 10:
                trend += 4
            elif pct < -10:
                trend -= 4
        if len(closes) >= 5:
            rr = (closes[-1] - closes[-5]) / closes[-5] * 100
            if rr > 5:
                trend += 4
            elif rr > 2:
                trend += 2
            elif rr < -5:
                trend -= 4
            elif rr < -2:
                trend -= 2
        trend = max(0, min(40, trend))

        # Momentum 0-35
        mom = 18
        if rsi:
            if 50 <= rsi <= 60:
                mom = 28
            elif 40 <= rsi < 50:
                mom = 22
            elif 30 <= rsi < 40:
                mom = 15
            elif rsi < 30:
                mom = 25
            elif 60 < rsi <= 70:
                mom = 22
            elif rsi > 70:
                mom = 12
        if len(closes) >= 20:
            h20, l20 = max(closes[-20:]), min(closes[-20:])
            rng = h20 - l20
            if rng > 0:
                pos = (current - l20) / rng
                if pos > 0.8:
                    mom += 4
                elif pos < 0.2:
                    mom += 5
                elif pos > 0.5:
                    mom += 2
        mom = max(0, min(35, mom))

        # Volume 0-15
        vscore = 7
        if len(vols) >= 20:
            avg20 = sum(vols[-20:]) / 20
            today = vols[-1]
            if avg20 > 0:
                vr = today / avg20
                if vr > 2:
                    vscore = 13
                elif vr > 1.5:
                    vscore = 11
                elif vr > 1:
                    vscore = 9
                elif vr < 0.5:
                    vscore = 4
        vscore = max(0, min(15, vscore))

        # Volatility 0-10
        vol = 5
        if len(closes) >= 20:
            recent = sum(abs(closes[i] - closes[i-1]) for i in range(-10, 0)) / 10
            older = sum(abs(closes[i] - closes[i-1]) for i in range(-20, -10)) / 10
            if older > 0:
                vt = recent / older
                if vt < 0.8:
                    vol += 2
                elif vt > 1.5:
                    vol -= 2
        vol = max(0, min(10, vol))

        score = trend + mom + vol + vscore
        return {
            "ticker": ticker,
            "score": round(score),
            "rsi": round(rsi, 1) if rsi else None,
            "price": round(current, 2),
            "1d": round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if len(closes) >= 2 else 0,
            "1w": round((closes[-1] - closes[-5]) / closes[-5] * 100, 2) if len(closes) >= 5 else 0,
            "1m": round((closes[-1] - closes[-20]) / closes[-20] * 100, 2) if len(closes) >= 20 else 0,
            "3m": round((closes[-1] - closes[-60]) / closes[-60] * 100, 2) if len(closes) >= 60 else 0,
        }
    except Exception as e:
        return {"error": str(e)}


def call_openrouter(
    system_prompt: str,
    user_prompt: str,
    model: str = "anthropic/claude-sonnet-5",
    max_tokens: int = 2500,
    temperature: float = 0.5,
    script_name: str = "",
    request_id: str = "",
    notes: str = "",
) -> Dict:
    """Call OpenRouter, compute cost, log to DB, and return structured result."""
    api_key = get_secret("OpenRouter", "api_key", "OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not found (checked 1Password and .env)")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    import requests
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter error {resp.status_code}: {resp.text}")

    data = resp.json()
    usage = data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

    cost_breakdown = log_llm_cost(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        script_name=script_name or Path(sys.argv[0]).name,
        request_id=request_id or data.get("id", ""),
        notes=notes,
    )

    return {
        "model": data.get("model", model),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_breakdown["total_cost"],
        "content": data["choices"][0]["message"]["content"],
    }


def save_cache(date_str: str, data: Dict):
    """Save daily grade snapshot to cache."""
    path = CACHE_DIR / f"grades_{date_str}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_cache(date_str: str) -> Optional[Dict]:
    """Load a daily grade snapshot."""
    path = CACHE_DIR / f"grades_{date_str}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def portfolio_status(ticker: str) -> str:
    """Static map of known holdings. Update as needed."""
    ownership = {
        # Core portfolio positions (user currently holds)
        "AMD": "PORTFOLIO", "GOOGL": "PORTFOLIO", "NET": "PORTFOLIO", "DASH": "PORTFOLIO",
        "ARM": "PORTFOLIO", "TSM": "PORTFOLIO", "CRDO": "PORTFOLIO", "MRVL": "PORTFOLIO",
        "ANET": "PORTFOLIO", "TE": "PORTFOLIO", "DUOL": "PORTFOLIO", "SFM": "PORTFOLIO",
        "CREX": "PORTFOLIO", "LYFT": "PORTFOLIO", "OPRA": "PORTFOLIO", "RPRX": "PORTFOLIO",
        "SIMO": "PORTFOLIO", "CRSP": "PORTFOLIO", "C": "PORTFOLIO", "QBTS": "PORTFOLIO",
        "VICR": "PORTFOLIO", "FORM": "PORTFOLIO", "CLPT": "PORTFOLIO", "SNDK": "PORTFOLIO",
        "MCRI": "PORTFOLIO", "FRSH": "PORTFOLIO", "INCY": "PORTFOLIO", "ARKG": "PORTFOLIO",
    }
    return ownership.get(ticker, "NEW")


def corrected_action(score: int) -> str:
    if score >= 80:
        return "STRONG_BUY"
    if score >= 65:
        return "BUY"
    if score >= 50:
        return "HOLD"
    if score >= 40:
        return "TRIM"
    return "SELL"


HOLDINGS_UNIVERSE = {
    "SFM", "CREX", "LYFT", "AMD", "GOOGL", "NET", "OPRA", "RPRX", "SIMO", "MRVL",
    "CRSP", "C", "DASH", "ARM", "QBTS", "TSM", "VICR", "CRDO", "FORM", "ANET",
    "AMAT", "ADP", "ADBE", "ABNB", "APD", "ASAN", "ALLY", "AIR", "ARKG", "INCY",
    "CLPT", "SNDK", "MCRI", "FRSH", "OLED", "BEAM", "BIIB", "ARWR", "AFRM", "ATEN",
    "BAND", "ARQQ", "AUR", "AGL", "ACH", "CAVA", "CELH", "APP", "CRWD", "DDOG",
    "SNOW", "PLTR", "MSTR", "COIN", "HOOD", "RBLX", "U", "DKNG", "MRNA", "NVAX",
    "TE", "DUOL", "TEAM", "OKTA", "ZS", "PANW", "FTNT", "CYBR", "S", "RPD",
    "MDB", "MNDY", "ASANA", "SMAR", "DOCU", "BOX", "ZUO", "PLAN", "NCNO", "FROG",
    "SUMO", "TENB", "VERI", "AI", "BBAI", "SOUN", "INTC", "MU", "QCOM", "AVGO",
    "LRCX", "KLAC", "SNPS", "CDNS", "MCHP", "NXPI", "TXN", "MRVL", "ON", "SWKS",
    "QRVO", "TER", "AMKR", "MPWR", "RMBS", "COHR", "COHU", "AEHR", "ACLS", "SOXX",
}


def ensure_portfolio_in_grades(grades: Dict[str, Dict]) -> Dict[str, Dict]:
    """Ensure user's holdings are present even if not in DB top 150."""
    for t in HOLDINGS_UNIVERSE:
        if t not in grades:
            grades[t] = {
                "ticker": t,
                "unified_grade": 50,  # neutral placeholder
                "action": "HOLD",
                "computed_at": datetime.now().isoformat(),
            }
    return grades


def build_snapshot(limit: int = 100) -> list:
    """Fetch fresh VOX grades + fresh technical scores + corrected grades."""
    grades = get_unified_grades(limit * 2)
    grades = ensure_portfolio_in_grades(grades)
    results = []
    for ticker, g in grades.items():
        tech = compute_fresh_technical(ticker)
        if tech is None or tech.get("error"):
            continue

        vox = g["unified_grade"]
        corrected = round(vox * 0.5 + tech["score"] * 0.5)

        results.append({
            "ticker": ticker,
            "vox_grade": vox,
            "fresh_technical": tech["score"],
            "corrected_grade": corrected,
            "action": corrected_action(corrected),
            "price": tech["price"],
            "rsi": tech.get("rsi"),
            "1d": tech.get("1d"),
            "1w": tech.get("1w"),
            "1m": tech.get("1m"),
            "3m": tech.get("3m"),
            "ownership": portfolio_status(ticker),
        })

    results.sort(key=lambda x: x["corrected_grade"], reverse=True)
    return results
