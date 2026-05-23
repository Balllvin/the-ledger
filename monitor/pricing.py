from __future__ import annotations

from typing import Any


PRICE_DENOMINATOR = 1_000_000

PRICE_SOURCES = {
    "openai": "https://developers.openai.com/api/docs/pricing",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing/",
    "opencode": "https://dev.opencode.ai/docs/zen",
    "anthropic": "https://platform.claude.com/docs/en/about-claude/pricing",
    "google": "https://ai.google.dev/gemini-api/docs/pricing",
    "xai": "https://docs.x.ai/docs/models",
}


MODEL_PRICES: dict[str, dict[str, Any]] = {
    "gpt-5.5": {"label": "GPT-5.5", "input": 5.0, "cachedInput": 0.5, "output": 30.0, "provider": "openai"},
    "gpt-5.4": {"label": "GPT-5.4", "input": 2.5, "cachedInput": 0.25, "output": 15.0, "provider": "openai"},
    "gpt-5.4-mini": {"label": "GPT-5.4 mini", "input": 0.75, "cachedInput": 0.075, "output": 4.5, "provider": "openai"},
    "gpt-5.3-codex": {"label": "GPT-5.3 Codex", "input": 1.75, "cachedInput": 0.175, "output": 14.0, "provider": "openai"},
    "gpt-5.2-codex": {"label": "GPT-5.2 Codex", "input": 1.75, "cachedInput": 0.175, "output": 14.0, "provider": "openai"},
    "gpt-5.1-codex": {"label": "GPT-5.1 Codex", "input": 1.25, "cachedInput": 0.125, "output": 10.0, "provider": "openai"},
    "gpt-5-codex": {"label": "GPT-5 Codex", "input": 1.25, "cachedInput": 0.125, "output": 10.0, "provider": "openai"},
    "gpt-5": {"label": "GPT-5", "input": 1.25, "cachedInput": 0.125, "output": 10.0, "provider": "openai"},
    "o3": {"label": "o3", "input": 2.0, "cachedInput": 0.5, "output": 8.0, "provider": "openai"},
    "deepseek-v4-pro": {"label": "DeepSeek V4 Pro", "input": 1.74, "cachedInput": 0.0145, "output": 3.48, "provider": "deepseek"},
    "deepseek-v4-flash": {"label": "DeepSeek V4 Flash", "input": 0.14, "cachedInput": 0.0028, "output": 0.28, "provider": "deepseek"},
    "deepseek-chat": {"label": "DeepSeek Chat", "input": 0.27, "cachedInput": 0.07, "output": 1.1, "provider": "deepseek"},
    "deepseek-reasoner": {"label": "DeepSeek Reasoner", "input": 0.55, "cachedInput": 0.14, "output": 2.19, "provider": "deepseek"},
    "claude-opus-4.7": {"label": "Claude Opus 4.7", "input": 5.0, "cachedInput": 0.5, "cacheWrite": 6.25, "output": 25.0, "provider": "opencode"},
    "grok-4": {"label": "Grok 4", "input": 3.0, "cachedInput": 0.75, "output": 15.0, "provider": "xai"},
    "gemini-3.1-pro": {"label": "Gemini 3.1 Pro", "input": 2.0, "cachedInput": 0.2, "output": 12.0, "provider": "google"},
    "gemini-2.5-pro": {"label": "Gemini 2.5 Pro", "input": 1.25, "cachedInput": 0.125, "output": 10.0, "provider": "google"},
    "gemini-2.5-flash": {"label": "Gemini 2.5 Flash", "input": 0.30, "cachedInput": 0.03, "output": 2.5, "provider": "google"},
    "gemini-2.5-flash-lite": {"label": "Gemini 2.5 Flash-Lite", "input": 0.10, "cachedInput": 0.01, "output": 0.40, "provider": "google"},
}


def build_billing_estimate(snapshot: dict[str, Any]) -> dict[str, Any]:
    estimate = _empty_estimate()
    for source, rows, note in (
        ("codex", _codex_rows(snapshot), _codex_note(snapshot)),
        ("hermes", _hermes_rows(snapshot), ""),
        ("opencode", _opencode_rows(snapshot), ""),
        ("cursor", _cursor_rows(snapshot), _cursor_note(snapshot)),
    ):
        source_estimate = _empty_source_estimate(source, note=note)
        for row in rows:
            priced = _price_row(row)
            _merge_estimate(source_estimate, priced)
            source_estimate["models"].append(priced)
        if not rows and note:
            source_estimate["available"] = False
        estimate["sources"][source] = source_estimate
        _merge_estimate(estimate, source_estimate)

    estimate["models"] = sorted(
        [row for source in estimate["sources"].values() for row in source.get("models") or []],
        key=lambda item: float(item.get("totalUsd") or 0),
        reverse=True,
    )
    estimate["notes"] = [source.get("note") for source in estimate["sources"].values() if source.get("note")]
    _round_money(estimate)
    for source in estimate["sources"].values():
        _round_money(source)
        for row in source.get("models") or []:
            _round_money(row)
    return estimate


def normalize_price_model(model: Any) -> tuple[str, str]:
    model_id = str(model or "").strip().lower()
    if not model_id or model_id in {"[unknown]", "[missing]"}:
        return "", ""
    if "gpt-5.4-mini" in model_id:
        return "gpt-5.4-mini", ""
    if "gpt-5.5" in model_id:
        return "gpt-5.5", ""
    if "gpt-5.4" in model_id:
        return "gpt-5.4", ""
    if "gpt-5.3-codex" in model_id:
        return "gpt-5.3-codex", "priced as GPT-5.3 Codex family"
    if "gpt-5.2-codex" in model_id:
        return "gpt-5.2-codex", ""
    if "gpt-5.1-codex" in model_id or "gpt-5.1-codex-max" in model_id:
        return "gpt-5.1-codex", ""
    if "gpt-5-codex" in model_id:
        return "gpt-5-codex", ""
    if model_id == "o3" or model_id.startswith("o3-"):
        return "o3", ""
    if "deepseek-v4-pro" in model_id:
        return "deepseek-v4-pro", ""
    if "deepseek-v4-flash" in model_id:
        return "deepseek-v4-flash", ""
    if model_id == "deepseek-chat":
        return "deepseek-chat", ""
    if model_id == "deepseek-reasoner":
        return "deepseek-reasoner", ""
    if "claude-opus-4.7" in model_id:
        return "claude-opus-4.7", "priced from OpenCode Zen public rate"
    if "grok-4" in model_id:
        return "grok-4", ""
    if "gemini-3.1-pro" in model_id:
        return "gemini-3.1-pro", ""
    if "gemini-2.5-pro" in model_id:
        return "gemini-2.5-pro", ""
    if "gemini-2.5-flash-lite" in model_id:
        return "gemini-2.5-flash-lite", ""
    if "gemini-2.5-flash" in model_id:
        return "gemini-2.5-flash", ""
    if "gpt-5" in model_id:
        return "gpt-5", ""
    return "", ""


def _codex_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    codex = snapshot.get("codex") or {}
    state = codex.get("state") or {}
    sessions = codex.get("sessions") or {}
    state_models = state.get("tokensByModel") or []
    if state_models:
        profiles = _codex_profiles(sessions)
        blended = _blend_profile(profiles.values())
        rows = []
        for row in state_models:
            model = str(row.get("model") or "[missing]")
            total = _to_int(row.get("tokens"))
            if total <= 0:
                continue
            profile = profiles.get(model) or blended
            tokens = _scale_codex_profile(profile, total)
            rows.append(
                {
                    "source": "codex",
                    "model": model,
                    "tokens": tokens,
                    "threads": _to_int(row.get("threads")),
                    "estimatedBuckets": True,
                    "cacheIncludedInInput": True,
                    "reasoningIncludedInOutput": True,
                    "note": "complete state ledger, buckets estimated from parsed Codex usage ratios",
                }
            )
        return rows

    rows = []
    for model, totals in (sessions.get("tokenTotalsByModel") or {}).items():
        tokens = _canonical_tokens(totals, codex=True)
        if tokens["total"] > 0:
            rows.append({"source": "codex", "model": model, "tokens": tokens, "cacheIncludedInInput": True, "reasoningIncludedInOutput": True})
    if rows:
        return rows
    totals = _canonical_tokens(sessions.get("tokenTotals") or {}, codex=True)
    if totals["total"] > 0:
        rows.append({"source": "codex", "model": "[unknown]", "tokens": totals, "cacheIncludedInInput": True, "reasoningIncludedInOutput": True})
    return rows


def _codex_profiles(sessions: dict[str, Any]) -> dict[str, dict[str, int]]:
    profiles = {}
    for model, totals in (sessions.get("tokenTotalsByModel") or {}).items():
        tokens = _canonical_tokens(totals, codex=True)
        if tokens["total"] > 0:
            profiles[str(model)] = tokens
    return profiles


def _blend_profile(profiles: Any) -> dict[str, int]:
    blended = _empty_tokens()
    for profile in profiles:
        for key in blended:
            blended[key] += _to_int((profile or {}).get(key))
    if blended["total"] <= 0:
        blended["input"] = 1
        blended["total"] = 1
    return blended


def _scale_codex_profile(profile: dict[str, int], total: int) -> dict[str, int]:
    profile_total = max(1, _to_int(profile.get("total")))
    scaled = _empty_tokens()
    for key in ("input", "output", "reasoning", "cacheRead", "cacheWrite"):
        scaled[key] = round(total * _to_int(profile.get(key)) / profile_total)
    if scaled["input"] + scaled["output"] <= 0:
        scaled["input"] = total
    drift = total - (scaled["input"] + scaled["output"])
    scaled["input"] += drift
    scaled["cacheRead"] = min(scaled["cacheRead"], scaled["input"])
    scaled["reasoning"] = min(scaled["reasoning"], scaled["output"])
    scaled["total"] = total
    return scaled


def _hermes_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    state = ((((snapshot.get("hermes") or {}).get("local") or {}).get("state")) or (snapshot.get("hermes") or {}).get("state") or {})
    rows = []
    for row in state.get("byModel") or []:
        tokens = _canonical_tokens(row)
        if tokens["total"] > 0:
            rows.append({"source": "hermes", "model": row.get("model") or "[unknown]", "tokens": tokens, "sessions": _to_int(row.get("sessions"))})
    if rows:
        return rows
    tokens = _canonical_tokens(state.get("sessions") or {})
    if tokens["total"] > 0:
        rows.append({"source": "hermes", "model": "[unknown]", "tokens": tokens})
    return rows


def _opencode_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    database = ((snapshot.get("opencode") or {}).get("database") or {})
    rows = []
    for model, totals in (database.get("tokensByModel") or {}).items():
        tokens = _canonical_tokens(totals)
        if tokens["total"] > 0:
            rows.append({"source": "opencode", "model": model, "tokens": tokens})
    if rows:
        return rows
    tokens = _canonical_tokens(((database.get("messages") or {}).get("tokens") or {}))
    if tokens["total"] > 0:
        rows.append({"source": "opencode", "model": "[unknown]", "tokens": tokens})
    return rows


def _cursor_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    cursor = snapshot.get("cursor") or {}
    billing = cursor.get("billing") or {}
    rows = []
    for row in billing.get("byModel") or []:
        tokens = _canonical_tokens(row)
        if tokens["total"] > 0:
            rows.append({"source": "cursor", "model": row.get("model") or "[unknown]", "tokens": tokens})
    return rows


def _price_row(row: dict[str, Any]) -> dict[str, Any]:
    tokens = _canonical_tokens(row.get("tokens") or {})
    price_model, alias_note = normalize_price_model(row.get("model"))
    price = MODEL_PRICES.get(price_model) if price_model else None
    output_tokens = tokens["output"]
    if not row.get("reasoningIncludedInOutput"):
        output_tokens += tokens["reasoning"]
    cache_included_in_input = bool(row.get("cacheIncludedInInput"))
    billable_input_tokens = tokens["input"] + tokens["cacheWrite"] if cache_included_in_input else tokens["input"] + tokens["cacheRead"] + tokens["cacheWrite"]
    result = {
        **row,
        "tokens": tokens,
        "inputTokens": tokens["input"],
        "cachedInputTokens": tokens["cacheRead"],
        "cacheWriteTokens": tokens["cacheWrite"],
        "outputTokens": tokens["output"],
        "reasoningTokens": tokens["reasoning"],
        "billableInputTokens": billable_input_tokens,
        "billableOutputTokens": output_tokens,
        "pricedTokens": 0,
        "unpricedTokens": tokens["total"],
        "priceModel": price_model or "",
        "priceLabel": "",
        "priceSource": "",
        "priceSourceUrl": "",
        "inputUsd": 0.0,
        "outputUsd": 0.0,
        "totalUsd": 0.0,
    }
    notes = [row.get("note"), alias_note]
    if not price:
        result["note"] = "; ".join(note for note in notes if note) or "no public API price matched this local model ID"
        return result

    cached_input = min(tokens["cacheRead"], tokens["input"]) if cache_included_in_input else tokens["cacheRead"]
    uncached_input = max(0, tokens["input"] - cached_input) if cache_included_in_input else tokens["input"]
    cache_write = tokens["cacheWrite"]
    input_usd = (
        uncached_input * float(price["input"])
        + cached_input * float(price.get("cachedInput", price["input"]))
        + cache_write * float(price.get("cacheWrite", price["input"]))
    ) / PRICE_DENOMINATOR
    output_usd = output_tokens * float(price["output"]) / PRICE_DENOMINATOR
    provider = str(price.get("provider") or "")
    result.update(
        {
            "pricedTokens": tokens["total"],
            "unpricedTokens": 0,
            "priceLabel": price["label"],
            "priceSource": provider,
            "priceSourceUrl": PRICE_SOURCES.get(provider, ""),
            "inputUsd": input_usd,
            "outputUsd": output_usd,
            "totalUsd": input_usd + output_usd,
            "note": "; ".join(note for note in notes if note),
        }
    )
    return result


def _canonical_tokens(value: Any, *, codex: bool = False) -> dict[str, int]:
    data = value if isinstance(value, dict) else {}
    tokens = _empty_tokens()
    tokens["input"] = _to_int(data.get("input", data.get("input_tokens", data.get("inputTokens", 0))))
    tokens["output"] = _to_int(data.get("output", data.get("output_tokens", data.get("outputTokens", 0))))
    tokens["reasoning"] = _to_int(data.get("reasoning", data.get("reasoning_output_tokens", data.get("reasoningTokens", 0))))
    tokens["cacheRead"] = _to_int(data.get("cacheRead", data.get("cached_input_tokens", data.get("cacheReadTokens", 0))))
    tokens["cacheWrite"] = _to_int(data.get("cacheWrite", data.get("cacheWriteTokens", 0)))
    total_key = data.get("total", data.get("total_tokens", data.get("tokens")))
    if total_key is not None:
        tokens["total"] = _to_int(total_key)
    elif codex:
        tokens["total"] = tokens["input"] + tokens["output"]
    else:
        tokens["total"] = tokens["input"] + tokens["output"] + tokens["reasoning"] + tokens["cacheRead"] + tokens["cacheWrite"]
    if tokens["total"] <= 0:
        tokens["total"] = tokens["input"] + tokens["output"] + (0 if codex else tokens["reasoning"]) + tokens["cacheRead"] + tokens["cacheWrite"]
    return tokens


def _empty_tokens() -> dict[str, int]:
    return {"input": 0, "output": 0, "reasoning": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0}


def _empty_estimate() -> dict[str, Any]:
    return {
        "inputUsd": 0.0,
        "outputUsd": 0.0,
        "totalUsd": 0.0,
        "inputTokens": 0,
        "outputTokens": 0,
        "reasoningTokens": 0,
        "cachedInputTokens": 0,
        "cacheWriteTokens": 0,
        "billableInputTokens": 0,
        "billableOutputTokens": 0,
        "pricedTokens": 0,
        "unpricedTokens": 0,
        "estimatedTokens": 0,
        "sources": {},
        "models": [],
        "notes": [],
    }


def _empty_source_estimate(source: str, *, note: str = "") -> dict[str, Any]:
    estimate = _empty_estimate()
    estimate["source"] = source
    estimate["available"] = True
    estimate["note"] = note
    estimate["models"] = []
    estimate.pop("sources")
    estimate.pop("notes")
    return estimate


def _merge_estimate(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "inputUsd",
        "outputUsd",
        "totalUsd",
        "inputTokens",
        "outputTokens",
        "reasoningTokens",
        "cachedInputTokens",
        "cacheWriteTokens",
        "billableInputTokens",
        "billableOutputTokens",
        "pricedTokens",
        "unpricedTokens",
    ):
        target[key] += source.get(key) or 0
    if source.get("estimatedBuckets"):
        target["estimatedTokens"] += ((source.get("tokens") or {}).get("total") if isinstance(source.get("tokens"), dict) else 0) or source.get("estimatedTokens") or 0
    else:
        target["estimatedTokens"] += source.get("estimatedTokens") or 0


def _round_money(value: dict[str, Any]) -> None:
    for key in ("inputUsd", "outputUsd", "totalUsd"):
        if key in value:
            value[key] = round(float(value.get(key) or 0), 6)


def _codex_note(snapshot: dict[str, Any]) -> str:
    overview = snapshot.get("overview") or {}
    state_tokens = _to_int(overview.get("codexStateTokens"))
    jsonl_tokens = _to_int(overview.get("codexJsonlTokens"))
    if state_tokens and jsonl_tokens and state_tokens > jsonl_tokens:
        return f"Codex billing uses complete state ledger tokens; parsed JSONL covers {jsonl_tokens:,} of {state_tokens:,} tokens and supplies bucket ratios."
    return ""


def _cursor_note(snapshot: dict[str, Any]) -> str:
    cursor = snapshot.get("cursor") or {}
    if not cursor.get("available"):
        return ""
    return "Cursor local records expose activity and line counters, but no token/model billing ledger was found."


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
