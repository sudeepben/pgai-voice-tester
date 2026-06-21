"""Pretty Good AI — voice tester CLI.

Commands
--------
  python main.py check                 Validate config + Vapi auth (no calls, free).
  python main.py list                  List the available test scenarios.
  python main.py call                  Run ALL scenarios once (>=10 calls).
  python main.py call <id> [<id> ...]  Run only the named scenario(s).
  python main.py call --repeat 2       Run the selected set N times.
  python main.py analyze               LLM-review saved transcripts -> BUG_REPORT.md.

A typical full run after `.env` is filled in:

    python main.py check && python main.py call && python main.py analyze
"""
from __future__ import annotations

import argparse
import sys

# Windows' legacy console defaults to cp1252 and chokes on non-ASCII output.
# Force UTF-8 so transcripts, tables, and arrows render everywhere.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — best effort; nothing to do if unsupported
        pass

from rich.console import Console
from rich.table import Table

from src.config import settings
from src.personas import SCENARIOS
from src.vapi_client import VapiClient, VapiError

console = Console()


def cmd_check(_args) -> int:
    problems = settings.validate_for_calls()
    if problems:
        console.print("[red]Configuration problems:[/]")
        for p in problems:
            console.print(f"  - {p}")
        console.print("\nFill these in your [cyan].env[/] (see .env.example) and retry.")
        return 1
    console.print("[green]OK[/] Required env vars are set.")
    try:
        client = VapiClient()
        client.ping()
    except VapiError as e:
        console.print(f"[red]Vapi auth/connectivity failed:[/] {e}")
        return 1
    console.print("[green]OK[/] Vapi API key works and is reachable.")
    console.print(
        f"\nReady to call [cyan]{settings.pgai_test_number}[/] from "
        f"[cyan]{settings.caller_number or '(CALLER_NUMBER not set)'}[/].\n"
        f"Spend cap: ${settings.spend_cap_usd:.2f} - max call {settings.max_call_seconds}s."
    )
    return 0


def cmd_list(_args) -> int:
    table = Table(title="Test scenarios")
    table.add_column("id", style="cyan")
    table.add_column("Title")
    table.add_column("Probes for")
    for s in SCENARIOS:
        table.add_row(s.id, s.title, s.probe)
    console.print(table)
    console.print(f"\n{len(SCENARIOS)} scenarios. `python main.py call` runs all of them.")
    return 0


def cmd_call(args) -> int:
    problems = settings.validate_for_calls()
    if problems:
        console.print("[red]Cannot place calls - fix config first (`python main.py check`).[/]")
        for p in problems:
            console.print(f"  - {p}")
        return 1

    # Import here so `check`/`list` work even without optional deps installed.
    from src.orchestrator import Orchestrator, select_personas

    personas = select_personas(args.scenarios or None)
    n = len(personas) * args.repeat
    console.print(
        f"About to place [bold]{n}[/] call(s) to {settings.pgai_test_number} "
        f"(cap ${settings.spend_cap_usd:.2f})."
    )
    if not args.yes:
        try:
            reply = input("Proceed? [y/N] ").strip().lower()
        except EOFError:
            reply = "n"
        if reply not in ("y", "yes"):
            console.print("Aborted.")
            return 1

    orch = Orchestrator()
    results = orch.run(personas, repeats=args.repeat)
    failed = [r for r in results if r.status not in ("ended", "completed")]
    return 0 if not failed else 2


def cmd_analyze(_args) -> int:
    from src.analyzer import analyze_all

    path = analyze_all()
    console.print(f"[green]OK[/] Wrote [cyan]{path}[/]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="PGAI voice tester")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Validate config + Vapi auth (no cost).").set_defaults(func=cmd_check)
    sub.add_parser("list", help="List test scenarios.").set_defaults(func=cmd_list)

    c = sub.add_parser("call", help="Place test calls.")
    c.add_argument("scenarios", nargs="*", help="Scenario id(s); omit to run all.")
    c.add_argument("--repeat", type=int, default=1, help="Run the selected set N times.")
    c.add_argument("-y", "--yes", action="store_true", help="Skip the confirmation prompt.")
    c.set_defaults(func=cmd_call)

    sub.add_parser("analyze", help="LLM-review transcripts -> BUG_REPORT.md.").set_defaults(func=cmd_analyze)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
