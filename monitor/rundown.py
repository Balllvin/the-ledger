from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .sanitize import safe_preview


def build_daily_rundown(snapshot: dict[str, Any], *, day: str | None = None, timezone_name: str | None = None) -> dict[str, Any]:
    requested_timezone = timezone_name or os.environ.get("THE_LEDGER_TIMEZONE") or "UTC"
    timezone_label, timezone_warning = _timezone_label(requested_timezone)
    resolved_day = day or _previous_day(timezone_label)
    codex_sessions = (snapshot.get("codex") or {}).get("sessions") or {}
    codex_human_meter = (codex_sessions.get("swearByOrigin") or {}).get("human") or codex_sessions.get("swearMeter") or {}
    codex_agent_meter = (codex_sessions.get("swearByOrigin") or {}).get("agent") or {}
    hermes_state = (((snapshot.get("hermes") or {}).get("local") or {}).get("state") or (snapshot.get("hermes") or {}).get("state") or {})
    codex_usage = _row_for_day(codex_sessions.get("timeline") or [], resolved_day, session_key="sessions")
    hermes_usage = _row_for_day(hermes_state.get("byDay") or [], resolved_day, session_key="sessions")
    codex_prompt = _swear_row_for_day(codex_human_meter, resolved_day)
    codex_agent_prompt = _swear_row_for_day(codex_agent_meter, resolved_day)
    hermes_prompt = _swear_row_for_day(hermes_state.get("swearMeter") or {}, resolved_day)
    overview = snapshot.get("overview") or {}
    hermes_last_active = _last_active_row(hermes_state.get("byDay") or [])
    model_input_items = int((codex_sessions.get("modelInputUserItems") or overview.get("codexModelInputUserItems") or 0))

    codex_tokens = int(codex_usage.get("tokens") or 0)
    hermes_tokens = int(hermes_usage.get("tokens") or 0)
    codex_session_count = int(codex_usage.get("sessions") or 0)
    hermes_session_count = int(hermes_usage.get("sessions") or 0)
    codex_prompt_count = int(codex_prompt.get("messages") or 0)
    hermes_prompt_count = int(hermes_prompt.get("messages") or 0)
    codex_index_count = int(codex_prompt.get("swearMessages") or 0)
    hermes_index_count = int(hermes_prompt.get("swearMessages") or 0)
    total_prompt_count = codex_prompt_count + hermes_prompt_count
    total_index_count = codex_index_count + hermes_index_count

    lines = [
        f"Ledger daily rundown for {resolved_day} ({timezone_label})",
        f"- Total usage (Codex + Hermes): {_fmt(codex_tokens + hermes_tokens)} tokens, {_fmt(codex_session_count + hermes_session_count)} sessions",
        f"- Codex: {_fmt(codex_tokens)} tokens, {_fmt(codex_session_count)} sessions",
        f"- Hermes: {_fmt(hermes_tokens)} tokens, {_fmt(hermes_session_count)} sessions",
        f"- Direct prompts checked: {_fmt(total_prompt_count)} ({_fmt(codex_prompt_count)} Codex, {_fmt(hermes_prompt_count)} Hermes)",
        f"- Frustration index: {_fmt(total_index_count)}/{_fmt(total_prompt_count)} direct prompts ({_pct(total_index_count, total_prompt_count)})",
        f"- Codex agent prompts excluded from prompt metrics: {_fmt(codex_agent_prompt.get('messages'))} for this day",
        f"- Codex transcript user items excluded from prompt metrics: {_fmt(model_input_items)} lifetime items",
        f"- Lifetime check -> Codex: {_fmt(overview.get('codexJsonlTokens'))} tokens/{_fmt(overview.get('codexSessionFiles'))} sessions | Hermes: {_fmt(overview.get('hermesTokens'))} tokens/{_fmt(overview.get('hermesSessions'))} sessions",
    ]
    if hermes_last_active:
        lines.append(
            f"- Hermes last active day: {hermes_last_active['day']} ({_fmt(hermes_last_active.get('tokens'))} tokens, {_fmt(hermes_last_active.get('sessions'))} sessions)"
        )
    if timezone_warning:
        lines.append(f"- Timezone note: {timezone_warning}")

    return {
        "day": resolved_day,
        "timezone": timezone_label,
        "timezoneWarning": timezone_warning,
        "text": "\n".join(lines),
        "codex": {"tokens": codex_tokens, "sessions": codex_session_count, "directPrompts": codex_prompt_count, "indexPrompts": codex_index_count},
        "hermes": {"tokens": hermes_tokens, "sessions": hermes_session_count, "directPrompts": hermes_prompt_count, "indexPrompts": hermes_index_count},
        "modelInputUserItems": model_input_items,
    }


def send_telegram_message(text: str, *, token: str | None = None, chat_id: str | None = None) -> dict[str, Any]:
    bot_token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    target_chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not target_chat_id:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required"}

    body = urllib.parse.urlencode({"chat_id": target_chat_id, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"Telegram API returned HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError):
        return {"ok": False, "error": "Telegram API request failed"}
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"Telegram API returned invalid JSON: {safe_preview(exc)}"}
    if not payload.get("ok"):
        return {"ok": False, "error": safe_preview(payload.get("description") or "Telegram API rejected the message")}
    return {"ok": True, "status": "sent"}


def _previous_day(timezone_name: str) -> str:
    zone = ZoneInfo(timezone_name)
    return (datetime.now(zone).date() - timedelta(days=1)).isoformat()


def _timezone_label(timezone_name: str) -> tuple[str, str | None]:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return "UTC", f"{timezone_name} was not found; UTC was used."
    return timezone_name, None


def _row_for_day(rows: list[dict[str, Any]], day: str, *, session_key: str) -> dict[str, Any]:
    for row in rows:
        if str(row.get("day") or "") == day:
            return {"tokens": int(row.get("tokens") or 0), "sessions": int(row.get(session_key) or row.get("threads") or 0)}
    return {"tokens": 0, "sessions": 0}


def _swear_row_for_day(meter: dict[str, Any], day: str) -> dict[str, int]:
    for row in meter.get("timeline") or []:
        if str(row.get("day") or "") == day:
            return {"messages": int(row.get("messages") or 0), "swearMessages": int(row.get("swearMessages") or 0)}
    return {"messages": 0, "swearMessages": 0}


def _last_active_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    active = [row for row in rows if int(row.get("tokens") or 0) > 0 or int(row.get("sessions") or 0) > 0]
    if not active:
        return None
    return max(active, key=lambda row: str(row.get("day") or ""))


def _fmt(value: Any) -> str:
    return f"{int(value or 0):,}"


def _pct(numerator: int, denominator: int) -> str:
    if not denominator:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"
