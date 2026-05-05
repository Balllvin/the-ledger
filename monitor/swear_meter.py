from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any


SCAFFOLD_PREFIXES = (
    "# AGENTS.md instructions",
    "<INSTRUCTIONS>",
    "<environment_context>",
    "<permissions instructions>",
    "<skill>",
    "<turn_aborted>",
)

SWEAR_INDEX_GROUPS = frozenset(
    {
        "swearing",
        "spicy_moment",
        "quality_critique",
        "boundary_violation",
        "frustrated_rework",
    }
)

SWEAR_INDEX_EXCLUDED_TERMS = {
    "a mess",
    "bit of a mess",
    "delete this",
    "do something completely different",
    "heck",
    "hell",
    "much worse",
    "not crisp enough",
    "start again",
    "too wordy",
    "untidy",
    "why do we need this",
}

SWEAR_INDEX_LEXICON = {
    "hard_swearing": {
        "group": "swearing",
        "weight": 4,
        "terms": [
            "fuck",
            "fucking",
            "fucked",
            "fucks",
            "fucker",
            "fuckers",
            "fuck's sake",
            "for fuck's sake",
            "for fucks sake",
            "jesus fucking christ",
            "jesus christ",
            "motherfucker",
            "motherfucking",
            "shit",
            "shitty",
            "bullshit",
            "wtf",
            "wtaf",
            "ffs",
            "fml",
            "stfu",
            "asshole",
            "dumbass",
            "bastard",
            "bollocks",
        ],
    },
    "soft_swearing": {
        "group": "swearing",
        "weight": 2,
        "terms": [
            "damn",
            "dammit",
            "damnit",
            "damn it",
            "goddamn",
            "god damn",
            "for god's sake",
            "for gods sake",
            "crap",
            "crappy",
            "bloody hell",
            "fucking hell",
            "what the heck",
        ],
    },
    "wtf_moment": {
        "group": "spicy_moment",
        "weight": 4,
        "terms": [
            "what the fuck",
            "what the actual fuck",
            "what the hell",
            "what in the hell",
            "why the hell",
            "how the hell",
            "what the hell is this",
            "what the hell are you doing",
            "what the fucking hell",
            "wth",
            "are you kidding me",
            "are you fucking kidding me",
            "fuck sake",
            "wtf man",
            "come on man",
            "what is going on here",
            "come on",
        ],
    },
    "quality_rejection": {
        "group": "quality_critique",
        "weight": 3,
        "terms": [
            "this is awful",
            "that's awful",
            "this sucks",
            "this really sucks",
            "sucks ass",
            "this looks awful",
            "everything looks awful",
            "this is terrible",
            "this is really bad",
            "this looks really bad",
            "this looks bad",
            "looks really bad",
            "looks terrible",
            "this is ridiculous",
            "this is insane",
            "looks disgusting",
            "looks trashy",
            "this is garbage",
            "hot garbage",
            "this is useless",
            "completely useless",
            "i hate this",
            "i hate it",
            "not remotely good enough",
            "not good enough",
            "looks ugly",
            "really ugly",
        ],
    },
    "unacceptable_boundary": {
        "group": "boundary_violation",
        "weight": 3,
        "terms": [
            "unacceptable",
            "completely unacceptable",
            "not acceptable",
            "this cannot happen",
            "can't happen",
            "cannot happen",
            "this must never",
            "this should never",
            "we must never ship",
            "never have that happen",
            "delete this shit",
            "delete this whole thing",
            "kill it and start again",
            "redo from scratch",
        ],
    },
    "rework_cost": {
        "group": "frustrated_rework",
        "weight": 2,
        "terms": [
            "waste of time",
            "wasted time",
            "wasting time",
            "waste my time",
            "wasting my time",
            "you are wasting my time",
            "real nightmare",
            "complete nightmare",
            "this is a mess",
            "it's a mess",
            "it is a mess",
            "looks like a mess",
            "complete mess",
            "everything is a mess",
            "you've messed up",
            "you messed up",
            "messed up",
            "made it worse",
            "you made it worse",
            "this is worse now",
            "looks worse now",
            "even worse now",
            "worse now",
        ],
    },
}


@dataclass(frozen=True)
class TermPattern:
    category: str
    group: str
    term: str
    weight: int
    pattern: re.Pattern[str]


def should_skip_message(message: str, *, include_automations: bool = False) -> bool:
    text = message.strip()
    if not text:
        return True
    if any(text.startswith(prefix) for prefix in SCAFFOLD_PREFIXES):
        return True
    if text.startswith("You are processing one item for a generic agent job."):
        return True
    if "Job ID:" in text and "Item ID:" in text and "Task instruction:" in text:
        return True
    if not include_automations and text.startswith("Automation:"):
        return True
    if "--- project-doc ---" in text:
        return True
    if "<environment_context>" in text and "<current_date>" in text:
        return True
    if len(text) > 20_000 and "<INSTRUCTIONS>" in text:
        return True
    return False


def compile_patterns() -> list[TermPattern]:
    patterns: list[TermPattern] = []
    for category, spec in SWEAR_INDEX_LEXICON.items():
        group = str(spec["group"])
        weight = int(spec["weight"])
        for term in spec["terms"]:
            patterns.append(
                TermPattern(
                    category=category,
                    group=group,
                    term=str(term),
                    weight=weight,
                    pattern=re.compile(_term_to_regex(str(term)), re.IGNORECASE),
                )
            )
    return patterns


def _term_to_regex(term: str) -> str:
    escaped = re.escape(term.strip())
    escaped = re.sub(r"\\\s+", r"\\s+", escaped)
    if term and term[0].isalnum():
        escaped = r"(?<![A-Za-z0-9_])" + escaped
    if term and term[-1].isalnum():
        escaped = escaped + r"(?![A-Za-z0-9_])"
    return escaped


PATTERNS = compile_patterns()


def match_message(message: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for pattern in PATTERNS:
        matches = list(pattern.pattern.finditer(message))
        if not matches:
            continue
        if pattern.term.casefold() in SWEAR_INDEX_EXCLUDED_TERMS:
            continue
        if pattern.group not in SWEAR_INDEX_GROUPS:
            continue
        hits.append(
            {
                "category": pattern.category,
                "group": pattern.group,
                "term": pattern.term,
                "weight": pattern.weight,
                "count": len(matches),
                "firstStart": matches[0].start(),
            }
        )
    hits.sort(key=lambda hit: (hit["firstStart"], hit["category"], hit["term"]))
    return hits


def empty_swear_meter() -> dict[str, Any]:
    return {
        "directUserMessages": 0,
        "swearIndexMessages": 0,
        "swearIndexOccurrences": 0,
        "swearIndexScore": 0,
        "groups": Counter(),
        "terms": Counter(),
        "termOccurrences": Counter(),
        "timeline": Counter(),
    }


def analyze_user_message(message: str, timestamp: str | None = None) -> dict[str, Any]:
    result = empty_swear_meter()
    if should_skip_message(message):
        return result

    result["directUserMessages"] = 1
    hits = match_message(message)
    day = str(timestamp or "")[:10]
    if day:
        result["timeline"][(day, "messages")] += 1
    if not hits:
        return result

    result["swearIndexMessages"] = 1
    if day:
        result["timeline"][(day, "swearMessages")] += 1
    for hit in hits:
        occurrences = int(hit["count"])
        result["swearIndexOccurrences"] += occurrences
        result["swearIndexScore"] += int(hit["weight"]) * occurrences
        result["groups"][hit["group"]] += occurrences
        result["terms"][hit["term"]] += 1
        result["termOccurrences"][hit["term"]] += occurrences
    return result


def merge_swear_meter(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["directUserMessages"] += int(source.get("directUserMessages") or 0)
    target["swearIndexMessages"] += int(source.get("swearIndexMessages") or 0)
    target["swearIndexOccurrences"] += int(source.get("swearIndexOccurrences") or 0)
    target["swearIndexScore"] += int(source.get("swearIndexScore") or 0)
    target["groups"].update(source.get("groups") or {})
    target["terms"].update(source.get("terms") or {})
    target["termOccurrences"].update(source.get("termOccurrences") or {})
    target["timeline"].update(source.get("timeline") or {})


def finalize_swear_meter(summary: dict[str, Any]) -> dict[str, Any]:
    messages = int(summary.get("directUserMessages") or 0)
    swear_messages = int(summary.get("swearIndexMessages") or 0)
    term_occurrences = summary.get("termOccurrences") or Counter()
    days = sorted({key[0] for key in (summary.get("timeline") or {}).keys()})
    return {
        "directUserMessages": messages,
        "swearIndexMessages": swear_messages,
        "swearIndexOccurrences": int(summary.get("swearIndexOccurrences") or 0),
        "swearIndexScore": int(summary.get("swearIndexScore") or 0),
        "swearIndexRate": round((swear_messages / messages) * 100, 2) if messages else 0,
        "groups": dict((summary.get("groups") or Counter()).most_common(12)),
        "terms": [
            {
                "term": term,
                "messages": count,
                "occurrences": int(term_occurrences.get(term) or 0),
            }
            for term, count in (summary.get("terms") or Counter()).most_common(12)
        ],
        "timeline": [
            {
                "day": day,
                "messages": int((summary.get("timeline") or {}).get((day, "messages")) or 0),
                "swearMessages": int((summary.get("timeline") or {}).get((day, "swearMessages")) or 0),
            }
            for day in days
        ],
    }
