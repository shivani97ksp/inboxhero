# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""The mail store: the only place message text is read from.

Every citation a draft or a commitment makes is checked back against this
store, so a message id that was never read cannot be cited.
"""

import json
from typing import Dict, Iterable, List, Optional

import config

REQUIRED_FIELDS = ("id", "thread_id", "timestamp", "from", "to", "subject", "body")


class InboxFormatError(ValueError):
    """The inbox file is not shaped like an inbox.

    Carries every problem found, not just the first, so one run tells you
    everything that needs fixing.
    """

    def __init__(self, path, problems: List[str]):
        self.path = str(path)
        self.problems = problems
        super().__init__(f"{self.path}: " + "; ".join(problems))


def _validate(raw, path) -> List[dict]:
    """Check the file before anything reads a field off it.

    The inbox is untrusted input, so every assumption the rest of the code
    makes -- a list of objects, the seven fields present, all of them text,
    ids unique -- is checked here once and reported together.
    """
    if not isinstance(raw, list):
        raise InboxFormatError(path, [f"top level must be a list of messages, found {type(raw).__name__}"])
    if not raw:
        raise InboxFormatError(path, ["inbox is empty; nothing to process"])

    problems: List[str] = []
    seen: Dict[str, int] = {}
    for index, item in enumerate(raw):
        where = f"item {index}"
        if not isinstance(item, dict):
            problems.append(f"{where}: expected an object, found {type(item).__name__}")
            continue
        for field in REQUIRED_FIELDS:
            if field not in item:
                problems.append(f"{where}: missing '{field}'")
            elif not isinstance(item[field], str):
                problems.append(f"{where}: '{field}' must be text, found {type(item[field]).__name__}")
        msg_id = item.get("id")
        if isinstance(msg_id, str):
            if msg_id in seen:
                problems.append(f"{where}: duplicate id '{msg_id}' (also item {seen[msg_id]})")
            else:
                seen[msg_id] = index

    if problems:
        raise InboxFormatError(path, problems)
    return raw


class MailStore:
    def __init__(self, path=None):
        self.path = path or config.INBOX_PATH
        try:
            with open(self.path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            raise InboxFormatError(self.path, ["file not found"])
        except json.JSONDecodeError as exc:
            raise InboxFormatError(self.path, [f"not valid JSON: {exc}"])

        self.messages: List[dict] = _validate(raw, self.path)
        self.messages.sort(key=lambda m: m["timestamp"])
        self._by_id: Dict[str, dict] = {m["id"]: m for m in self.messages}
        self._read_ids: set = set()

    # ---------- basic access ----------

    def __len__(self) -> int:
        return len(self.messages)

    def all(self) -> List[dict]:
        return list(self.messages)

    def get(self, msg_id: str) -> Optional[dict]:
        msg = self._by_id.get(msg_id)
        if msg is not None:
            self._read_ids.add(msg_id)
        return msg

    def exists(self, msg_id: str) -> bool:
        return msg_id in self._by_id

    def thread(self, thread_id: str) -> List[dict]:
        msgs = [m for m in self.messages if m["thread_id"] == thread_id]
        self._read_ids.update(m["id"] for m in msgs)
        return msgs

    def earlier_in_thread(self, msg: dict) -> List[dict]:
        """Messages in the same thread that arrived before this one."""
        return [
            m
            for m in self.thread(msg["thread_id"])
            if m["timestamp"] < msg["timestamp"] and m["id"] != msg["id"]
        ]

    def sent_by_owner(self) -> List[dict]:
        return [m for m in self.messages if m["from"] == config.OWNER]

    def from_sender(self, address: str) -> List[dict]:
        address = address.lower()
        return [m for m in self.messages if m["from"].lower() == address]

    # ---------- retrieval helpers ----------

    def keyword_search(self, terms: Iterable[str], exclude_id: str = "") -> List[dict]:
        """Cheap cross-thread fallback when the thread itself has no answer."""
        terms = [t.lower() for t in terms if len(t) > 3]
        hits = []
        for m in self.messages:
            if m["id"] == exclude_id:
                continue
            haystack = (m["subject"] + " " + m["body"]).lower()
            score = sum(1 for t in terms if t in haystack)
            if score:
                hits.append((score, m))
        hits.sort(key=lambda pair: (-pair[0], pair[1]["timestamp"]))
        found = [m for _, m in hits[:5]]
        self._read_ids.update(m["id"] for m in found)
        return found

    # ---------- citation checking ----------

    def verify_cited(self, cited_ids: Iterable[str]) -> List[str]:
        """Return the subset of cited ids that are not real, read messages.

        An empty list means the citation is honest. Anything in it is a
        fabricated citation and the caller must throw the draft away.
        """
        bad = []
        for cid in cited_ids:
            if cid not in self._by_id or cid not in self._read_ids:
                bad.append(cid)
        return bad

    def quote(self, msg_id: str, limit: int = 240) -> str:
        msg = self.get(msg_id)
        if not msg:
            return ""
        body = " ".join(msg["body"].split())
        return body if len(body) <= limit else body[:limit] + "..."
