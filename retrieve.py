# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""Retrieval: thread-walk first, keyword search second.

A thread walk is preferred because in real mail the answer to "can you resend
that?" is almost always a few messages up the same thread, and walking it is
exact, free and explainable -- every fact carries the id of the message it
came from, which is what lets draft.py refuse to cite anything it did not
read. Keyword search across the whole inbox is the fallback for the cases
where the sender opened a new thread.

Nothing here is embedding-based. With 100 messages an index would add a
dependency and a failure mode without finding anything the two cheap
strategies miss.
"""

import re
from typing import Dict, List

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "you", "your", "yours", "can",
    "could", "would", "please", "again", "that", "this", "those", "these",
    "for", "from", "with", "was", "were", "have", "has", "had", "hi", "hey",
    "thanks", "thank", "just", "not", "get", "got", "need", "needs", "want",
    "send", "resend", "give", "know", "one", "our", "out", "its", "it's",
    "are", "any", "all", "what", "when", "which", "where", "who", "how",
    "about", "again", "back", "over", "into", "same", "still", "will",
}

# A sentence is only worth quoting if it carries something concrete.
CONCRETE = re.compile(r"(https?://|amqps?://|[\w.-]+@[\w.-]+|\d{1,2}:\d{2}|\d{1,2}(st|nd|rd|th)\b|\$\d|\d{3,})", re.I)


def keywords(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9][a-z0-9'./:-]{2,}", text.lower())
    return [w for w in words if w not in STOPWORDS]


def _sentences(body: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", body)
    return [p.strip() for p in parts if p.strip()]


def _facts_from(msg: dict, terms: List[str], min_hits: int) -> List[Dict]:
    """Sentences worth quoting. A sentence must carry something concrete and
    must overlap the request; `min_hits` is raised for cross-thread hits,
    where a single shared word means very little."""
    strong = {t for t in terms if len(t) >= 5}
    out = []
    for sentence in _sentences(msg["body"]):
        lowered = sentence.lower()
        hits = sum(1 for t in strong if t in lowered)
        if CONCRETE.search(sentence) and hits >= min_hits:
            out.append({"msg_id": msg["id"], "from": msg["from"], "text": sentence, "hits": hits})
    return out


def context_for(store, msg: dict) -> Dict:
    """Facts that might answer `msg`, each tagged with its source message."""
    terms = keywords(msg["subject"] + " " + msg["body"])
    earlier = store.earlier_in_thread(msg)

    facts: List[Dict] = []
    for candidate in earlier:
        facts.extend(_facts_from(candidate, terms, min_hits=1))
    if facts:
        facts.sort(key=lambda f: -f["hits"])
        return {"strategy": "thread-walk", "read": [m["id"] for m in earlier], "facts": facts[:4]}

    hits = store.keyword_search([t for t in terms if len(t) > 4], exclude_id=msg["id"])
    for candidate in hits[:5]:
        facts.extend(_facts_from(candidate, terms, min_hits=2))
    facts.sort(key=lambda f: -f["hits"])
    return {
        "strategy": "keyword" if facts else "none",
        "read": [m["id"] for m in earlier] + [m["id"] for m in hits[:5]],
        "facts": facts[:4],
    }
