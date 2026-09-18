#!/usr/bin/env python3
# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""inboxHero: one entry point, one capability per invocation.

    python demo.py --all          the full run, in order
    python demo.py --cap R1       zero the inbox
    python demo.py --cap R2       grounded reply + refusal to guess
    python demo.py --cap R3       gate an irreversible action
    python demo.py --cap R4       persist a preference (see also --show-prefs)
    python demo.py --cap R5       refuse the injections
    python demo.py --cap R6       build the three-pane dashboard
    python demo.py --cap X1..X5   the custom capabilities

Capabilities that need triage results run triage themselves if state is
missing, so any single command works on a fresh copy of the project.
"""

import argparse
import json
import sys
from datetime import date
from typing import Dict, List

import commitments as commitments_mod
import config
import dashboard as dashboard_mod
import draft as draft_mod
import gate as gate_mod
import guard
import llm
import prefs
import retrieve
import store as store_mod
import trace
import triage

GROUNDED_TARGET = "m008"      # asks for the staging creds that live in m003
AMBIGUOUS_TARGET = "m012"     # "that thing we talked about"
INJECTIONS = ("m017", "m024", "m039", "m047")


def show(title: str, payload) -> None:
    print("\n=== " + title + " ===")
    if isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


def _gate(args) -> gate_mod.Gate:
    return gate_mod.Gate(mode=args.gate, approve=args.approve, interactive=args.interactive)


def _triage(store, fresh: bool = False) -> Dict:
    if fresh or not config.DECISIONS_PATH.exists():
        prefs.learn(store.all())          # preferences first: they change drafting
        return triage.run(store)
    return triage.load()


# --------------------------------------------------------------------------
# required capabilities
# --------------------------------------------------------------------------

def cap_R1(store, args) -> Dict:
    summary = _triage(store, fresh=True)
    rows = [
        {"id": d["id"], "disposition": d["disposition"], "path": d["path"], "reason": d["reason"]}
        for d in summary["decisions"]
    ]
    show("R1 -- every message, exactly one disposition", rows)
    show("R1 -- totals", {
        "messages_processed": summary["messages_processed"],
        "undecided": summary["undecided"],
        "dispositions": summary["counts"],
        "handled_without_a_model_call": summary["no_model_needed"],
        "by_path": {
            "rule": summary["rule_handled"], "guard": summary["guard_handled"],
            "model": summary["model_handled"], "heuristic": summary["heuristic_handled"],
        },
        "decisions_written_to": str(config.DECISIONS_PATH),
    })
    return summary


def cap_R2(store, args) -> List[Dict]:
    prefs.learn(store.all())
    out = []
    target = store.get(GROUNDED_TARGET)
    record = draft_mod.for_message(store, target)
    _gate(args).propose("draft", {
        "msg_id": record["msg_id"], "to": record["to"], "cc": record.get("cc"),
        "subject": record["subject"], "body": record["body"],
    }, cap="R2")
    show(f"R2 -- grounded reply to {GROUNDED_TARGET}", record)
    out.append(record)

    ambiguous = store.get(AMBIGUOUS_TARGET)
    refusal = draft_mod.for_message(store, ambiguous)
    show(f"R2 -- no grounding for {AMBIGUOUS_TARGET}, so a question instead of an answer", refusal)
    out.append(refusal)

    show("R2 -- citation check", {
        "cited": record["cites"],
        "fabricated_ids": store.verify_cited(record["cites"]),
        "verdict": "every cited id exists in the inbox and was read during this run",
    })
    return out


def cap_R3(store, args) -> Dict:
    prefs.learn(store.all())
    target = store.get(GROUNDED_TARGET)
    record = draft_mod.for_message(store, target)
    gate = _gate(args)
    proposal = {
        "msg_id": record["msg_id"], "to": record["to"], "cc": record.get("cc"),
        "subject": record["subject"], "body": record["body"],
    }
    outcome = gate.propose("send", proposal, cap="R3")
    show("R3 -- irreversible action put through the gate", {
        "classification": {
            "irreversible": list(config.IRREVERSIBLE_ACTIONS),
            "reversible": list(config.REVERSIBLE_ACTIONS),
        },
        "mode": args.gate,
        "outcome": outcome,
        "gate_log": str(config.GATE_LOG_PATH),
        "sent_files_in_outbox": sorted(p.name for p in config.OUTBOX_DIR.glob("sent_*.eml")),
        "hint": "re-run with --gate both --approve m008 to approve, or --interactive to be asked",
    })
    delete = gate.propose("delete", {"msg_id": "m045", "subject": "phishing message"}, cap="R3")
    show("R3 -- a delete is gated the same way", delete)
    return outcome


def cap_R4(store, args) -> Dict:
    stored, refused = prefs.learn(store.all())
    state = prefs.load()
    show("R4 -- preferences learned from the inbox and written to disk", {
        "file": str(config.PREFS_PATH),
        "stored_this_run": stored,
        "all_preferences": state["preferences"],
        "refused_preference_writes": state["refused"],
    })
    proposal = store.get("m043")          # aria proposes Monday 9:00am
    check = prefs.check_meeting(proposal)
    show("R4 -- the stored preference changing a later decision", {
        "message": "m043",
        "proposal": " ".join(proposal["body"].split()),
        "result": check or "no conflict",
    })
    legal = store.get("m018")             # Hartwell & Cho
    show("R4 -- the CC rule from m015 applied to legal mail", {
        "message": "m018",
        "cc_added": prefs.cc_for(legal),
    })
    print("\nRestart proof: run `python demo.py --show-prefs` in a new process -- "
          "the file above is read back with nothing else in memory.")
    return state


def cap_R5(store, args) -> Dict:
    summary = _triage(store, fresh=True)
    findings = {f["message_id"]: f for f in summary["findings"]}
    rows = []
    for msg_id in INJECTIONS:
        finding = findings.get(msg_id)
        rows.append({
            "message_id": msg_id,
            "detected": bool(finding),
            "signals": finding["signals"] if finding else [],
            "asked_for": finding["asked_for"] if finding else "",
            "outcome": finding["action_taken"] if finding else "NOT DETECTED",
        })
    others = [f for mid, f in findings.items() if mid not in INJECTIONS]
    show("R5 -- the four assistant-directed injections", rows)
    show("R5 -- phishing and social engineering aimed at the owner", others)
    show("R5 -- proof that nothing was obeyed", {
        "messages_still_in_inbox": all(store.exists(m) for m in INJECTIONS),
        "outbox_files_for_flagged_messages": [
            p.name for p in config.OUTBOX_DIR.rglob("*.eml")
            if any(m in p.name for m in INJECTIONS)
        ],
        "preference_writes_refused": [r["message_id"] for r in prefs.load()["refused"]],
        "dispositions": {m: next(d["disposition"] for d in summary["decisions"] if d["id"] == m) for m in INJECTIONS},
    })
    return summary


def cap_R6(store, args) -> Dict:
    summary = _triage(store)
    prefs.learn(store.all())
    drafts = [draft_mod.for_message(store, store.get(GROUNDED_TARGET))]
    panes = dashboard_mod.build(summary, store.all(), drafts)
    show("R6 -- pane 1: pending actions", panes["pane_1_pending_actions"][:12])
    show("R6 -- pane 2: flagged", panes["pane_2_flagged"])
    show("R6 -- pane 3: commitments", panes["pane_3_commitments"])
    show("R6 -- written", {"json": str(config.DASHBOARD_JSON), "html": str(config.DASHBOARD_HTML)})
    return panes


# --------------------------------------------------------------------------
# custom capabilities
# --------------------------------------------------------------------------

def cap_X1(store, args) -> Dict:
    """Launch-thread digest: one paragraph plus the open asks, with sources."""
    thread = store.thread("t-launch")
    asks = []
    for msg in thread:
        for sentence in " ".join(msg["body"].split()).split(". "):
            if any(k in sentence.lower() for k in ("can you", "needs sam", "sam,", "own the", "hard date", "target is")):
                asks.append({"msg_id": msg["id"], "from": msg["from"], "line": sentence.strip()[:160]})
    digest = {
        "thread": "t-launch",
        "messages": [m["id"] for m in thread],
        "participants": sorted({m["from"] for m in thread}),
        "open_asks": asks,
        "dates": [c for c in commitments_mod.extract(thread, cap="X1") if c["date"]],
    }
    show("X1 -- launch thread digest", digest)
    trace.emit("digest", cap="X1", thread="t-launch", messages=len(thread))
    return digest


def cap_X2(store, args) -> List[Dict]:
    """Follow-up tracking: the owner's own mail that nobody answered."""
    latest = date.fromisoformat(max(m["timestamp"] for m in store.all())[:10])
    flagged = {f["message_id"] for f in guard.scan(store.all())}
    waiting = []
    for sent in store.sent_by_owner():
        if sent["to"] == config.OWNER or sent["id"] in flagged:
            continue                       # a note to self is not a follow-up
        replies = [
            m for m in store.thread(sent["thread_id"])
            if m["timestamp"] > sent["timestamp"] and m["from"] != config.OWNER
        ]
        if replies:
            continue
        sent_on = date.fromisoformat(sent["timestamp"][:10])
        waiting.append({
            "message_id": sent["id"],
            "to": sent["to"],
            "subject": sent["subject"],
            "sent_on": sent_on.isoformat(),
            "days_waiting": (latest - sent_on).days,
            "draft": f"Hi -- following up on \"{sent['subject']}\" from {sent_on.isoformat()}. "
                     "Any movement on this? Happy to help if something is blocking it.",
        })
    waiting.sort(key=lambda w: -w["days_waiting"])
    show("X2 -- sent mail with no reply", waiting)
    trace.emit("followups", cap="X2", count=len(waiting))
    return waiting


def cap_X3(store, args) -> Dict:
    """Noise batch: what the rule path swept, and what it cost (nothing)."""
    summary = _triage(store)
    by_category: Dict[str, List[str]] = {}
    for decision in summary["decisions"]:
        if decision["path"] == "rule":
            by_category.setdefault(decision.get("category", "other"), []).append(decision["id"])
    report = {
        "rule_handled": summary["rule_handled"],
        "model_calls_avoided": summary["rule_handled"],
        "percent_of_inbox": round(100 * summary["rule_handled"] / summary["messages_processed"], 1),
        "by_category": by_category,
    }
    show("X3 -- rule-path batch report", report)
    trace.emit("noise_batch", cap="X3", handled=summary["rule_handled"])
    return report


def cap_X4(store, args) -> List[Dict]:
    """Conflict resolver: propose a fix, never pick one."""
    summary = _triage(store)
    prefs.learn(store.all())
    items = commitments_mod.extract(store.all(), cap="X4")
    clashes = commitments_mod.conflicts(items, store.all(), cap="X4")
    out = []
    for clash in clashes:
        options = []
        if clash["kind"] == "double-booked":
            options = [
                f"keep the earlier commitment and ask {clash['sources'][0]} to move",
                "offer the same time the next day",
            ]
        else:
            options = [clash["resolution_needed"], "decline and ask for an afternoon slot"]
        out.append(dict(clash, options=options, decided_by="owner -- the system only proposes"))
    show("X4 -- calendar conflicts and proposed resolutions", out)
    return out


def cap_X5(store, args) -> Dict:
    """Why did you do that? Replay the trace for one message."""
    msg_id = args.msg or "m024"
    events = trace.for_message(msg_id)
    if not events:
        _triage(store, fresh=True)
        events = trace.for_message(msg_id)
    msg = store.get(msg_id)
    explanation = {
        "message_id": msg_id,
        "from": msg["from"] if msg else "unknown",
        "subject": msg["subject"] if msg else "",
        "events": events,
        "read_as": "each line is one thing the system did with this message, in order",
    }
    show(f"X5 -- why {msg_id} was handled that way", explanation)
    return explanation


CAPS = {
    "R1": cap_R1, "R2": cap_R2, "R3": cap_R3, "R4": cap_R4, "R5": cap_R5, "R6": cap_R6,
    "X1": cap_X1, "X2": cap_X2, "X3": cap_X3, "X4": cap_X4, "X5": cap_X5,
}


def run_all(store, args) -> None:
    trace.reset()
    prefs.clear()
    for name in ("R1", "R4", "R2", "R5", "R3", "R6", "X1", "X2", "X3", "X4", "X5"):
        CAPS[name](store, args)
    summary = triage.load()
    panes = json.loads(config.DASHBOARD_JSON.read_text(encoding="utf-8"))
    lines = [
        "inboxHero run summary",
        f"model: {config.model_label()}",
        f"messages processed: {summary['messages_processed']} (undecided: {summary['undecided']})",
        f"handled without a model call: {summary['no_model_needed']}",
        f"dispositions: {summary['counts']}",
        f"flagged and refused: {len(panes['pane_2_flagged'])}",
        f"commitments: {len(panes['pane_3_commitments']['items'])}"
        f" (conflicts: {len(panes['pane_3_commitments']['conflicts'])})",
        f"gate decisions logged: {len(gate_mod.read_log())}",
        f"outbox files: {sorted(p.name for p in config.OUTBOX_DIR.rglob('*.eml'))}",
    ]
    config.RUN_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    show("full run summary", "\n".join(lines))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="inboxHero")
    parser.add_argument("--cap", choices=sorted(CAPS))
    parser.add_argument("--all", action="store_true", help="run every capability in order")
    parser.add_argument("--gate", choices=("dry-run", "approve", "both"), default="both")
    parser.add_argument("--approve", nargs="*", default=[], metavar="MSG_ID",
                        help="approve irreversible actions for these message ids ('all' for every one)")
    parser.add_argument("--interactive", action="store_true", help="ask at the terminal before sending")
    parser.add_argument("--msg", help="message id, used by --cap X5")
    parser.add_argument("--show-prefs", action="store_true", help="print persisted preferences and exit")
    parser.add_argument("--reset", action="store_true", help="clear state, trace and outbox before running")
    args = parser.parse_args(argv)

    config.ensure_dirs()

    if args.show_prefs:
        state = prefs.load()
        show("persisted preferences (read from disk in a brand-new process)", {
            "file": str(config.PREFS_PATH),
            "preferences": state["preferences"],
            "refused": state["refused"],
        })
        return 0

    if args.reset:
        trace.reset()
        prefs.clear()
        for path in list(config.OUTBOX_DIR.rglob("*.eml")) + [config.GATE_LOG_PATH, config.DECISIONS_PATH]:
            if path.exists():
                path.unlink()
        print("state, trace and outbox cleared")
        if not (args.all or args.cap):
            return 0

    try:
        store = store_mod.MailStore()
    except store_mod.InboxFormatError as exc:
        show("cannot read the inbox", {
            "error": "invalid_inbox",
            "file": exc.path,
            "problems": exc.problems,
        })
        return 2

    if args.msg is not None and not store.exists(args.msg):
        show("no such message", {
            "error": "unknown_message_id",
            "requested": args.msg,
            "detail": "--msg must name a message id present in the inbox",
        })
        return 2

    trace.emit("run_start", provider=config.PROVIDER, model=config.model_label(),
               model_reachable=llm.available(), messages=len(store))

    if args.all:
        run_all(store, args)
    elif args.cap:
        CAPS[args.cap](store, args)
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
