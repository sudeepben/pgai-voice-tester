"""Central configuration, loaded from environment / .env.

Everything tunable lives here so the rest of the code stays declarative. Import
`settings` and read attributes; call `settings.validate_for_calls()` before doing
anything that costs money.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of where the command is run from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

CALLS_DIR = PROJECT_ROOT / "calls"
DATA_DIR = PROJECT_ROOT / "data"


def _get(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name, default)
    if val is not None:
        val = val.strip()
    return val or default


def _get_float(name: str, default: float) -> float:
    try:
        return float(_get(name) or default)
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(float(_get(name) or default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    # Vapi
    vapi_api_key: str | None = _get("VAPI_API_KEY")
    vapi_phone_number_id: str | None = _get("VAPI_PHONE_NUMBER_ID")
    caller_number: str | None = _get("CALLER_NUMBER")
    pgai_test_number: str = _get("PGAI_TEST_NUMBER", "+18054398008")
    vapi_base_url: str = _get("VAPI_BASE_URL", "https://api.vapi.ai")

    # In-call patient brain
    patient_model_provider: str = _get("PATIENT_MODEL_PROVIDER", "openai")
    patient_model: str = _get("PATIENT_MODEL", "gpt-4o")
    patient_voice_provider: str = _get("PATIENT_VOICE_PROVIDER", "vapi")
    patient_voice_id: str = _get("PATIENT_VOICE_ID", "Elliot")
    transcriber_provider: str = _get("TRANSCRIBER_PROVIDER", "deepgram")
    transcriber_model: str = _get("TRANSCRIBER_MODEL", "nova-2")

    # Guardrails
    spend_cap_usd: float = _get_float("SPEND_CAP_USD", 12.0)
    max_call_seconds: int = _get_int("MAX_CALL_SECONDS", 210)
    poll_interval_seconds: int = _get_int("POLL_INTERVAL_SECONDS", 6)
    call_timeout_seconds: int = _get_int("CALL_TIMEOUT_SECONDS", 420)

    # Analyzer (optional)
    analyzer_provider: str = _get("ANALYZER_PROVIDER", "openai")
    analyzer_model: str = _get("ANALYZER_MODEL", "gpt-4o")
    openai_api_key: str | None = _get("OPENAI_API_KEY")
    anthropic_api_key: str | None = _get("ANTHROPIC_API_KEY")

    def validate_for_calls(self) -> list[str]:
        """Return a list of human-readable problems blocking call placement."""
        problems = []
        if not self.vapi_api_key:
            problems.append("VAPI_API_KEY is not set (Vapi -> API Keys -> Private key).")
        if not self.vapi_phone_number_id:
            problems.append(
                "VAPI_PHONE_NUMBER_ID is not set (Vapi -> Phone Numbers -> number's ID)."
            )
        if not self.pgai_test_number:
            problems.append("PGAI_TEST_NUMBER is not set.")
        return problems

    def analyzer_key(self) -> str | None:
        if self.analyzer_provider == "anthropic":
            return self.anthropic_api_key
        return self.openai_api_key


settings = Settings()

# Ensure output dirs exist on import — cheap and avoids scattered mkdir calls.
CALLS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
