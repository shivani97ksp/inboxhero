# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""Grounded drafting.

A draft is only produced when the facts behind it were retrieved from real
messages, and every fact keeps the id of the message it came from. Before the
draft is returned the citations are checked back against the store: an id that
does not exist, or that the run never actually read, voids the draft rather
than being quietly dropped.

When retrieval finds nothing, the answer is a refusal with a clarifying
question -- m012 ("that thing we talked about") gets a question, not a guess.
"""

from typing import Dict, List, Optional

import config
import llm
import prefs
import retrieve
import trace


def _subject(msg: dict) -> str:
    subject = msg["subject"]
    return subject if subject.lower().startswith("re:") else "Re: " + subject


def clarify(msg: dict, cap: str = "R2") -> Dict:
    """No grounding exists: ask, do not invent."""
    question = (
        "Happy to pick this up -- could you tell me which item you mean and what "
        "you need from me? I could not find it in our earlier messages."
    )
    record = {
        "msg_id": msg["id"],
        "to": msg["from"],
        "subject": _subject(msg),
        "body": f"Hi,\n\n{question}\n\nSam",
        "cites": [],
        "strategy": "none",
        "grounded": False,
        "reason": "nothing in the inbox identifies the request; asking instead of drafting an answer",
    }
    trace.emit("draft_refused", cap=cap, msg_id=msg["id"], reason=record["reason"])
    return record


def for_message(store, msg: dict, cap: str = "R2") -> Dict:
    """Draft a grounded reply to one message, or refuse."""
    context = retrieve.context_for(store, msg)
    trace.emit(
        "retrieval", cap=cap, msg_id=msg["id"], strategy=context["strategy"],
        read=context["read"], facts=len(context["facts"]),
    )
    if not context["facts"]:
        return clarify(msg, cap)

    facts: List[str] = [f"{f['text']} (from {f['msg_id']})" for f in context["facts"][:6]]
    cites = sorted({f["msg_id"] for f in context["facts"][:6]})

    fabricated = store.verify_cited(cites)
    if fabricated:
        trace.emit("citation_rejected", cap=cap, msg_id=msg["id"], bad_ids=fabricated)
        return clarify(msg, cap)

    body: Optional[str] = llm.compose(
        f"{msg['from']} asks: {' '.join(msg['body'].split())}", facts, cap
    )
    if not body:
        return clarify(msg, cap)

    cc = [rule["cc"] for rule in prefs.cc_for(msg)]
    schedule = prefs.check_meeting(msg)
    if schedule:
        body += (
            f"\n\nOne scheduling note: {schedule['proposed']} is earlier than I take meetings "
            f"({schedule['earliest']} at the earliest, per {schedule['violates']}). "
            f"Can we make it {schedule['counter_offer']} or later?"
        )

    record = {
        "msg_id": msg["id"],
        "to": msg["from"],
        "cc": cc,
        "subject": _subject(msg),
        "body": body,
        "cites": cites,
        "strategy": context["strategy"],
        "grounded": True,
        "reason": f"answered from {', '.join(cites)} via {context['strategy']}",
    }
    trace.emit(
        "draft", cap=cap, msg_id=msg["id"], cites=cites, strategy=context["strategy"],
        cc=cc, model=config.model_label(),
    )
    return record
