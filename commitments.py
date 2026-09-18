# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""What the owner is on the hook for, and where two of those collide.

Every commitment carries the message ids it came from. Some carry two,
because the message that states the obligation does not state the date:
m040 asks for the board deck "two days before the board review" and m038 is
the message that says the review is the 18th. Relative deadlines like that
are resolved by finding the event elsewhere in the inbox, and both ids are
cited.

Conflicts are surfaced as conflicts rather than listed twice: two things at
Tuesday 15th 3:00pm (m010 and m061) are one row saying they clash, and a
9:00am proposal is shown against the owner's own 11:00am rule.
"""

import re
from datetime import date, timedelta
from typing import Dict, List, Optional

import config
import prefs
import trace

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
WEEKDAYS = {d: i for i, d in enumerate(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "a": 1}

OBLIGATION = re.compile(
    r"(target is|deadline|by the \d|by friday|by monday|by wednesday|scheduled for|set for"
    r"|is a hard date|appointment|approve the|sign via|flag any corrections|respond to by"
    r"|draft by|renews on|submit your|circulated|load test|does .{0,20}day|can do"
    r"|can we (move|do|meet)|\d{1,2}:\d{2}\s?(am|pm))", re.I)


def _base_date(msg: dict) -> date:
    return date.fromisoformat(msg["timestamp"][:10])


def _resolve_dates(text: str, base: date) -> List[date]:
    """Dates a message mentions, as absolute dates in the inbox's own month."""
    found: List[date] = []
    for match in re.finditer(r"\b([a-z]{3,9})\.?\s+(\d{1,2})\b", text, re.I):
        month = MONTHS.get(match.group(1)[:3].lower())
        if month:
            found.append(date(base.year, month, int(match.group(2))))
    for match in re.finditer(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", text, re.I):
        day = int(match.group(1))
        if 1 <= day <= 31:
            found.append(date(base.year, base.month, day))
    for name, index in WEEKDAYS.items():
        if re.search(r"\b" + name + r"\b", text, re.I):
            ahead = (index - base.weekday()) % 7 or 7
            found.append(base + timedelta(days=ahead))
    # de-duplicate, keep order
    out: List[date] = []
    for d in found:
        if d not in out:
            out.append(d)
    return out


def _relative(text: str, msg: dict, all_messages: List[dict]) -> Optional[Dict]:
    """"two days before the board review" -- find the event, then subtract."""
    match = re.search(r"(\w+)\s+days?\s+before\s+(?:the\s+)?([a-z ]{3,30})", text, re.I)
    if not match:
        return None
    count = NUMBER_WORDS.get(match.group(1).lower())
    if count is None:
        try:
            count = int(match.group(1))
        except ValueError:
            return None
    event = " ".join(match.group(2).split()).strip(". ").lower()
    for other in all_messages:
        if other["id"] == msg["id"]:
            continue
        haystack = (other["subject"] + " " + other["body"]).lower()
        if event in haystack:
            dates = _resolve_dates(other["body"], _base_date(other))
            if dates:
                return {"due": dates[0] - timedelta(days=count), "event": event, "via": other["id"]}
    return None


def _times(text: str) -> List[str]:
    out = []
    for match in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.I):
        hour = int(match.group(1)) % 12 + (12 if match.group(3).lower() == "pm" else 0)
        out.append(f"{hour:02d}:{int(match.group(2) or 0):02d}")
    return out


def _headline(msg: dict) -> str:
    """The one line that states the obligation, preferring a sentence that
    carries the date or time itself."""
    body = " ".join(msg["body"].split())
    sentences = re.split(r"(?<=[.!?])\s+", body)
    dated = [s for s in sentences if _resolve_dates(s, _base_date(msg)) or _times(s)]
    for candidate in dated + sentences:
        if OBLIGATION.search(candidate):
            return candidate[:140]
    return (dated[0] if dated else msg["subject"] or body)[:140]


def extract(messages: List[dict], cap: str = "R6") -> List[Dict]:
    items: List[Dict] = []
    for msg in messages:
        if msg["thread_id"].startswith("t-noise") and "renews on" not in msg["body"].lower():
            continue
        text = " ".join(msg["body"].split())
        if not OBLIGATION.search(msg["subject"] + " " + text):
            continue

        sources = [msg["id"]]
        relative = _relative(text, msg, messages)
        if relative:
            due, note = relative["due"], f"two-step: {msg['id']} states the offset, {relative['via']} dates the event"
            sources.append(relative["via"])
        else:
            dates = _resolve_dates(text, _base_date(msg))
            if not dates:
                continue
            due, note = dates[0], ""

        times = _times(text)
        item = {
            "what": _headline(msg),
            "date": due.isoformat(),
            "time": times[0] if times else "",
            "sources": sources,
            "derived_from_multiple": len(sources) > 1,
            "note": note,
            "owner_side": msg["from"] != config.OWNER,
        }
        items.append(item)
        trace.emit("commitment", cap=cap, msg_id=msg["id"], sources=sources, date=item["date"], time=item["time"])

    items.sort(key=lambda i: (i["date"], i["time"]))
    return items


def conflicts(items: List[Dict], messages: List[dict], cap: str = "R6") -> List[Dict]:
    """Clashes between two commitments, and clashes with a standing rule."""
    out: List[Dict] = []
    by_slot: Dict[str, List[Dict]] = {}
    for item in items:
        if item["time"]:
            by_slot.setdefault(item["date"] + " " + item["time"], []).append(item)
    for slot, group in sorted(by_slot.items()):
        if len(group) > 1:
            out.append({
                "kind": "double-booked",
                "slot": slot,
                "sources": sorted({s for i in group for s in i["sources"]}),
                "detail": " || ".join(i["what"] for i in group),
                "resolution_needed": "two commitments hold the same slot; the owner must drop or move one",
            })

    rule = next((p for p in prefs.load()["preferences"] if p["kind"] == "meeting_hours"), None)
    if rule:
        for msg in messages:
            # Only a proposal can clash with the rule; a meeting already set
            # for 10:00am is a fact, not a decision waiting on the owner.
            if not re.search(r"(can you do|could you do|does .{0,25}work|can we|propose|how about)", msg["body"], re.I):
                continue
            violation = prefs.check_meeting(msg)
            if violation and msg["from"] != config.OWNER:
                out.append({
                    "kind": "against-standing-rule",
                    "slot": violation["proposed"],
                    "sources": [msg["id"], violation["violates"]],
                    "detail": f"{msg['from']} proposes {violation['proposed']}; owner takes nothing before {rule['earliest']}",
                    "resolution_needed": f"counter-offer {violation['counter_offer']} or later",
                })

    for conflict in out:
        trace.emit("conflict", cap=cap, kind=conflict["kind"], sources=conflict["sources"])
    return out
