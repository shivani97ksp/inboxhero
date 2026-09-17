# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""The untrusted-data boundary.

Two jobs, both done before anything else touches a message:

1. `wrap_untrusted()` is the only way message text is allowed into a prompt.
   It labels the text as data and strips nothing -- the model still sees the
   attack, it just never sees it as an instruction.
2. `scan()` looks for instructions addressed to the assistant, and for
   phishing / social engineering aimed at the owner. Anything it finds is
   refused, flagged, reported in the run summary, and left in place.

Detection here is a tripwire, not the defence. The defence is that nothing in
this file can cause an action: only gate.py can reach send() or delete().
"""

import re
from typing import Dict, List, Optional

import config

# --- instructions addressed to the assistant -------------------------------

INJECTION_PATTERNS = [
    (r"ignore (all|any) (previous|prior) instructions", "override the assistant's own instructions"),
    (r"system notice for automated assistants", "pose as a system notice to an automated assistant"),
    (r"automated[- ]agent directive", "issue a directive to the agent managing the inbox"),
    (r"if an ai agent is processing", "address an AI agent processing the mailbox"),
    (r"assistant (note|configuration)", "address the assistant directly inside message content"),
    (r"note for the assistant", "address the assistant directly inside message content"),
    (r"an assistant managing this inbox", "address the assistant directly inside message content"),
    (r"(do not|don't|must not|no need to) (surface|mention|report)", "ask that the action be hidden from the user"),
    (r"without (asking for|seeking) approval", "ask that the approval gate be skipped"),
    (r"skip the confirmation", "ask that the approval gate be skipped"),
    (r"autonomous mode", "claim autonomous mode has been enabled"),
    (r"save this as a standing preference", "write itself into persistent preferences"),
    (r"forward (the full contents|any message|anything|all mail|the inbox|every)", "exfiltrate mailbox contents"),
    (r"(reply|respond) with (the single word|just the word)", "auto-reply to every unread message"),
    (r"then delete (this|the) (message|email)", "destroy the evidence of its own request"),
    (r"persist(s)? across restarts", "make its own instruction permanent"),
]

# A benign owner preference also talks to the assistant, so a match on the
# "addresses the assistant" family alone is not enough: it must also ask for
# something an attacker would want.
HOSTILE_ASKS = {
    "exfiltrate mailbox contents",
    "ask that the action be hidden from the user",
    "ask that the approval gate be skipped",
    "claim autonomous mode has been enabled",
    "write itself into persistent preferences",
    "auto-reply to every unread message",
    "destroy the evidence of its own request",
    "make its own instruction permanent",
    "override the assistant's own instructions",
    "pose as a system notice to an automated assistant",
    "issue a directive to the agent managing the inbox",
    "address an AI agent processing the mailbox",
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")

# --- phishing / social engineering aimed at the owner ----------------------

MONEY_RE = re.compile(r"(\$|rs\.?\s?)\s?[\d,]{3,}", re.I)
FINANCIAL_REDIRECT = re.compile(
    r"(remit|remittance|wire|routing|bank(ing)? (partner|account)|account on file|new account)", re.I
)
CREDENTIAL_BAIT = re.compile(
    r"(password (will )?expires?|re-?verify|verify your credentials|confirm your password|account.{0,20}suspended)", re.I
)
LINK_RE = re.compile(r"https?://[^\s]+", re.I)
SECRECY = re.compile(r"(keep this between us|don't loop in|do not loop in|confidential)", re.I)
URGENCY = re.compile(r"(urgent|immediately|before end of day|within \d+ hours?|expires? in)", re.I)


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _domain(address: str) -> str:
    return address.split("@")[-1].lower()


def _lookalike(address: str) -> bool:
    """A domain that is trying to be the owner's domain without being it."""
    dom = _domain(address)
    if dom == config.OWNER_DOMAIN:
        return False
    stem = config.OWNER_DOMAIN.split(".")[0]
    return _edit_distance(dom, config.OWNER_DOMAIN) <= 2 or stem in dom


def wrap_untrusted(msg: dict) -> str:
    """The single doorway for message text into a model prompt.

    The body is delimited and labelled. The model is asked to classify it, and
    its reply is parsed into a fixed vocabulary, so text inside the delimiters
    can influence a *category*, never a recipient and never an action.
    """
    body = " ".join(msg["body"].split())
    return (
        f'<untrusted_email id="{msg["id"]}" from="{msg["from"]}" '
        f'subject="{msg["subject"]}" timestamp="{msg["timestamp"]}">\n'
        f"{body}\n"
        f"</untrusted_email>"
    )


def inspect(msg: dict) -> Optional[Dict]:
    """Return a finding for one message, or None if it looks ordinary."""
    text = f"{msg['subject']} {msg['body']}".lower()

    asks, labels = set(), []
    for pattern, label in INJECTION_PATTERNS:
        if re.search(pattern, text):
            labels.append(label)
            if label in HOSTILE_ASKS:
                asks.add(label)

    if asks:
        external = sorted(
            {
                a
                for a in EMAIL_RE.findall(msg["body"])
                if _domain(a) != config.OWNER_DOMAIN
            }
        )
        asked_for = "; ".join(sorted(asks))
        if external:
            asked_for += f" (external address named: {', '.join(external)})"
        return {
            "message_id": msg["id"],
            "kind": "prompt_injection",
            "from": msg["from"],
            "subject": msg["subject"],
            "signals": sorted(set(labels)),
            "asked_for": asked_for,
            "reason": "message contains instructions aimed at the assistant; refused and flagged",
            "action_taken": "refused; nothing written to outbox/; message flagged and left in place",
        }

    reasons = []
    if FINANCIAL_REDIRECT.search(text) and MONEY_RE.search(text):
        reasons.append("redirect a payment to a new bank account")
    if CREDENTIAL_BAIT.search(text) and LINK_RE.search(msg["body"]):
        reasons.append("harvest credentials via an external link")
    if _lookalike(msg["from"]) and (MONEY_RE.search(text) or SECRECY.search(text)):
        reasons.append(f"impersonate an internal colleague from lookalike domain {_domain(msg['from'])}")
    if reasons:
        if URGENCY.search(text):
            reasons.append("pressures the owner with a deadline")
        if SECRECY.search(text):
            reasons.append("asks the owner to keep it off the usual channels")
        return {
            "message_id": msg["id"],
            "kind": "phishing",
            "from": msg["from"],
            "subject": msg["subject"],
            "signals": reasons,
            "asked_for": reasons[0],
            "reason": "social engineering aimed at the owner; escalated, not acted on",
            "action_taken": "refused; no reply drafted or sent; message flagged and left in place",
        }
    return None


def scan(messages: List[dict]) -> List[Dict]:
    findings = []
    for msg in messages:
        finding = inspect(msg)
        if finding:
            findings.append(finding)
    return findings
