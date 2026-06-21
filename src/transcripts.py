"""Build a clean, both-sides transcript from a Vapi call object.

Vapi labels turns from *our* assistant as the assistant role and the other party
(the PGAI agent) as the user role. We relabel them so the transcript reads from the
tester's point of view:

    PATIENT     = our bot (the simulated patient)
    PGAI AGENT  = the agent under test
"""
from __future__ import annotations

ROLE_LABELS = {
    "assistant": "PATIENT",      # our simulated patient
    "bot": "PATIENT",
    "user": "PGAI AGENT",        # the agent we are testing
    "customer": "PGAI AGENT",
    "system": "SYSTEM",
}


def _seconds_to_ts(seconds: float | int | None) -> str:
    if seconds is None:
        return "--:--"
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def from_messages(call: dict) -> str | None:
    """Prefer structured messages (have timestamps + roles)."""
    artifact = call.get("artifact") or {}
    messages = artifact.get("messages") or call.get("messages")
    if not messages:
        return None

    start_ms = None
    lines = []
    for m in messages:
        role = (m.get("role") or "").lower()
        if role == "system":
            continue
        text = (m.get("message") or m.get("content") or "").strip()
        if not text:
            continue
        label = ROLE_LABELS.get(role, role.upper() or "UNKNOWN")
        # secondsFromStart is the most reliable relative timestamp Vapi provides.
        secs = m.get("secondsFromStart")
        if secs is None and m.get("time") is not None:
            if start_ms is None:
                start_ms = m["time"]
            secs = (m["time"] - start_ms) / 1000.0
        lines.append(f"[{_seconds_to_ts(secs)}] {label}: {text}")
    return "\n".join(lines) if lines else None


def from_plain(call: dict) -> str | None:
    """Fallback: Vapi's pre-rendered transcript string ('AI:' / 'User:')."""
    artifact = call.get("artifact") or {}
    raw = artifact.get("transcript") or call.get("transcript")
    if not raw:
        return None
    out = []
    for line in raw.splitlines():
        if line.startswith("AI:"):
            out.append("PATIENT:" + line[3:])
        elif line.startswith("User:"):
            out.append("PGAI AGENT:" + line[5:])
        else:
            out.append(line)
    return "\n".join(out)


def build_transcript(call: dict, header: str = "") -> str:
    body = from_messages(call) or from_plain(call) or "(no transcript captured)"
    return f"{header}\n{body}\n" if header else body + "\n"
