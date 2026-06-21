"""Thin Vapi REST client — just the endpoints we need.

Docs: https://docs.vapi.ai/api-reference
We deliberately keep this small and dependency-light (plain `requests`) so it is
easy to read and audit.
"""
from __future__ import annotations

import requests

from .config import settings
from .personas import Persona


class VapiError(RuntimeError):
    pass


class VapiClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.vapi_api_key
        self.base_url = (base_url or settings.vapi_base_url).rstrip("/")
        if not self.api_key:
            raise VapiError("VAPI_API_KEY is not set.")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    # ── low-level ────────────────────────────────────────────────────────────
    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        resp = self._session.request(method, url, timeout=30, **kwargs)
        if resp.status_code >= 400:
            raise VapiError(
                f"{method} {path} -> {resp.status_code}: {resp.text[:500]}"
            )
        return resp.json() if resp.content else {}

    # ── helpers / sanity checks ──────────────────────────────────────────────
    def list_phone_numbers(self) -> list[dict]:
        return self._request("GET", "/phone-number")

    def ping(self) -> bool:
        """Cheap auth check — lists phone numbers."""
        self.list_phone_numbers()
        return True

    # ── assistant config builder ─────────────────────────────────────────────
    def build_assistant(self, persona: Persona) -> dict:
        """Turn a Persona into an inline Vapi assistant config.

        We send the assistant inline (rather than pre-creating it) so each call is
        fully self-describing and reproducible from the persona definition.
        """
        return {
            "name": f"pgai-tester::{persona.id}",
            "firstMessageMode": persona.first_message_mode,
            "model": {
                "provider": settings.patient_model_provider,
                "model": settings.patient_model,
                "temperature": 0.8,
                "messages": [
                    {"role": "system", "content": persona.system_prompt()}
                ],
            },
            "voice": {
                "provider": settings.patient_voice_provider,
                "voiceId": persona.voice_id or settings.patient_voice_id,
            },
            "transcriber": {
                "provider": settings.transcriber_provider,
                "model": settings.transcriber_model,
                "language": "en",
            },
            "maxDurationSeconds": settings.max_call_seconds,
            "silenceTimeoutSeconds": 30,
            # End the call when our patient says goodbye.
            "endCallPhrases": ["goodbye", "bye bye", "have a good day, bye"],
            # Ensure recording is on (it is by default, but be explicit).
            "artifactPlan": {
                "recordingEnabled": True,
                "recordingFormat": "wav",
                "transcriptPlan": {"enabled": True},
            },
        }

    # ── calls ────────────────────────────────────────────────────────────────
    def create_call(self, persona: Persona) -> dict:
        if not settings.vapi_phone_number_id:
            raise VapiError("VAPI_PHONE_NUMBER_ID is not set.")
        payload = {
            "phoneNumberId": settings.vapi_phone_number_id,
            "customer": {"number": settings.pgai_test_number},
            "assistant": self.build_assistant(persona),
        }
        return self._request("POST", "/call", json=payload)

    def get_call(self, call_id: str) -> dict:
        return self._request("GET", f"/call/{call_id}")
