# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""Effects on the world.

There is no real mail server. "Sending" writes an .eml-style file into
outbox/, which is the whole extent of this system's reach -- a deliberate
design choice, because it means a bug or a successful injection can at worst
create a file on the owner's own disk.

Reversible effects (draft, label, flag, archive, defer) are applied directly.
Irreversible ones (send, delete) are only reachable through gate.py, which is
why send_now() and delete_now() are named the way they are and are never
called from anywhere else.
"""

import json
import re
from typing import Dict, List, Optional

import config
import trace


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "message"


def render(to: str, subject: str, body: str, cc: Optional[List[str]] = None, in_reply_to: str = "") -> str:
    lines = [f"To: {to}"]
    if cc:
        lines.append("Cc: " + ", ".join(cc))
    lines.append(f"From: {config.OWNER}")
    lines.append(f"Subject: {subject}")
    if in_reply_to:
        lines.append(f"In-Reply-To: {in_reply_to}")
    lines.append("")
    lines.append(body)
    return "\n".join(lines) + "\n"


# ---------------- reversible ----------------

def save_draft(msg_id: str, to: str, subject: str, body: str, cc=None, cap: str = "-") -> str:
    config.OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = config.OUTBOX_DIR / f"draft_{msg_id}_{_slug(subject)}.eml"
    path.write_text(render(to, subject, body, cc, msg_id), encoding="utf-8")
    trace.emit("action", cap=cap, msg_id=msg_id, action="draft", reversible=True, artifact=str(path.name))
    return str(path)


def label(msg_id: str, tag: str, cap: str = "-") -> None:
    trace.emit("action", cap=cap, msg_id=msg_id, action="label", reversible=True, tag=tag)


# ---------------- irreversible: only gate.py may call these ----------------

def send_now(msg_id: str, to: str, subject: str, body: str, cc=None, cap: str = "-") -> str:
    config.OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = config.OUTBOX_DIR / f"sent_{msg_id}_{_slug(subject)}.eml"
    path.write_text(render(to, subject, body, cc, msg_id), encoding="utf-8")
    trace.emit("action", cap=cap, msg_id=msg_id, action="send", reversible=False, artifact=str(path.name))
    return str(path)


def delete_now(msg_id: str, cap: str = "-") -> str:
    """Records a tombstone. The inbox file itself is never rewritten, so even
    an approved delete cannot destroy evidence."""
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.STATE_DIR / "deleted.json"
    existing: Dict[str, str] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    existing[msg_id] = "tombstoned; inbox.json is never modified"
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    trace.emit("action", cap=cap, msg_id=msg_id, action="delete", reversible=False, artifact="state/deleted.json")
    return str(path)


def dry_run_preview(msg_id: str, to: str, subject: str, body: str, cc=None, cap: str = "-",
                    action: str = "send") -> str:
    """Writes what the action would have done, and nothing else."""
    directory = config.OUTBOX_DIR / "_dryrun"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"would_{action}_{msg_id}_{_slug(subject)}.eml"
    if action == "send":
        path.write_text(render(to, subject, body, cc, msg_id), encoding="utf-8")
    else:
        path.write_text(
            f"would {action} {msg_id} (\"{subject}\")\n"
            "no change written; inbox.json is never modified\n",
            encoding="utf-8")
    trace.emit("action", cap=cap, msg_id=msg_id, action=f"dry_run_{action}", reversible=True,
               artifact=str(path.name))
    return str(path)
