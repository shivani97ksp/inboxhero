# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""The approval gate: the only route to an irreversible action.

Two controls, and the default run uses both. Every irreversible proposal is
first rendered as a dry run -- the exact bytes that would leave, written under
outbox/_dryrun/ -- and then it waits for a human. With no approval supplied it
stays blocked, so the safe outcome is the one you get by doing nothing.

Approval is explicit and per proposal: `--approve m008` approves one, and
`--interactive` asks at the terminal. There is no flag, and no preference,
that turns the gate off; prefs.py refuses to learn one. That matters because
m039 asks for exactly that.

Every proposal, the human's answer and the outcome are appended to
state/gate_log.jsonl, so an action can always be traced back to whoever
allowed it.
"""

import json
from typing import Dict, List, Optional, Sequence

import actions
import config
import trace


class Gate:
    def __init__(self, mode: str = "both", approve: Optional[Sequence[str]] = None, interactive: bool = False):
        self.mode = mode                      # dry-run | approve | both
        self.approved = set(approve or ())    # message ids (or "all") pre-approved on the CLI
        self.interactive = interactive
        self.decisions: List[Dict] = []

    # ---------- logging ----------

    def _log(self, record: Dict) -> None:
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.GATE_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.decisions.append(record)
        trace.emit(
            "gate",
            cap=record.get("cap", "-"),
            msg_id=record.get("msg_id"),
            action=record["action"],
            approved_by=record["approved_by"],
            outcome=record["outcome"],
        )

    # ---------- the ask ----------

    def _ask_human(self, action: str, proposal: Dict) -> str:
        """Returns the approver identity, or '' for refusal."""
        msg_id = proposal.get("msg_id", "-")
        if "all" in self.approved or msg_id in self.approved:
            return f"cli:--approve {msg_id}"
        if self.interactive:
            print(f"\n  PROPOSED {action.upper()} for {msg_id}")
            print(f"  to: {proposal.get('to')}")
            print(f"  subject: {proposal.get('subject')}")
            body = (proposal.get("body") or "").strip().splitlines()
            for line in body[:8]:
                print("  | " + line)
            answer = input("  approve? [y/N] ").strip().lower()
            return "terminal:operator" if answer in ("y", "yes") else ""
        return ""

    def propose(self, action: str, proposal: Dict, cap: str = "-") -> Dict:
        """Put an action through the gate. Returns the outcome record."""
        msg_id = proposal.get("msg_id", "-")
        reversible = action in config.REVERSIBLE_ACTIONS
        record = {
            "ts": trace.now(),
            "cap": cap,
            "msg_id": msg_id,
            "action": action,
            "reversible": reversible,
            "proposal": {k: v for k, v in proposal.items() if k != "body"},
            "preview": (proposal.get("body") or "")[:400],
            "approved_by": "not-required" if reversible else "",
            "outcome": "",
            "artifact": "",
        }

        if reversible:
            record["outcome"] = "executed (reversible)"
            if action == "draft":
                record["artifact"] = actions.save_draft(
                    msg_id, proposal["to"], proposal["subject"], proposal["body"],
                    proposal.get("cc"), cap,
                )
            elif action in ("label", "flag", "archive", "defer"):
                actions.label(msg_id, proposal.get("tag", action), cap)
            self._log(record)
            return record

        if self.mode in ("dry-run", "both"):
            record["artifact"] = actions.dry_run_preview(
                msg_id, proposal.get("to", ""), proposal.get("subject", ""),
                proposal.get("body", ""), proposal.get("cc"), cap, action,
            )
            record["dry_run"] = True

        if self.mode == "dry-run":
            record["approved_by"] = "n/a (dry-run only)"
            record["outcome"] = "not executed; dry run written for review"
            self._log(record)
            return record

        approver = self._ask_human(action, proposal)
        if not approver:
            record["approved_by"] = "none"
            record["outcome"] = "blocked; awaiting human approval"
            self._log(record)
            return record

        record["approved_by"] = approver
        if action == "send":
            record["artifact"] = actions.send_now(
                msg_id, proposal["to"], proposal["subject"], proposal["body"],
                proposal.get("cc"), cap,
            )
        elif action == "delete":
            record["artifact"] = actions.delete_now(msg_id, cap)
        record["outcome"] = "executed after approval"
        self._log(record)
        return record


def read_log() -> List[Dict]:
    if not config.GATE_LOG_PATH.exists():
        return []
    return [json.loads(l) for l in config.GATE_LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
