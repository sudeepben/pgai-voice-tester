# PGAI Voice Tester

An automated voice bot that **calls the Pretty Good AI test line, role-plays a real
patient, records and transcribes every call, and auto-drafts a bug report** of the
issues it finds in the agent under test.

Each call is driven by a distinct *persona* (a patient with a name, DOB, phone, and
a goal) whose only job is to hold a natural, lucid phone conversation and steer it
toward a specific test outcome — appointment scheduling, refills, a weekend-booking
edge case, a possible-emergency safety check, and more.

- **Calls only** `+1-805-439-8008` (the assessment line).
- **12 scenarios** out of the box → a single `call` run produces ≥10 recordings.
- **Hard spend cap** measured against the *real* per-call cost Vapi reports, so a run
  physically cannot blow past your budget.
- Recordings saved as **mp3**, transcripts as both-sides text, plus a generated
  `BUG_REPORT.md`.

---

## How it works (one line)

[Vapi](https://vapi.ai) places the outbound call and runs the whole voice loop
(speech-to-text → patient LLM → text-to-speech → telephony) in one place. We just
hand Vapi a persona, poll the call to completion, then pull down the recording and
transcript. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the why.

---

## Setup (one-time)

### 1. Create a Vapi account and get credentials
Vapi bundles telephony + STT + LLM + TTS, so it's the only account you need.

1. Sign up at **https://dashboard.vapi.ai**.
2. **API key:** top-right org menu → *API Keys* → copy the **Private** key.
3. **Phone number:** *Phone Numbers* → create a free Vapi number. Copy its **ID**
   (a UUID) and the number itself (E.164, e.g. `+18885551234`).
   - This number is the **single number you report on the submission form** — all
     test calls go out from it.

### 2. Configure the project
```bash
pip install -r requirements.txt        # core deps + bundled ffmpeg (no system install)
cp .env.example .env                    # then edit .env
```
Fill in at minimum:
```
VAPI_API_KEY=...            # Vapi Private key
VAPI_PHONE_NUMBER_ID=...    # the phone number's UUID
CALLER_NUMBER=+1...         # the Vapi number itself (for the submission form)
```
Optional — only for the automated bug-analysis pass — set **one** of
`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (and `ANALYZER_PROVIDER` to match).

### 3. (Recommended) Create the patient-side context account
Make a test account at **pgai.us/athena** to understand the product you're testing.
*Do not call the number on its confirmation screen* — only call the assessment line.

---

## Run

```bash
python main.py check          # validate config + Vapi auth — costs nothing
python main.py call           # place ALL 12 scenarios (>=10 calls), with a confirm prompt
python main.py analyze        # LLM-review the transcripts -> BUG_REPORT.md
```

Or end-to-end after `.env` is filled in:
```bash
python main.py check && python main.py call -y && python main.py analyze
```

### Useful variants
```bash
python main.py list                          # show every scenario and what it probes
python main.py call weekend_booking_edge     # run a single scenario
python main.py call refill urgent_triage     # run a chosen subset
python main.py call --repeat 2               # run the full set twice
python main.py call -y                        # skip the confirmation prompt
```

---

## Output

Everything lands in `calls/` (committed as deliverables):

```
calls/
  manifest.json                       # every call: id, status, cost, duration, paths
  findings.json                       # raw bug findings from `analyze`
  call-01-schedule_simple/
    recording.mp3                     # the audio (deliverable)
    transcript.txt                    # both sides, timestamped (PATIENT / PGAI AGENT)
    call.json                         # raw Vapi call object (debugging)
    meta.json                         # this call's summary
  call-02-reschedule/
    ...
BUG_REPORT.md                         # generated, human-reviewable bug report
```

---

## Cost & safety guardrails

A full 12-call run is typically **well under $5** in Vapi + telephony charges.
Controls (all in `.env`):

| Variable | Purpose | Default |
|---|---|---|
| `SPEND_CAP_USD` | Cumulative ceiling; a call that would exceed it is **skipped**, not placed | `12` |
| `MAX_CALL_SECONDS` | Per-call hard duration limit | `210` (3.5 min) |
| `CALL_TIMEOUT_SECONDS` | Give up polling a stuck call | `420` |

The cap is enforced against the **actual cost Vapi reports per call**, so it tracks
real money, not an estimate. Start with a single scenario (`python main.py call
weekend_booking_edge`) to confirm audio quality before running the whole set.

---

## Project layout

```
main.py                 CLI: check | list | call | analyze
src/config.py           env-driven settings + guardrails
src/personas.py         the 12 patient scenarios (voice rules + goals)
src/vapi_client.py      thin Vapi REST client; builds the inline assistant
src/orchestrator.py     places calls, enforces the cap, saves artifacts
src/media.py            download recording -> mp3 (bundled ffmpeg)
src/transcripts.py      both-sides transcript from the Vapi call object
src/analyzer.py         LLM review of transcripts -> BUG_REPORT.md
```

## Notes
- **No secrets are committed.** `.env` is git-ignored; `.env.example` documents every
  variable.
- The in-call "patient brain" runs **inside Vapi** on its bundled model credits, so
  placing calls does **not** require your own OpenAI/Anthropic key. Those keys are
  only used by the optional `analyze` step.
