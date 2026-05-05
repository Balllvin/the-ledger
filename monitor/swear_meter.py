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

SWEAR_INDEX_EXCLUDED_TERMS: set[str] = set()

SWEAR_INDEX_LEXICON = {
    "hard_swearing": {
        "group": "swearing",
        "weight": 4,
        "label": "Hard Swearing",
        "terms": [
            "fuck",
            "fucking",
            "fucked",
            "fucks",
            "fucker",
            "fuckers",
            "fuck off",
            "fuck you",
            "fuck this",
            "fuck that",
            "fuck sake",
            "fuck's sake",
            "for fuck's sake",
            "for fucks sake",
            "af",
            "as fuck",
            "fucked up",
            "fucking up",
            "fucking awful",
            "fucking terrible",
            "fucking useless",
            "fucking ridiculous",
            "no fucking way",
            "jesus fucking christ",
            "jesus christ",
            "holy shit",
            "motherfucker",
            "motherfucking",
            "mother fucker",
            "shit",
            "shitty",
            "shite",
            "shitting",
            "shitshow",
            "shit show",
            "piece of shit",
            "pieces of shit",
            "full of shit",
            "load of shit",
            "total shit",
            "complete shit",
            "batshit",
            "horseshit",
            "bull shit",
            "bullshitted",
            "bullshit",
            "bullshitting",
            "wtf",
            "wtaf",
            "ffs",
            "fml",
            "stfu",
            "asshole",
            "arsehole",
            "ass hole",
            "dumbass",
            "dumb ass",
            "bastard",
            "bollocks",
            "fucjing",
            "fuk",
            "fck",
            "fuking",
            "fcking",
            "fukker",
            "cunt",
            "cunting",
            "cuntish",
            "bitch",
            "bitchy",
            "bitching",
            "son of a bitch",
            "sob",
            "twat",
            "prick",
            "wanker",
            "knob",
            "knobhead",
            "dick",
            "dickhead",
            "dickwad",
            "pussy",
            "pussy ass",
            "cock",
            "cocksucker",
            "arse",
            "git",
            "tosser",
            "bellend",
            "minger",
            "slag",
            "whore",
            "fuckwit",
            "fucktard",
            "shithead",
            "shitforbrains",
            "clusterfuck",
            "shitstorm",
            "fuckery",
            "fuckall",
        ],
    },
    "soft_swearing": {
        "group": "swearing",
        "weight": 2,
        "label": "Soft Swearing",
        "terms": [
            "damn",
            "damned",
            "dammit",
            "damnit",
            "damn it",
            "goddamn",
            "god damn",
            "goddammit",
            "goddamnit",
            "for god's sake",
            "for gods sake",
            "crap",
            "crappy",
            "crappiest",
            "bloody hell",
            "fucking hell",
            "screw this",
            "screwed up",
            "screwing up",
            "pissed",
            "pissed off",
            "what the heck",
            "heck",
            "hell",
            "darn",
            "dang",
            "dagnabbit",
            "frigging",
            "frick",
            "frickin",
            "fricking",
            "gosh darn",
            "jeez",
            "jesus",
            "christ",
            "christ on a bike",
            "holy crap",
            "holy hell",
            "oh for crying out loud",
            "oh come on",
        ],
    },
    "wtf_moment": {
        "group": "spicy_moment",
        "weight": 4,
        "label": "WTF / Confusion",
        "terms": [
            "what the fuck",
            "what the actual fuck",
            "what the hell",
            "what in the hell",
            "why the hell",
            "how the hell",
            "where the hell",
            "what the hell is this",
            "what the hell are you doing",
            "what the fucking hell",
            "what the heck",
            "wth",
            "wtf is this",
            "are you kidding me",
            "are you fucking kidding me",
            "are you serious",
            "you have got to be kidding",
            "you've got to be kidding",
            "you must be kidding",
            "fuck sake",
            "wtf man",
            "come on man",
            "seriously",
            "what is going on here",
            "what happened",
            "what is happening",
            "why is this happening",
            "what is this",
            "what is this nonsense",
            "this makes no sense",
            "i don't get it",
            "you can't be serious",
            "what the actual",
            "come on",
        ],
    },
    "anger_callout": {
        "group": "frustrated_rework",
        "weight": 3,
        "label": "Anger Callouts",
        "terms": [
            "you said",
            "you told me",
            "you didn't",
            "you did not",
            "you haven't",
            "you have not",
            "you should have",
            "why did you",
            "you missed",
            "you ignored",
            "not what i asked",
            "that's not what i asked",
            "this isn't what",
            "i asked you",
            "i asked for",
            "i told you",
            "i told you to",
            "wrong thing",
            "not the point",
            "read the prompt",
            "follow the instructions",
            "actually do",
            "try again",
            "redo",
            "start over",
            "what are you doing",
            "what have you done",
            "what did you do",
            "what's up with that",
            "why would you",
            "why are you doing",
            "do you even understand",
            "you are not listening",
            "you are not reading",
            "you are not checking",
            "you are not following",
            "what a joke",
            "absolute joke",
            "complete joke",
            "load of crap",
            "load of bullshit",
            "this is bullshit",
            "driving me crazy",
            "driving me nuts",
            "driving me mad",
            "i can't believe this",
            "i can't believe you",
            "again",
            "still broken",
            "still not working",
            "keeps happening",
        ],
    },
    "incomplete_failure": {
        "group": "quality_critique",
        "weight": 3,
        "label": "Incomplete / Failure",
        "terms": [
            "not done",
            "isn't done",
            "this is incomplete",
            "still incomplete",
            "unfinished",
            "left out",
            "you skipped",
            "you stopped",
            "this is not enough",
            "that's not enough",
            "barely visible",
            "finish it",
            "finish the job",
            "actually finish",
            "half a job",
            "you keep stopping",
            "not doing the work",
            "do the actual work",
            "not working at all",
            "doesn't work at all",
            "nothing works",
            "can't use this",
            "unusable",
            "useless",
            "can't see any data",
            "hard to read",
            "hard to navigate",
            "things are stuck",
            "doesn't seem to be progressing",
            "broken",
            "broke",
            "crashed",
            "crash",
            "failing",
            "failure",
            "bug",
            "issue",
            "problem",
            "regression",
            "wrong",
            "error",
            "sloppy",
            "lazy",
            "generic",
            "low quality",
            "looks bad",
            "looks awful",
            "looks terrible",
            "looks ugly",
            "garbage output",
        ],
    },
    "trust_break": {
        "group": "boundary_violation",
        "weight": 4,
        "label": "Trust Break",
        "terms": [
            "pretend",
            "pretending",
            "made up",
            "making it up",
            "invented",
            "fabricated",
            "hallucinated",
            "hallucination",
            "hallucinating",
            "hallucinating again",
            "just guessing",
            "you assumed",
            "without checking",
            "didn't actually",
            "not verified",
            "fake progress",
            "bogus",
            "unsupported",
            "not real",
            "source doesn't say",
            "show me evidence",
            "prove it",
            "you're lying",
            "this is a lie",
            "made this up",
            "you made this up",
            "not true",
            "isn't true",
        ],
    },
    "quality_rejection": {
        "group": "quality_critique",
        "weight": 3,
        "label": "Quality Rejection",
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
            "this is bullshit",
            "hot garbage",
            "this is useless",
            "completely useless",
            "useless output",
            "this is nonsense",
            "that is nonsense",
            "nonsense",
            "this is junk",
            "junk",
            "trash",
            "this is trash",
            "trash output",
            "horrible",
            "this is horrible",
            "i hate this",
            "i hate it",
            "not remotely good enough",
            "not good enough",
            "not even close",
            "nowhere near good enough",
            "doesn't make sense",
            "does not make sense",
            "makes no sense",
            "looks ugly",
            "really ugly",
            "i really hate this",
            "ugly",
            "disgusting",
            "trashy",
            "sloppy work",
            "lazy work",
            "half-assed",
            "half baked",
            "total mess",
            "bit of a mess",
            "this is a mess",
            "you've messed up",
            "you messed up",
            "made it worse",
            "this is worse now",
            "much worse",
            "even worse",
            "waste of time",
            "wasting my time",
            "frustrating",
            "annoying",
            "disappointing",
            "unacceptable",
            "completely unacceptable",
            "delete this",
            "delete this shit",
            "start again",
            "redo from scratch",
            "do something completely different",
            "i want to cry",
            "i can't follow",
            "nothing worked",
            "nothing changed",
            "same problem",
            "still failing",
            "this looks garbage",
        ],
    },
    "unacceptable_boundary": {
        "group": "boundary_violation",
        "weight": 3,
        "label": "Boundary / No Shortcuts",
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
            "throw this away",
            "throw it away",
            "scrap this",
            "scrap it",
            "no shortcuts",
            "don't pretend",
            "don't assume",
            "don't guess",
            "don't hand-wave",
            "full rebuild",
            "actually do it",
            "do it properly",
            "not a mock",
            "real check",
            "paper over",
            "fake progress",
            "this is not acceptable",
            "kill this",
        ],
    },
    "rework_cost": {
        "group": "frustrated_rework",
        "weight": 2,
        "label": "Rework Cost",
        "terms": [
            "waste of time",
            "wasted time",
            "wasting time",
            "waste my time",
            "wasting my time",
            "you are wasting my time",
            "real nightmare",
            "complete nightmare",
            "nightmare",
            "this is a mess",
            "it's a mess",
            "it is a mess",
            "messy",
            "too messy",
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
            "worse than before",
        ],
    },
    "ai_coding_failure": {
        "group": "quality_critique",
        "weight": 3,
        "label": "AI Coding Failure",
        "terms": [
            "keeps looping",
            "looping forever",
            "infinite loop",
            "repeating itself",
            "making shit up",
            "inventing code",
            "wrong code",
            "broken code",
            "syntax error every time",
            "doesn't compile",
            "won't run",
            "crashes on load",
            "useless suggestion",
            "terrible suggestion",
            "ignores my instructions",
            "ignores the spec",
            "off topic",
            "completely irrelevant",
            "why are you adding that",
            "stop adding extra",
            "stop hallucinating",
            "this is not what i wanted",
            "back to square one",
            "starting over again",
            "another waste",
            "another failure",
            "why won't you listen",
            "listen to me",
            "follow the prompt damn it",
        ],
    },
}


@dataclass(frozen=True)
class TermPattern:
    category: str
    group: str
    label: str
    term: str
    normalized: str
    weight: int


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
        label = str(spec.get("label") or category.replace("_", " ").title())
        weight = int(spec["weight"])
        for term in dict.fromkeys(spec["terms"]):
            patterns.append(
                TermPattern(
                    category=category,
                    group=group,
                    label=label,
                    term=str(term),
                    normalized=_normalize_term(str(term)),
                    weight=weight,
                )
            )
    return sorted(patterns, key=lambda item: (-len(item.term), -item.weight, item.category, item.term))


def _normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.casefold().strip())


def _normalize_message(message: str) -> str:
    return re.sub(r"\s+", " ", message.casefold())


def _has_word_boundary(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return (not before or not (before.isalnum() or before == "_")) and (not after or not (after.isalnum() or after == "_"))


PATTERNS = compile_patterns()


def match_message(message: str) -> list[dict[str, Any]]:
    normalized = _normalize_message(message)
    by_term: dict[tuple[str, str], dict[str, Any]] = {}
    occupied: list[tuple[int, int]] = []
    for pattern in PATTERNS:
        if pattern.term.casefold() in SWEAR_INDEX_EXCLUDED_TERMS:
            continue
        if pattern.group not in SWEAR_INDEX_GROUPS:
            continue
        start = normalized.find(pattern.normalized)
        while start != -1:
            end = start + len(pattern.normalized)
            if _has_word_boundary(normalized, start, end) and not any(start < taken_end and end > taken_start for taken_start, taken_end in occupied):
                occupied.append((start, end))
                key = (pattern.category, pattern.term)
                hit = by_term.setdefault(
                    key,
                    {
                        "category": pattern.category,
                        "group": pattern.group,
                        "label": pattern.label,
                        "term": pattern.term,
                        "weight": pattern.weight,
                        "count": 0,
                        "firstStart": start,
                    },
                )
                hit["count"] += 1
                hit["firstStart"] = min(int(hit["firstStart"]), start)
            start = normalized.find(pattern.normalized, start + 1)
    hits = list(by_term.values())
    hits.sort(key=lambda hit: (hit["firstStart"], hit["category"], hit["term"]))
    return hits


def empty_swear_meter() -> dict[str, Any]:
    return {
        "directUserMessages": 0,
        "swearIndexMessages": 0,
        "swearIndexOccurrences": 0,
        "swearIndexScore": 0,
        "groups": Counter(),
        "categories": Counter(),
        "categoryMessages": Counter(),
        "categoryScores": Counter(),
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
    categories_in_message = set()
    for hit in hits:
        occurrences = int(hit["count"])
        result["swearIndexOccurrences"] += occurrences
        result["swearIndexScore"] += int(hit["weight"]) * occurrences
        result["groups"][hit["group"]] += occurrences
        result["categories"][hit["category"]] += occurrences
        result["categoryScores"][hit["category"]] += int(hit["weight"]) * occurrences
        categories_in_message.add(hit["category"])
        if day:
            result["timeline"][(day, f"category:{hit['category']}")] += occurrences
        result["terms"][hit["term"]] += 1
        result["termOccurrences"][hit["term"]] += occurrences
    for category in categories_in_message:
        result["categoryMessages"][category] += 1
        if day:
            result["timeline"][(day, f"categoryMessages:{category}")] += 1
    return result


def merge_swear_meter(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["directUserMessages"] += int(source.get("directUserMessages") or 0)
    target["swearIndexMessages"] += int(source.get("swearIndexMessages") or 0)
    target["swearIndexOccurrences"] += int(source.get("swearIndexOccurrences") or 0)
    target["swearIndexScore"] += int(source.get("swearIndexScore") or 0)
    target["groups"].update(source.get("groups") or {})
    target["categories"].update(source.get("categories") or {})
    target["categoryMessages"].update(source.get("categoryMessages") or {})
    target["categoryScores"].update(source.get("categoryScores") or {})
    target["terms"].update(source.get("terms") or {})
    target["termOccurrences"].update(source.get("termOccurrences") or {})
    target["timeline"].update(source.get("timeline") or {})


def finalize_swear_meter(summary: dict[str, Any]) -> dict[str, Any]:
    messages = int(summary.get("directUserMessages") or 0)
    swear_messages = int(summary.get("swearIndexMessages") or 0)
    term_occurrences = summary.get("termOccurrences") or Counter()
    days = sorted({key[0] for key in (summary.get("timeline") or {}).keys()})
    category_occurrences = summary.get("categories") or Counter()
    category_messages = summary.get("categoryMessages") or Counter()
    category_scores = summary.get("categoryScores") or Counter()
    categories = []
    for category, spec in SWEAR_INDEX_LEXICON.items():
        occurrences = int(category_occurrences.get(category) or 0)
        category_message_count = int(category_messages.get(category) or 0)
        if not occurrences and not category_message_count:
            continue
        categories.append(
            {
                "id": category,
                "label": str(spec.get("label") or category.replace("_", " ").title()),
                "group": str(spec["group"]),
                "weight": int(spec["weight"]),
                "messages": category_message_count,
                "occurrences": occurrences,
                "score": int(category_scores.get(category) or 0),
            }
        )
    categories.sort(key=lambda row: (int(row["score"]), int(row["occurrences"]), int(row["messages"])), reverse=True)
    return {
        "directUserMessages": messages,
        "swearIndexMessages": swear_messages,
        "swearIndexOccurrences": int(summary.get("swearIndexOccurrences") or 0),
        "swearIndexScore": int(summary.get("swearIndexScore") or 0),
        "swearIndexRate": round((swear_messages / messages) * 100, 2) if messages else 0,
        "groups": dict((summary.get("groups") or Counter()).most_common(12)),
        "categories": categories,
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
                "categories": {
                    category: {
                        "messages": int((summary.get("timeline") or {}).get((day, f"categoryMessages:{category}")) or 0),
                        "occurrences": int((summary.get("timeline") or {}).get((day, f"category:{category}")) or 0),
                    }
                    for category in SWEAR_INDEX_LEXICON
                    if (summary.get("timeline") or {}).get((day, f"categoryMessages:{category}"))
                    or (summary.get("timeline") or {}).get((day, f"category:{category}"))
                },
            }
            for day in days
        ],
    }
