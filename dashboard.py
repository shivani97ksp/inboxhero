# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""Three panes, no more: pending actions, flagged, commitments.

The panes exist to answer three different questions -- what is waiting on me,
what tried something on me, and what have I promised -- and anything that does
not answer one of those is deliberately left out. Both a JSON and an HTML file
are written: the JSON so the panes can be diffed and graded, the HTML so it can
be opened and screenshotted.
"""

import html
import json
from typing import Dict, List

import commitments as commitments_mod
import config
import gate as gate_mod
import prefs
import trace


def build(summary: Dict, messages: List[dict], drafts: List[Dict]) -> Dict:
    by_id = {m["id"]: m for m in messages}
    draft_index = {d["msg_id"]: d for d in drafts}

    pending = []
    for decision in summary["decisions"]:
        if decision["disposition"] in ("reply", "defer", "delegate", "escalate") and not decision.get("flagged"):
            draft = draft_index.get(decision["id"])
            pending.append({
                "message_id": decision["id"],
                "from": decision["from"],
                "subject": decision["subject"],
                "action": decision["disposition"],
                "why": decision["reason"],
                "draft_ready": bool(draft and draft.get("grounded")),
                "waiting_on": "owner approval" if decision.get("needs_human") else "owner",
            })

    flagged = []
    for finding in summary["findings"]:
        flagged.append({
            "message_id": finding["message_id"],
            "from": finding["from"],
            "subject": by_id[finding["message_id"]]["subject"],
            "kind": finding["kind"],
            "signals": finding["signals"],
            "what_was_asked": finding["asked_for"],
            "outcome": "refused; message left in the inbox and reported here",
        })
    for refusal in prefs.load().get("refused", []):
        flagged.append({
            "message_id": refusal["message_id"],
            "from": refusal["from"],
            "subject": by_id.get(refusal["message_id"], {}).get("subject", ""),
            "kind": "preference-tampering",
            "signals": ["asks to be stored as a standing instruction"],
            "what_was_asked": refusal["reason"],
            "outcome": "not stored; preferences of this kind are never learnable from mail",
        })
    seen = set()
    flagged = [f for f in flagged if not (f["message_id"] in seen or seen.add(f["message_id"]))]

    items = commitments_mod.extract(messages)
    clashes = commitments_mod.conflicts(items, messages)
    conflicting_ids = {s for c in clashes for s in c["sources"]}

    panes = {
        "generated": trace.now(),
        "model": summary["model"],
        "pane_1_pending_actions": pending,
        "pane_2_flagged": flagged,
        "pane_3_commitments": {
            "conflicts": clashes,
            "items": [dict(i, in_conflict=any(s in conflicting_ids for s in i["sources"])) for i in items],
        },
        "counts": {
            "messages": summary["messages_processed"],
            "rule_handled": summary["rule_handled"],
            "no_model_needed": summary["no_model_needed"],
            "dispositions": summary["counts"],
            "pending": len(pending),
            "flagged": len(flagged),
            "commitments": len(items),
            "conflicts": len(clashes),
            "gate_decisions": len(gate_mod.read_log()),
        },
    }

    config.DASHBOARD_JSON.write_text(json.dumps(panes, indent=2), encoding="utf-8")
    config.DASHBOARD_HTML.write_text(_render_html(panes), encoding="utf-8")
    trace.emit("dashboard", cap="R6", panes=3, pending=len(pending), flagged=len(flagged), commitments=len(items))
    return panes


def _esc(value) -> str:
    return html.escape(str(value))


def _render_html(panes: Dict) -> str:
    rows = []
    for item in panes["pane_1_pending_actions"]:
        rows.append(
            f"<tr><td>{_esc(item['message_id'])}</td><td>{_esc(item['from'])}</td>"
            f"<td>{_esc(item['subject'])}</td><td><b>{_esc(item['action'])}</b></td>"
            f"<td>{_esc(item['why'])}</td><td>{'yes' if item['draft_ready'] else '-'}</td></tr>"
        )
    pending_rows = "\n".join(rows)

    rows = []
    for item in panes["pane_2_flagged"]:
        rows.append(
            f"<tr><td>{_esc(item['message_id'])}</td><td>{_esc(item['from'])}</td>"
            f"<td>{_esc(item['kind'])}</td><td>{_esc(item['what_was_asked'])}</td>"
            f"<td>{_esc(', '.join(item['signals']))}</td><td>{_esc(item['outcome'])}</td></tr>"
        )
    flagged_rows = "\n".join(rows)

    rows = []
    for clash in panes["pane_3_commitments"]["conflicts"]:
        rows.append(
            f"<tr class='clash'><td>CONFLICT</td><td>{_esc(clash['slot'])}</td>"
            f"<td>{_esc(clash['detail'])}</td><td>{_esc(', '.join(clash['sources']))}</td>"
            f"<td>{_esc(clash['resolution_needed'])}</td></tr>"
        )
    for item in panes["pane_3_commitments"]["items"]:
        note = item["note"] or ("in conflict -- see above" if item["in_conflict"] else "")
        rows.append(
            f"<tr><td>{_esc(item['date'])}</td><td>{_esc(item['time'] or '-')}</td>"
            f"<td>{_esc(item['what'])}</td><td>{_esc(', '.join(item['sources']))}</td>"
            f"<td>{_esc(note)}</td></tr>"
        )
    commitment_rows = "\n".join(rows)

    counts = panes["counts"]
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>inboxHero dashboard</title>
<style>
 body {{ font: 14px/1.45 -apple-system, Segoe UI, Roboto, sans-serif; margin: 28px; color: #16181d; }}
 h1 {{ font-size: 20px; margin-bottom: 2px; }}
 .meta {{ color: #666; font-size: 12px; margin-bottom: 22px; }}
 h2 {{ font-size: 15px; margin: 26px 0 8px; border-bottom: 2px solid #16181d; padding-bottom: 4px; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #e6e8ec; vertical-align: top; }}
 th {{ background: #f6f7f9; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
 tr.clash td {{ background: #fff4f4; font-weight: 600; }}
 code {{ background: #f2f3f5; padding: 1px 4px; }}
</style></head><body>
<h1>inboxHero &mdash; sam@paperjet.io</h1>
<div class="meta">generated {_esc(panes['generated'])} &middot; model {_esc(panes['model'])} &middot;
 {counts['messages']} messages &middot; {counts['no_model_needed']} handled without a model call &middot;
 {counts['gate_decisions']} gate decisions logged</div>

<h2>1. Pending actions &mdash; waiting on Sam ({len(panes['pane_1_pending_actions'])})</h2>
<table><tr><th>id</th><th>from</th><th>subject</th><th>action</th><th>why</th><th>draft</th></tr>
{pending_rows}</table>

<h2>2. Flagged &mdash; refused and reported ({len(panes['pane_2_flagged'])})</h2>
<table><tr><th>id</th><th>from</th><th>kind</th><th>what it asked for</th><th>signals</th><th>outcome</th></tr>
{flagged_rows}</table>

<h2>3. Commitments &mdash; with sources ({len(panes['pane_3_commitments']['items'])},
 {len(panes['pane_3_commitments']['conflicts'])} conflicts)</h2>
<table><tr><th>date</th><th>time</th><th>what</th><th>sources</th><th>note</th></tr>
{commitment_rows}</table>
</body></html>
"""
