#!/usr/bin/env python3
"""
VOX publish-only Telegram broadcast (@Vox_alertsbot_bot).

Uses TELEGRAM_BROADCAST_BOT_TOKEN + TELEGRAM_BROADCAST_CHAT_ID.
Not the Hermes interactive gateway.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def tg_api(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return json.loads(body)
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}", "body": body[:300]}


def send_broadcast(text: str) -> tuple[bool, str]:
    token = os.environ.get("TELEGRAM_BROADCAST_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_BROADCAST_CHAT_ID", "").strip()
    if not token:
        return False, "TELEGRAM_BROADCAST_BOT_TOKEN missing"
    if not chat:
        return False, "TELEGRAM_BROADCAST_CHAT_ID missing — /start the bot then discover chat id"
    chunks: list[str] = []
    while text:
        if len(text) <= 4000:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, 3900)
        if cut < 1000:
            cut = 3900
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    last = ""
    for i, ch in enumerate(chunks):
        res = tg_api(
            token,
            "sendMessage",
            {
                "chat_id": chat,
                "text": ch,
                "disable_web_page_preview": True,
            },
        )
        if not res.get("ok"):
            return False, f"send failed part {i+1}: {res}"
        last = f"msg_id={res.get('result', {}).get('message_id')}"
    return True, last


def broadcast_configured() -> bool:
    return bool(
        os.environ.get("TELEGRAM_BROADCAST_BOT_TOKEN", "").strip()
        and os.environ.get("TELEGRAM_BROADCAST_CHAT_ID", "").strip()
    )
