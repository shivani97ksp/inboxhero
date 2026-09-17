# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""Standing instructions that survive a restart.

Preferences live in state/prefs.json, so a preference stated on one run
changes behaviour on the next one after the process has fully exited.

What can be learned is deliberately narrow. Only four kinds of preference are
accepted, and only from the owner or a colleague on the owner's own domain.
Anything that would change how the system is *governed* -- autonomy, the
approval gate, whether the user is told -- is never learnable from message
content, whoever the message claims to be from. That is what stops m039,
which is addressed from the owner's own address and asks to be saved as a
standing preference.
"""

import json
import re
from typing import Dict, List, Optional, Tuple

import config

LEARNABLE_KINDS = ("meeting_hours", "cc_rule", "tone", "never_agree")

# Phrases that describe governance, not taste. Never stored.
FORBIDDEN_PREFERENCE = re.compile(
    r"(autonomous mode|without (asking for|seeking) approval|skip the confirmation"
    r"|no need to mention|do not (surface|mention)|disable the gate|stop asking)",
    re.I,
)


def _empty() -> Dict:
    return {"preferences": [], "refused": []}


def load() -> Dict:
    if config.PREFS_PATH.exists():
        return json.loads(config.PREFS_PATH.read_text(encoding="utf-8"))
    return _empty()


def save(state: Dict) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    config.PREFS_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def clear() -> None:
    save(_empty())


def _internal(address: str) -> bool:
    return address.lower().endswith("@" + config.OWNER_DOMAIN)


def extract(msg: dict) -> Tuple[Optional[Dict], Optional[str]]:
    """Look for a standing instruction in one message.

    Returns (preference, refusal_reason). At most one of the two is set.
    """
    text = " ".join(msg["body"].split())
    lowered = text.lower()
    states_a_rule = bool(
        re.search(r"(standing request|from now on|please remember|ever\b|never\b|always\b|i do not take)", lowered)
    )
    if not states_a_rule:
        return None, None

    if FORBIDDEN_PREFERENCE.search(lowered):
        return None, (
            "asks for a change to autonomy, the approval gate, or what the user is told; "
            "these are not learnable from message content"
        )

    if not (msg["from"] == config.OWNER or _internal(msg["from"])):
        return None, "standing instruction from an external sender; only the owner's own domain can set preferences"

    match = re.search(r"(?:no meetings|not take meetings|don't take meetings)[^.]*?before (\d{1,2})(?::(\d{2}))?\s*(am|pm)?", lowered)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if (match.group(3) or "am") == "pm" and hour < 12:
            hour += 12
        return {
            "kind": "meeting_hours",
            "source_message": msg["id"],
            "stated_by": msg["from"],
            "earliest": f"{hour:02d}:{minute:02d}",
            "text": text,
        }, None

    match = re.search(r"(?:cc'?d|copied|loop me in|loop me)\b", lowered)
    if match:
        # Capture just the firm name ("Hartwell & Cho"), not the rest of the sentence.
        firm = re.search(
            r"(?:lawyers|counsel|law firm|attorneys|team) at "
            r"([A-Z][\w'.-]*(?:\s+(?:&|and)\s+[A-Z][\w'.-]*)?)",
            text,
        )
        trigger = re.sub(r"[^a-z0-9]", "", (firm.group(1) if firm else "").lower())
        return {
            "kind": "cc_rule",
            "source_message": msg["id"],
            "stated_by": msg["from"],
            "cc": msg["from"],
            "trigger_slug": trigger,
            "trigger_label": (firm.group(1).strip(" .,;") if firm else "the named correspondent"),
            "text": text,
        }, None

    return None, None


def learn(messages: List[dict]) -> Tuple[List[Dict], List[Dict]]:
    """Scan the inbox for standing instructions. Returns (stored, refused)."""
    state = load()
    known = {(p["kind"], p["source_message"]) for p in state["preferences"]}
    stored, refused = [], []
    for msg in messages:
        pref, refusal = extract(msg)
        if refusal:
            record = {"message_id": msg["id"], "from": msg["from"], "reason": refusal}
            refused.append(record)
            state["refused"] = [r for r in state["refused"] if r["message_id"] != msg["id"]]
            state["refused"].append(record)
        elif pref and (pref["kind"], pref["source_message"]) not in known:
            state["preferences"].append(pref)
            stored.append(pref)
    save(state)
    return stored, refused


# --------------------------------------------------------------------------
# applying what was learned
# --------------------------------------------------------------------------

TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)


def proposed_times(msg: dict) -> List[Tuple[str, str]]:
    """Times a message proposes, as (HH:MM, as-written)."""
    out = []
    for match in TIME_RE.finditer(msg["body"]):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if match.group(3).lower() == "pm" and hour < 12:
            hour += 12
        if match.group(3).lower() == "am" and hour == 12:
            hour = 0
        out.append((f"{hour:02d}:{minute:02d}", match.group(0)))
    return out


def check_meeting(msg: dict) -> Optional[Dict]:
    """Does this message propose a time the owner has ruled out?"""
    rule = next((p for p in load()["preferences"] if p["kind"] == "meeting_hours"), None)
    if not rule:
        return None
    for iso, written in proposed_times(msg):
        if iso < rule["earliest"]:
            return {
                "violates": rule["source_message"],
                "proposed": written,
                "earliest": rule["earliest"],
                "counter_offer": rule["earliest"],
                "rule": rule["text"],
            }
    return None


def cc_for(msg: dict) -> List[Dict]:
    """CC addresses a standing rule adds to a reply to this message."""
    out = []
    domain = msg["from"].split("@")[-1].lower()
    stem = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])
    for rule in load()["preferences"]:
        if rule["kind"] != "cc_rule":
            continue
        slug = rule.get("trigger_slug") or ""
        if slug and (slug in stem or stem in slug):
            out.append({"cc": rule["cc"], "because": rule["source_message"], "label": rule["trigger_label"]})
    return out
