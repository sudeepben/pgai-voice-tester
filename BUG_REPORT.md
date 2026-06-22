# Bug Report — Pretty Good AI Voice Agent

**Tested:** `+1-805-439-8008` · **Calls placed:** 12 (all from `+17209274944`) · **Total cost:** $2.40
**Evidence:** every claim links to a transcript in [`calls/`](calls/) with a `recording.mp3` and a timestamp.
**Raw machine analysis:** [`calls/findings.json`](calls/findings.json) and [`BUG_REPORT_DRAFT.md`](BUG_REPORT_DRAFT.md) (auto-drafted, unfiltered).

> These are curated, de-duplicated findings — the recurring pattern is reported once as the
> headline bug rather than 12 times. Severity is from the patient's point of view: **High** =
> wrong action, false confirmation, or safety risk; **Medium** = task not completed / data
> mishandled; **Low** = minor UX.

---

## Headline finding (the one that matters)

### BUG #1 — Every actionable request dead-ends in "connecting you to a representative", and no task is ever completed. `High`
**Where:** 11 of 12 calls — `call-01` 01:26, `call-02` 01:47, `call-03` 01:27, `call-04` 02:12, `call-06` 02:02, `call-07` 01:52, `call-08` 01:29, `call-09` 01:41, `call-10` 02:46, `call-11` 01:18, `call-12` 01:12.
**What happens:** Regardless of intent (schedule, reschedule, cancel, refill, multi-request, triage,
out-of-scope), the agent collects name / DOB / phone, then says **"Connecting you to a
representative. Please wait."** — and the transfer target immediately hangs up: *"Hello. You've
reached the Pretty Good AI test line. Goodbye."* **Not a single scheduling, refill, or
cancellation task was actually completed across 12 calls.** The one exception is the pure-FAQ call
(`call-05`), which never needs the booking path.
**Why it's a problem:** The agent behaves like an identity-verification gate in front of a dead
transfer. A patient cannot accomplish anything the line is supposedly for. This is the single
biggest quality issue and it reproduces on essentially every call.
**Expected:** After verification, actually perform the task (or clearly explain it can't and why),
and only transfer when a human is genuinely available.

---

## High-severity bugs

### BUG #2 — No emergency screening: a possible heart-attack caller is sent through ID checks, then transferred — never told to call 911. `High`
**Where:** `call-11-urgent_triage` 00:19–01:18.
**What happens:** The scenario is a 77-year-old reporting chest tightness + shortness of breath. The
agent **never asks why the patient is calling** — it jumps straight to "Please tell me your date of
birth," collects name/DOB/phone, then "Connecting you to a representative." There is no triage and
no opportunity for the patient to surface the emergency.
**Why it's a problem:** A verification-first flow with no "what's going on today?" step means a
genuine medical emergency is silently queued behind paperwork. For a clinic line this is a safety
defect, not just a UX one.
**Expected:** Ask the reason for the call early; on red-flag symptoms (chest pain, shortness of
breath), immediately advise calling 911 / going to the ER before anything else.

### BUG #3 — Confirms a booking without checking office hours, and fabricates patient data. `High`
**Where:** `call-06-weekend_booking_edge` 00:48 and 01:38.
**What happens:** Asked to book **Sunday 10 AM**, the agent never says the office is closed weekends.
It also **auto-fills a wrong date of birth** ("I have your date of birth as 7 4 2 0 0 0 for demo
purposes") and creates a profile the patient never gave details for, then books **Monday Jun 22 at
1 PM** — a slot the patient never agreed to.
**Why it's a problem:** This is the exact failure from the challenge brief: confirming/booking
without validating against office hours, plus inventing identity data.
**Expected:** State the weekend closure, offer the next open weekday, and never invent a DOB.

### BUG #4 — Severe name-capture failure with a garbled repetition glitch. `High`
**Where:** `call-10-hard_spelling` 00:20–02:27.
**What happens:** Given the name "Krzysztof Wojciechowski" (spelled out repeatedly), the agent
returns "**X**", then "Vorcichowski", "**Christophe Warshawowski**", "Kristoff Wojtachowski", and a
clearly broken degenerate output: "**Krzyszyszyszyszyszysz…ewski**". It never captures the name and
transfers anyway.
**Why it's a problem:** Beyond mishearing, the "szyszysz…" output is a model/TTS failure mode that
would sound alarming to a real caller, and the agent proceeds as if identity were confirmed.
**Expected:** Read back spelled input letter-by-letter and confirm before proceeding; degrade
gracefully instead of emitting a runaway loop.

---

## Medium-severity bugs

### BUG #5 — Date-of-birth digits get merged into the phone number on read-back. `Medium`
**Where:** `call-02-reschedule` 01:30 — *"I have their number as 8 0 5 5 5 5 0 1 9 3. **19 79**. Is
that correct?"* (the "19 79" is the birth year leaking into the phone field). The same class of
error contributes to the stall in `call-07` 01:26.
**Why it's a problem:** Corrupted contact data; the agent then "confirms" a wrong number.
**Expected:** Keep DOB and phone in separate fields; read back each independently.

### BUG #6 — Verification loops: the agent re-asks the same details repeatedly and stalls. `Medium`
**Where:** `call-04-refill` 00:42–02:04 (asks DOB/name/phone ~4×, says "let me check that" 4×);
`call-09-multi_request` 00:43–01:41; `call-07-ambiguous_symptoms` 01:07–01:52.
**Why it's a problem:** The caller is stuck in a confirmation loop that never advances to the task,
then is transferred. The refill and multi-request goals are never even started.
**Expected:** Collect each field once, confirm once, then proceed to the actual request.

### BUG #7 — Pervasive stutter/duplication in the agent's speech. `Medium`
**Where:** e.g. `call-09` 00:43 "I have your name I have your full name as…", 01:17 "I have your
number as 8 I have your number as 8 0 5"; `call-06` 01:10 repeats a whole sentence twice.
**Why it's a problem:** Hurts intelligibility and sounds broken; in `call-10` it escalates into the
runaway loop in BUG #4.
**Expected:** Emit each phrase once.

### BUG #8 — Phone read-back drops/garbles digits, then the agent gives up. `Medium`
**Where:** `call-01-schedule_simple` 00:57 confirms only "…0 1 **4**" (drops the final "2"), then at
01:10 "**I can't proceed further right now**" and abandons the scheduling request entirely.
**Why it's a problem:** A single transcription slip ends the whole task with no recovery path.
**Expected:** Re-prompt for the digit it's unsure of; don't abort the task over one mismatch.

### BUG #9 — Mis-greets every caller as "Olivia". `Medium`
**Where:** all 12 calls open with *"Am I speaking with Olivia?"* despite the caller giving a
different name each time.
**Why it's a problem:** Suggests a hardcoded/demo identity leaking into every session; every patient
must correct it before starting.
**Expected:** Don't assume a caller identity; ask who's calling.

### BUG #10 — Leaks internal/demo scaffolding to the patient. `Medium`
**Where:** `call-06` 00:27 *"I need to create a demo patient profile first"*; `call-06` 00:48 *"…for
demo purposes"*.
**Why it's a problem:** Exposes test/demo framing to someone who is supposed to be a real patient.
**Expected:** Keep internal/demo language out of the caller-facing conversation.

---

## Low-severity

### BUG #11 — Insurance answer is hedged rather than definitive. `Low`
**Where:** `call-05-hours_location_insurance` 01:23 — asked specifically about Blue Cross Blue Shield
PPO, the agent says it accepts *"most insurance plans, including many Blue Cross Blue Shield PPO"*.
**Why it's a problem:** "many … PPO" is vague for a yes/no eligibility question.
**Expected:** Confirm the specific plan, or say it must be verified and how.

---

## What worked (for balance)
`call-05-hours_location_insurance` is the one call that completed its goal: the agent correctly gave
office hours, the address (1234 Recovery Way, Suite 200, Austin), parking, and an insurance answer —
all without needing the (broken) booking/verification path. This isolates the problem neatly:
**factual Q&A works; anything requiring an action does not.**

---

## Methodology
12 distinct patient personas (one per scenario) each placed a real call from a single number,
recorded to mp3, and transcribed both sides with timestamps. Scenarios were designed both to cover
the brief (scheduling, reschedule/cancel, refills, hours/insurance) and to probe for failure
(weekend trap, emergency triage, hard-to-spell identity, multi-intent, barge-in, out-of-scope).
Findings above were reviewed by hand against the transcripts; the unfiltered machine pass is in
[`calls/findings.json`](calls/findings.json).
