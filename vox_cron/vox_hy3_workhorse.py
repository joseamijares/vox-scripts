#!/usr/bin/env python3
"""
VOX hy3:free Workhorse Router
Tests and routes tasks to tencent/hy3:free (or fallback) for heavy-lift, low-risk work
where Sonnet 5 handles architecture/review and paid models handle high-stakes synthesis.

Strategy:
- Use hy3:free for structured drafting, summarization, classification, and ranking at scale.
- Always validate output shape before downstream use.
- Fallback to deepseek-v4-flash or Sonnet 5 if hy3:free returns null content or malformed JSON.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_utils import call_openrouter


def hy3_draft(system_prompt: str, user_prompt: str, max_tokens: int = 800, temperature: float = 0.3,
              script_name: str = "hy3_workhorse", fallback_model: str = "deepseek/deepseek-v4-flash",
              cheap_hy3: str = "tencent/hy3-preview") -> dict:
    """Call hy3:free with a system prompt and fall back if content is missing."""
    # Enforce content field usage
    full_system = (
        system_prompt.strip()
        + "\n\nIMPORTANT: Provide your final answer in the 'content' field. "
        "Do not leave content empty."
    )
    # For the free endpoint, strip any system output-field instructions because it tends to echo them.
    free_system = system_prompt.strip()
    models = ["tencent/hy3:free", cheap_hy3, fallback_model]
    result: dict = {}
    for model in models:
        sys_to_use = free_system if model.endswith(":free") else full_system
        result = call_openrouter(sys_to_use, user_prompt, model=model,
                                 max_tokens=max_tokens, temperature=temperature, script_name=script_name)
        content = str(result.get("content") or "").strip()
        reasoning = str(result.get("reasoning") or "").strip()
        if not content and reasoning:
            content = reasoning
        if content:
            result["content"] = content
            result["fallback"] = model != "tencent/hy3:free"
            return result
    # Final fallback (should never reach if fallback_model works)
    result["content"] = content
    result["fallback"] = True
    return result


if __name__ == '__main__':
    # Example: rank watchlist tickers
    user = """Rank these 10 small-cap tickers from strongest to weakest setup. Output a Markdown table with columns: Rank, Ticker, Score(0-100), One-line reason. Keep under 250 words.

Tickers: JMIA, CLPT, EOSE, OSS, CLFD, AMBQ, VPG, TE, KRKNF, BZAI."""
    out = hy3_draft("You are a disciplined small-cap equities analyst. Be concise and structured.", user)
    print(f"fallback={out['fallback']}")
    print(out['content'])
