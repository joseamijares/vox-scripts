#!/usr/bin/env python3
"""
VOX Workhorse Router
Configurable heavy-lift router for high-volume, low-stakes VOX tasks.
Defaults to deepseek/deepseek-v4-pro (or x-ai/grok-4.3) as workhorse,
alongside OpenRouter (deepseek, kimi) and direct xAI Grok options.
Grok 4.3 for workhorse tasks, Grok 4.5 for brain/high-stakes.
Thinking/reasoning tasks use Sonnet 5, gpt-5.6-terra-pro, or grok-4.5.

Never use this router for:
- Final investment decisions
- Unified grade computation
- Position sizing / risk overrides
- Auto-triggered alerts without human review
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_utils import call_openrouter

DEFAULT_WORKHORSE = "deepseek/deepseek-v4-pro"  # alternatives: "x-ai/grok-4.3", "moonshotai/kimi-k2"
WORKHORSE_FALLBACKS = [
    "deepseek/deepseek-v4-flash",
    "x-ai/grok-4.3",   # direct Grok workhorse via OpenRouter
]

THINKING_MODELS = [
    "anthropic/claude-sonnet-5",
    "openai/gpt-5.6-terra-pro",
    # Grok 4.5 brain is Hermes default via direct xai-oauth (not on OpenRouter).
    # Use workhorse x-ai/grok-4.3 for OpenRouter path when needed.
]


def workhorse_draft(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 800,
    temperature: float = 0.3,
    script_name: str = "vox_workhorse",
    primary_model: str = DEFAULT_WORKHORSE,
    fallbacks: list | None = None,
) -> dict:
    """
    Call the configured workhorse model and fall back if content is missing.
    Returns the first successful result with a non-empty content field.
    """
    if fallbacks is None:
        fallbacks = WORKHORSE_FALLBACKS
    models = [primary_model] + [m for m in fallbacks if m != primary_model]
    last_error = ""
    for model in models:
        try:
            result = call_openrouter(
                system_prompt,
                user_prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                script_name=script_name,
            )
            content = str(result.get("content") or "").strip()
            if content:
                result["fallback"] = model != primary_model
                result["primary"] = primary_model
                return result
        except Exception as e:
            last_error = str(e)
            continue
    return {
        "content": "",
        "fallback": True,
        "primary": primary_model,
        "error": last_error or "All models failed",
    }


def thinking_draft(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.4,
    script_name: str = "vox_thinking",
    primary_model: str = "anthropic/claude-sonnet-5",
    fallbacks: list | None = None,
) -> dict:
    """
    Thinking/reasoning helper. Use for architecture, review, complex synthesis.
    Defaults to Sonnet 5, with openai/gpt-5.6-terra-pro as fallback.
    """
    if fallbacks is None:
        fallbacks = [m for m in THINKING_MODELS if m != primary_model]
    return workhorse_draft(
        system_prompt,
        user_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        script_name=script_name,
        primary_model=primary_model,
        fallbacks=fallbacks,
    )


if __name__ == '__main__':
    # Example: rank watchlist tickers
    user = """Rank these 10 small-cap tickers from strongest to weakest setup. Output a Markdown table with columns: Rank, Ticker, Score(0-100), One-line reason. Keep under 250 words.

Tickers: JMIA, CLPT, EOSE, OSS, CLFD, AMBQ, VPG, TE, KRKNF, BZAI."""
    out = workhorse_draft("You are a disciplined small-cap equities analyst. Be concise and structured.", user)
    print(f"model={out.get('model')}")
    print(f"fallback={out.get('fallback')}")
    print(out['content'])
