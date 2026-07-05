"""
Shared DeepSeek v4 Pro second-layer review helper for VOX scanners.
"""
import os
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import vox_utils as vu

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')


def deepseek_review(candidates, context, max_tokens=2000, temperature=0.2):
    """
    Call DeepSeek v4 Pro to filter candidate alerts.
    candidates: list of dicts with at least a 'ticker' key
    context: short description of what this scan is for
    Returns: list of approved candidates (subset of input)
    """
    if not OPENROUTER_API_KEY or not candidates:
        return candidates
    system_prompt = """You are a strict quantitative review layer for a stock alert system. You receive candidate alerts with data fields. Your job is to reject any alert that:
- Is based on mock, synthetic, or placeholder data
- Has missing or zero scores that make it non-actionable
- Is a defensive/boring sector (utilities, staples, telecom, REITs, gold, pharma) unless explicitly justified
- Is a position with extreme P&L but tiny cost basis (data error)
- Is a duplicate or low-conviction signal
Return a JSON object with key "approved" containing only the tickers you approve. Example: {"approved": ["TICKER1", "TICKER2"]}. If none are approved, return {"approved": []}. No other text."""
    user_prompt = f"Context: {context}\n\nCandidates:\n{json.dumps(candidates, indent=2, default=str)}\n\nReturn JSON only."
    try:
        result = vu.call_openrouter(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model="deepseek/deepseek-v4-pro",
            max_tokens=max_tokens,
            temperature=temperature,
            script_name="deepseek_review.py",
            notes="DeepSeek v4 Pro second-layer review",
        )
        content = result.get("content", "")
        start = content.find('{')
        end = content.rfind('}')
        if start == -1 or end == -1:
            return candidates
        parsed = json.loads(content[start:end+1])
        approved = set(parsed.get('approved', []))
        return [c for c in candidates if c.get('ticker') in approved]
    except Exception as e:
        print(f"DeepSeek review failed: {e}")
        return candidates
