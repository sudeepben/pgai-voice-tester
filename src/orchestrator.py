"""Run test calls end-to-end and save the deliverables.

For each persona the orchestrator:
  1. Checks the cumulative spend cap (aborts BEFORE a call that would exceed it).
  2. Places the call via Vapi (our patient persona dials the PGAI test number).
  3. Polls the call until it ends (or times out).
  4. Downloads the recording as mp3 and writes a both-sides transcript.
  5. Records a per-call meta.json and appends to a run manifest.

Artifacts land in `calls/`:

    calls/
      manifest.json                      ← summary of every call in the run
      call-01-schedule_simple/
        recording.mp3
        transcript.txt
        call.json                        ← raw Vapi call object (debugging)
        meta.json                        ← id, scenario, cost, duration, status

The spend cap uses the real per-call cost Vapi reports, so the ceiling reflects
actual money spent, not an estimate.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import transcripts
from .config import CALLS_DIR, settings
from .media import fetch_recording_as_mp3
from .personas import Persona, SCENARIOS, by_id
from .vapi_client import VapiClient, VapiError

console = Console()

_TERMINAL_STATUSES = {"ended", "failed", "completed", "busy", "no-answer", "canceled"}


@dataclass
class CallResult:
    index: int
    scenario_id: str
    title: str
    call_id: str | None
    status: str
    ended_reason: str | None
    cost_usd: float
    duration_seconds: float
    transcript_path: str | None
    recording_path: str | None
    dir: str
    error: str | None = None


def _slugged_dir(index: int, persona: Persona) -> Path:
    d = CALLS_DIR / f"call-{index:02d}-{persona.id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _recording_url(call: dict) -> str | None:
    """Vapi exposes the recording in a few shapes depending on plan/version.

    Try the known locations in order and return the first non-empty URL.
    """
    artifact = call.get("artifact") or {}
    rec = artifact.get("recording") if isinstance(artifact.get("recording"), dict) else {}
    mono = rec.get("mono") if isinstance(rec.get("mono"), dict) else {}
    candidates = [
        artifact.get("recordingUrl"),
        call.get("recordingUrl"),
        rec.get("combinedUrl"),
        rec.get("stereoUrl"),
        mono.get("combinedUrl"),
    ]
    return next((u for u in candidates if u), None)


def _duration_seconds(call: dict) -> float:
    started = call.get("startedAt")
    ended = call.get("endedAt")
    # Vapi timestamps are ISO-8601 strings; fall back to messages if absent.
    if started and ended:
        from datetime import datetime

        def _p(ts: str) -> float:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()

        try:
            return max(0.0, _p(ended) - _p(started))
        except ValueError:
            pass
    msgs = (call.get("artifact") or {}).get("messages") or []
    secs = [m.get("secondsFromStart") for m in msgs if m.get("secondsFromStart") is not None]
    return float(max(secs)) if secs else 0.0


class Orchestrator:
    def __init__(self, client: VapiClient | None = None):
        self.client = client or VapiClient()
        self.spent_usd = 0.0

    # ── one call ─────────────────────────────────────────────────────────────
    def _wait_for_call(self, call_id: str) -> dict:
        deadline = time.monotonic() + settings.call_timeout_seconds
        last_status = ""
        while time.monotonic() < deadline:
            try:
                call = self.client.get_call(call_id)
            except VapiError as e:
                # A transient poll failure must not abort an in-progress call; keep
                # polling until the deadline. (The client already retried internally.)
                console.print(f"    [yellow]poll error (continuing): {e}[/]")
                time.sleep(settings.poll_interval_seconds)
                continue
            status = (call.get("status") or "").lower()
            if status != last_status:
                console.print(f"    · status: [cyan]{status or '?'}[/]")
                last_status = status
            if status in _TERMINAL_STATUSES:
                return call
            time.sleep(settings.poll_interval_seconds)
        raise VapiError(f"call {call_id} did not finish within {settings.call_timeout_seconds}s")

    def run_one(self, persona: Persona, index: int) -> CallResult:
        out_dir = _slugged_dir(index, persona)
        console.print(f"\n[bold]({index:02d}) {persona.title}[/]  [dim]{persona.id}[/]")

        # Spend guardrail — refuse to start a call once we are over the cap.
        if self.spent_usd >= settings.spend_cap_usd:
            msg = f"spend cap ${settings.spend_cap_usd:.2f} reached (spent ${self.spent_usd:.2f}); skipping"
            console.print(f"    [yellow]{msg}[/]")
            return CallResult(index, persona.id, persona.title, None, "skipped", "spend_cap",
                              0.0, 0.0, None, None, str(out_dir), error=msg)

        try:
            created = self.client.create_call(persona)
        except VapiError as e:
            console.print(f"    [red]failed to create call:[/] {e}")
            return CallResult(index, persona.id, persona.title, None, "failed", "create_error",
                              0.0, 0.0, None, None, str(out_dir), error=str(e))

        call_id = created.get("id")
        console.print(f"    · call id: [dim]{call_id}[/]  → dialing {settings.pgai_test_number}")

        try:
            call = self._wait_for_call(call_id)
        except VapiError as e:
            console.print(f"    [red]{e}[/]")
            return CallResult(index, persona.id, persona.title, call_id, "timeout", "timeout",
                              0.0, 0.0, None, None, str(out_dir), error=str(e))

        # Persist the raw call object for debugging / reproducibility.
        (out_dir / "call.json").write_text(json.dumps(call, indent=2), encoding="utf-8")

        cost = float(call.get("cost") or 0.0)
        self.spent_usd += cost
        duration = _duration_seconds(call)
        status = (call.get("status") or "unknown").lower()
        ended_reason = call.get("endedReason")

        # Transcript.
        header = (
            f"# {persona.title}  ({persona.id})\n"
            f"# call_id: {call_id}\n"
            f"# probe: {persona.probe}\n"
            f"# duration: {duration:.0f}s  cost: ${cost:.3f}  ended: {ended_reason}\n"
        )
        transcript_text = transcripts.build_transcript(call, header=header)
        tpath = out_dir / "transcript.txt"
        tpath.write_text(transcript_text, encoding="utf-8")

        # Recording → mp3.
        rec_path = None
        url = _recording_url(call)
        if url:
            try:
                mp3 = fetch_recording_as_mp3(url, out_dir, stem="recording")
                rec_path = str(mp3) if mp3 else None
            except Exception as e:  # noqa: BLE001 — never let a bad download abort the run
                console.print(f"    [yellow]recording download failed:[/] {e}")
        else:
            console.print("    [yellow]no recording URL on call object[/]")

        console.print(
            f"    [green]done[/] · {duration:.0f}s · ${cost:.3f} · "
            f"transcript: {tpath.name}" + (f" · {Path(rec_path).name}" if rec_path else "")
        )

        result = CallResult(
            index, persona.id, persona.title, call_id, status, ended_reason,
            cost, duration, str(tpath), rec_path, str(out_dir),
        )
        (out_dir / "meta.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        return result

    # ── a whole run ──────────────────────────────────────────────────────────
    def run(self, personas: list[Persona], repeats: int = 1) -> list[CallResult]:
        results: list[CallResult] = []
        index = 0
        for r in range(repeats):
            for persona in personas:
                index += 1
                results.append(self.run_one(persona, index))
        self._write_manifest(results)
        self._summary(results)
        return results

    def _write_manifest(self, results: list[CallResult]) -> None:
        manifest = {
            "caller_number": settings.caller_number,
            "test_number": settings.pgai_test_number,
            "total_cost_usd": round(self.spent_usd, 4),
            "spend_cap_usd": settings.spend_cap_usd,
            "calls": [asdict(r) for r in results],
        }
        (CALLS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _summary(self, results: list[CallResult]) -> None:
        table = Table(title="Call run summary", show_lines=False)
        table.add_column("#", justify="right")
        table.add_column("Scenario")
        table.add_column("Status")
        table.add_column("Dur", justify="right")
        table.add_column("Cost", justify="right")
        table.add_column("Recording")
        for r in results:
            ok = r.status in {"ended", "completed"}
            table.add_row(
                f"{r.index:02d}",
                r.title,
                f"[green]{r.status}[/]" if ok else f"[yellow]{r.status}[/]",
                f"{r.duration_seconds:.0f}s",
                f"${r.cost_usd:.3f}",
                "✓" if r.recording_path else "—",
            )
        console.print(table)
        console.print(
            f"\n[bold]Total spent:[/] ${self.spent_usd:.3f} "
            f"(cap ${settings.spend_cap_usd:.2f})  ·  artifacts in [cyan]{CALLS_DIR}[/]"
        )


def select_personas(scenario_ids: list[str] | None) -> list[Persona]:
    if not scenario_ids:
        return list(SCENARIOS)
    chosen = []
    for sid in scenario_ids:
        p = by_id(sid)
        if not p:
            raise SystemExit(f"unknown scenario id: {sid!r}. Known: {[s.id for s in SCENARIOS]}")
        chosen.append(p)
    return chosen
