# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""The rule path: the messages that must never cost a model call.

Receipts, newsletters and platform notifications are recognised by sender
shape and a handful of phrases. Recognising them with an LLM would spend money
and latency on mail whose handling is never in doubt, so they are dispatched
here and the model never sees them.

Order matters: guard.scan() runs before this, so a phishing mail from
billing@... is flagged rather than swept up as a receipt.
"""

import re
from typing import Dict, Optional

NO_REPLY_LOCALPARTS = (
    "no-reply", "noreply", "no_reply", "do-not-reply", "donotreply",
    "notifications", "notification", "notify", "receipts", "receipt",
    "billing", "invoice", "invoice+statements", "alerts", "digest",
    "newsletter", "updates", "orders", "ship-confirm", "checkin",
    "statements", "feedback", "insights", "mailer",
)

NOISE_SENDER_DOMAINS = (
    "dropbox.com", "slack.com", "vercel.com", "1password.com", "amazon.com",
    "members.netflix.com", "google.com", "apple.com", "email.apple.com",
    "spotify.com", "coursera.org", "lyft.com", "github.com", "figma.com",
    "bluebottlecoffee.com", "pagerduty.com", "producthunt.com",
    "accounts.google.com", "sentry.io", "postmarkapp.com", "datadoghq.com",
    "mail.notion.so", "notion.so", "cloudflare.com", "pragmaticengineer.com",
    "robinhood.com", "mailchimp.com", "zoom.us", "digitalocean.com",
    "twitter.com", "medium.com", "substack.com", "stripe.com", "intercom.io",
    "chase.com", "instacart.com", "swiggy.in", "ramp.com", "linkedin.com",
    "doordash.com", "uber.com", "hackernewsletter.com", "todoist.com",
    "united.com", "grammarly.com", "calendly.com", "openai.com",
    "namecheap.com", "email.apple.com",
)

RECEIPT_PHRASES = (
    "receipt", "invoice", "your bill", "was charged", "charged to your card",
    "payment of", "statement is", "statement is available", "auto-renews",
    "payout", "order confirmed", "order is delivered", "has shipped",
    "monthly statement",
)
NEWSLETTER_PHRASES = (
    "read more on our site", "top stories", "daily digest", "this week:",
    "new course recommendations", "upvote", "read in your browser",
    "pick up '", "top 5", "new posts", "recommendations",
)
PLATFORM_PHRASES = (
    "no action is needed", "no action needed", "no issues found",
    "unread activity", "new comments", "new notifications", "appeared in",
    "screen time", "recording is ready", "campaign report", "analytics",
    "actions minutes", "free up space", "verification code", "new sign-in",
    "new login", "new device signed in", "if this wasn't you",
    "monitor ok", "incident resolved", "uptime last week", "check in for",
    "seat selection", "rate your", "5 tasks due", "productive than",
    "delivery rate", "see what's happening", "see what changed",
    "upgrade or free up",
)

# Internal, purely informational mail from the owner's own company.
INTERNAL_FYI_SENDERS = ("facilities@", "notes@", "status@")


def _localpart(address: str) -> str:
    return address.split("@")[0].lower()


def _domain(address: str) -> str:
    return address.split("@")[-1].lower()


def _has(text: str, phrases) -> bool:
    return any(p in text for p in phrases)


def apply(msg: dict) -> Optional[Dict[str, str]]:
    """Return {disposition, reason, category} if a rule decides this message."""
    sender = msg["from"].lower()
    local, dom = _localpart(sender), _domain(sender)
    text = f"{msg['subject']} {msg['body']}".lower()
    machine_sender = any(local.startswith(p) or local == p for p in NO_REPLY_LOCALPARTS)
    known_noise_domain = dom in NOISE_SENDER_DOMAINS

    if machine_sender or known_noise_domain:
        if _has(text, RECEIPT_PHRASES):
            return {"disposition": "archive", "reason": "automated receipt or invoice; for records only", "category": "receipt"}
        if _has(text, NEWSLETTER_PHRASES):
            return {"disposition": "archive", "reason": "newsletter or content digest; nothing is asked of the owner", "category": "newsletter"}
        if _has(text, PLATFORM_PHRASES):
            return {"disposition": "archive", "reason": "platform notification with no action for the owner", "category": "notification"}
        if "do not reply" in text or "this inbox is not monitored" in text:
            return {"disposition": "archive", "reason": "unmonitored automated sender", "category": "notification"}
        if machine_sender and known_noise_domain:
            return {"disposition": "archive", "reason": "automated mail from a known no-reply sender", "category": "notification"}

    if any(sender.startswith(p) for p in INTERNAL_FYI_SENDERS):
        return {"disposition": "archive", "reason": "internal FYI announcement; no reply expected", "category": "internal-fyi"}

    if re.search(r"(submit your timesheet|timesheet by)", text):
        return {"disposition": "defer", "reason": "recurring personal admin task with a stated deadline", "category": "admin-task"}

    if "we received your dispute" in text or "no further action needed" in text:
        return {"disposition": "archive", "reason": "support acknowledgement; explicitly needs no action now", "category": "support-ack"}

    if re.search(r"(renews (in|on)|renewal)", text) and "no action" in text:
        return {"disposition": "archive", "reason": "vendor renewal notice requiring no action", "category": "vendor-notice"}

    return None
