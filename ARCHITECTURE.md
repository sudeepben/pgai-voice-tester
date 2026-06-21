# Architecture

**The system turns a declarative "patient persona" into a real phone call and back
into reviewable evidence.** A persona (`src/personas.py`) is just data — an
identity, a goal, and scenario instructions written specifically for *voice* (short
turns, one request at a time, active steering, a clean goodbye). The orchestrator
(`src/orchestrator.py`) hands that persona to **Vapi**, which runs the entire
real-time voice loop — telephony, speech-to-text (Deepgram `nova-2`), the patient
LLM (`gpt-4o`), and text-to-speech — as a single low-latency service and places the
outbound call to the assessment line. We then poll the call to completion, download
the recording, transcode it to mp3 with a bundled ffmpeg (`src/media.py`), and write
a both-sides, timestamped transcript (`src/transcripts.py`). An optional analyzer
(`src/analyzer.py`) re-reads those transcripts with an LLM acting as a QA engineer
and drafts `BUG_REPORT.md`. The CLI (`main.py`) exposes this as `check → call →
analyze`.

**The key design choice is to let Vapi own the voice loop instead of wiring STT, an
LLM, TTS, and a telephony provider together ourselves.** The challenge's #1
criterion is a *lucid voice conversation*, and that is overwhelmingly a
latency-and-turn-taking problem; an integrated provider gives natural barge-in and
sub-second response out of the box, which a hand-rolled pipeline rarely matches
without significant tuning. It also collapses setup to a single account and keeps
cost low and observable — we read Vapi's real per-call cost and enforce a hard spend
cap *before* each call, so a run cannot exceed budget. Everything that matters lives
in the persona definitions and the shared `VOICE_RULES`, so improving conversation
quality or adding edge cases means editing data, not plumbing — and the assistant is
sent **inline** with every call so each run is fully reproducible from its persona.
Personas deliberately carry a fixed fake identity (name/DOB/phone) and each picks a
distinct voice, which keeps calls coherent (no mid-call detail drift) and the
recordings varied. The 12 scenarios are chosen to span the brief — routine
scheduling, reschedule/cancel, refills, factual Q&A — and to actively hunt for bugs:
a weekend/closed-day booking trap, a possible-emergency safety check, identity-
verification gaps on refills, multi-intent task tracking, barge-in robustness, and
out-of-scope diagnosis/billing boundaries.
