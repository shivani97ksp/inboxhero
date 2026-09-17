# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""Zeroing the inbox: exactly one disposition, with a reason, for every message.

Three paths, in this order, and the order is the design:

  1. guard  -- hostile mail is decided before anything reads it for content,
               so an injection cannot influence its own triage.
  2. rules  -- receipts, newsletters and platform noise. Deterministic, free,
               and the reason is auditable. This is the majority of the inbox.
  3. model  -- only what is left, in batches.

Whatever happens, every message ends the run with a disposition: if the model
is unreachable the heuristic in llm.py answers instead, so "undecided" is not
a state this system can end in.
"""

import json
from typing import Dict, List

import config
import guard
import llm
import rules
import trace


def run(store, cap: str = "R1") -> Dict:
    messages = store.all()

    findings = guard.scan(messages)
    by_id = {f["message_id"]: f for f in findings}
    for finding in findings:
        trace.emit(
            "flagged", cap="R5", msg_id=finding["message_id"],
            kind=finding["kind"], signals=finding["signals"],
        )

    decisions: List[Dict] = []
    needs_model: List[dict] = []

    for msg in messages:
        store.get(msg["id"])  # record that the run actually read it
        finding = by_id.get(msg["id"])
        if finding:
            decisions.append({
                "id": msg["id"],
                "thread_id": msg["thread_id"],
                "from": msg["from"],
                "subject": msg["subject"],
                "disposition": "escalate",
                "reason": finding["reason"],
                "path": "guard",
                "flagged": finding["kind"],
                "needs_human": True,
            })
            continue

        decided = rules.apply(msg)
        if decided:
            decisions.append({
                "id": msg["id"],
                "thread_id": msg["thread_id"],
                "from": msg["from"],
                "subject": msg["subject"],
                "disposition": decided["disposition"],
                "reason": decided["reason"],
                "path": "rule",
                "category": decided["category"],
                "needs_human": False,
            })
        else:
            needs_model.append(msg)

    classified = llm.classify(needs_model, cap=cap)
    for msg in needs_model:
        result = classified[msg["id"]]
        decisions.append({
            "id": msg["id"],
            "thread_id": msg["thread_id"],
            "from": msg["from"],
            "subject": msg["subject"],
            "disposition": result["disposition"],
            "reason": result["reason"],
            "path": result["path"],
            "ambiguous": result.get("ambiguous", False),
            "needs_human": result.get("needs_human", False),
        })

    order = {m["id"]: i for i, m in enumerate(messages)}
    decisions.sort(key=lambda d: order[d["id"]])

    for decision in decisions:
        trace.emit(
            "disposition", cap=cap, msg_id=decision["id"],
            disposition=decision["disposition"], path=decision["path"],
            reason=decision["reason"],
        )

    counts: Dict[str, int] = {d: 0 for d in config.DISPOSITIONS}
    for decision in decisions:
        counts[decision["disposition"]] += 1

    summary = {
        "model": config.model_label(),
        "messages_processed": len(messages),
        "rule_handled": sum(1 for d in decisions if d["path"] == "rule"),
        "guard_handled": sum(1 for d in decisions if d["path"] == "guard"),
        "model_handled": sum(1 for d in decisions if d["path"] == "model"),
        "heuristic_handled": sum(1 for d in decisions if d["path"] == "heuristic"),
        "undecided": sum(1 for d in decisions if d["disposition"] not in config.DISPOSITIONS),
        "counts": counts,
        "decisions": decisions,
        "findings": findings,
    }
    summary["no_model_needed"] = summary["rule_handled"] + summary["guard_handled"]

    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    config.DECISIONS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def load() -> Dict:
    if not config.DECISIONS_PATH.exists():
        raise SystemExit("No decisions yet -- run `python demo.py --cap R1` (or --all) first.")
    return json.loads(config.DECISIONS_PATH.read_text(encoding="utf-8"))
