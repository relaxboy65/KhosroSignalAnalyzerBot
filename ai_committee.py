"""AI committee for Khosro Confluence Engine v11.

Three independent free AI providers vote on each candidate signal:
  - OpenRouter  (z-ai/glm-5.2:free)            weight 40
  - Mistral     (open-mistral-nemo)            weight 35
  - SiliconFlow (Qwen/Qwen2.5-7B-Instruct)     weight 25

Each provider returns strict JSON {"decision":"approve|reject",
"confidence":0-100,"reason":"..."}. Votes are combined into a single 0..1
score plus a boolean majority approval. If every provider fails, the
committee is "unavailable" and the engine falls back to a neutral 0.5 so a
network outage can never silently approve (or veto) trades.

Budgets keep the free quotas safe:
  - AI_MAX_CALLS_PER_RUN   per process run
  - AI_DAILY_BUDGET        persisted daily counter (signals/ai_budget_*.json)
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

import aiohttp

from config import (
    AI_PROVIDERS, AI_SYSTEM_PROMPT, AI_TEMPERATURE, AI_MAX_TOKENS,
    AI_TIMEOUT_SECONDS, AI_MAX_CALLS_PER_RUN, AI_DAILY_BUDGET,
    AI_MIN_COMMITTEE_SCORE, AI_REJECT_DECAY,
)

logger = logging.getLogger(__name__)

_run_calls = 0


# ---------------------------------------------------------------------------
# budgeting
# ---------------------------------------------------------------------------
def reset_budget():
    global _run_calls
    _run_calls = 0


def _budget_path():
    from signal_store import SIGNALS_DIR, tehran_date_str
    os.makedirs(SIGNALS_DIR, exist_ok=True)
    return os.path.join(SIGNALS_DIR, f"ai_budget_{tehran_date_str()}.json")


def _daily_count() -> int:
    path = _budget_path()
    try:
        with open(path, encoding="utf-8") as f:
            return int(json.load(f).get("count", 0))
    except Exception:
        return 0


def _bump_daily(n: int = 1):
    path = _budget_path()
    data = {"date": datetime.now(timezone.utc).isoformat(), "count": _daily_count() + n}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def budget_left() -> int:
    return max(0, min(AI_MAX_CALLS_PER_RUN - _run_calls,
                      AI_DAILY_BUDGET - _daily_count()))


# ---------------------------------------------------------------------------
# JSON extraction (models wrap JSON in prose / code fences sometimes)
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # reasoning models often repeat the schema first and answer last —
    # so try brace groups from the END of the text backwards.
    matches = re.findall(r"\{[^{}]*\}", cleaned, re.S)
    for candidate in reversed(matches):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and "decision" in data:
                return data
        except Exception:
            continue
    return None


def _normalize_vote(data: dict) -> tuple[bool, int] | None:
    decision = str(data.get("decision", "")).strip().lower()
    try:
        conf = float(data.get("confidence", 50))
    except (TypeError, ValueError):
        return None
    conf = max(0.0, min(100.0, conf))
    if decision.startswith("app") or decision in ("yes", "long", "buy", "approve"):
        return True, conf
    if decision.startswith("rej") or decision in ("no", "short", "sell", "reject", "avoid"):
        return False, conf
    return None


# ---------------------------------------------------------------------------
# prompt
# ---------------------------------------------------------------------------
def build_user_prompt(candidate: dict) -> str:
    lines = [
        f"Symbol: {candidate.get('symbol')}",
        f"Proposed trade: {candidate.get('direction')} (spot/derivative scalp, ~30m basis)",
        f"Entry {candidate.get('price')}, SL {candidate.get('stop_loss')}, TP {candidate.get('take_profit')}, R:R 1:{candidate.get('rr')}",
    ]
    atr = candidate.get('atr_pct')
    if atr is not None:
        lines.append(f"ATR: {atr:.2%} of price")
    comps = candidate.get('components') or []
    if comps:
        lines.append("Analysis components (score 0..1 and evidence):")
        for c in comps:
            lines.append(f"- {c['name']}: {c['score']:.2f} | {c.get('detail', '')[:110]}")
    rules = candidate.get('custom_rules')
    if rules:
        lines.append("Trader rules you MUST respect:")
        lines.append(rules)
    lines.append(
        'Vote now. Reply ONLY with JSON: '
        '{"decision":"approve|reject","confidence":0-100,"reason":"max 15 words"}'
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# single provider call
# ---------------------------------------------------------------------------
async def _call_provider(session: aiohttp.ClientSession, provider: dict,
                         user_prompt: str) -> dict:
    api_key = os.getenv(provider["key_env"], "").strip()
    if not api_key:
        return {"ok": False, "error": f"missing {provider['key_env']}"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider["name"] == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/khosro-signal-bot"
        headers["X-Title"] = "KhosroSignalAnalyzerBot"
    models = [provider["model"]] + list(provider.get("fallback_models") or [])
    attempts_per_model = 2 if provider.get("retry_429") else 1
    last_error = "unknown"
    for model in models:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": AI_TEMPERATURE,
            "max_tokens": AI_MAX_TOKENS,
        }
        for attempt in range(attempts_per_model):
            try:
                async with session.post(provider["url"], headers=headers, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=AI_TIMEOUT_SECONDS)) as resp:
                    if resp.status == 429 and attempt + 1 < attempts_per_model:
                        await asyncio.sleep(3.0)
                        continue
                    if resp.status != 200:
                        last_error = f"{model}: HTTP {resp.status}: {(await resp.text())[:100]}"
                        break       # move to next model
                    data = await resp.json()
                    choice = (data.get("choices") or [{}])[0]
                    message = choice.get("message") or {}
                    # some reasoning models return the visible text in `reasoning`
                    content = (message.get("content")
                               or message.get("reasoning")
                               or message.get("reasoning_content") or "")
                    vote = _extract_json(content)
                    if vote is None:
                        last_error = f"{model}: unparseable reply"
                        break       # move to next model
                    norm = _normalize_vote(vote)
                    if norm is None:
                        last_error = f"{model}: bad decision field"
                        break       # move to next model
                    approved, conf = norm
                    return {"ok": True, "model": model, "approved": approved,
                            "confidence": conf, "reason": str(vote.get("reason", ""))[:80]}
            except Exception as exc:
                last_error = f"{model}: {type(exc).__name__}: {str(exc)[:90]}"
                if attempt + 1 < attempts_per_model:
                    await asyncio.sleep(1.5)
    return {"ok": False, "error": last_error}


# ---------------------------------------------------------------------------
# committee entrypoint
# ---------------------------------------------------------------------------
async def consult_committee(candidate: dict,
                            session: aiohttp.ClientSession | None = None) -> dict:
    """Ask all enabled providers to vote on one candidate.

    Returns {"available", "approved", "score", "detail", "votes"}.
    """
    global _run_calls
    if budget_left() <= 0:
        return {"available": False, "approved": None, "score": 0.5,
                "detail": "AI budget exhausted (neutral)", "votes": []}
    _run_calls += 1
    _bump_daily()
    user_prompt = build_user_prompt(candidate)
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    votes = []
    try:
        tasks = [_call_provider(session, p, user_prompt) for p in AI_PROVIDERS if p.get("enabled", True)]
        results = await asyncio.gather(*tasks)
        for provider, res in zip([p for p in AI_PROVIDERS if p.get("enabled", True)], results):
            votes.append({"provider": provider["name"], "weight": provider["weight"], **res})
    finally:
        if own_session:
            await session.close()

    ok_votes = [v for v in votes if v.get("ok")]
    if not ok_votes:
        detail = "AI unavailable: " + "; ".join(
            f"{v['provider']}={v.get('error', '?')}" for v in votes) or "no providers"
        return {"available": False, "approved": None, "score": 0.5,
                "detail": detail[:180], "votes": votes}

    total_w = sum(v["weight"] for v in ok_votes) or 1
    combined = 0.0
    for v in ok_votes:
        v_score = (v["confidence"] / 100.0) if v["approved"] \
            else (100.0 - v["confidence"]) / 100.0 * AI_REJECT_DECAY
        combined += v["weight"] * v_score
    combined /= total_w
    approves = sum(1 for v in ok_votes if v["approved"])
    rejects = len(ok_votes) - approves
    approved = approves > rejects and combined >= AI_MIN_COMMITTEE_SCORE
    detail = (f"AI {approves} approve/{rejects} reject, score={combined:.2f} | "
              + "; ".join(f"{v['provider']}={'approve' if v['approved'] else 'reject'}"
                          f"{v['confidence']:.0f}% ({v.get('reason', '')[:40]})" for v in ok_votes))
    return {"available": True, "approved": approved, "score": round(combined, 3),
            "detail": detail[:220], "votes": votes}
