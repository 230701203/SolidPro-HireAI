"""Google Gemini provider (generateContent REST API over plain httpx, no SDK).

It reuses the prompts, JSON parsing and item validation of the Anthropic provider, so both behave the same way:
resume text is delimited as untrusted data, only valid items are kept, and failures become safe messages.

NOTE: covered by tests that use a mocked HTTP transport. Not run against the live API in development.
"""
import time

import httpx

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.schemas import AIProviderError

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(AnthropicProvider):
    name = "gemini"
    is_mock = False

    def __init__(self, api_key: str, model: str, timeout: int = 60, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise AIProviderError("The AI provider is not configured (GEMINI_API_KEY is empty).")
        if not model or not all(c.isalnum() or c in "-._" for c in model):
            raise AIProviderError("The configured Gemini model name is not valid.")
        self.api_key, self.model, self.timeout = api_key, model, timeout
        self._client = client

    def _complete(self, system: str, user: str, max_tokens: int) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": max(max_tokens * 4, 4096),
                "responseMimeType": "application/json",
            },
        }

        url = f"{API_BASE}/{self.model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "content-type": "application/json",
        }

        retryable_statuses = {408, 429, 500, 502, 503, 504}
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                if self._client is not None:
                    resp = self._client.post(
                        url, json=body, headers=headers
                    )
                else:
                    with httpx.Client(timeout=self.timeout) as client:
                        resp = client.post(
                            url, json=body, headers=headers
                        )

            except httpx.HTTPError as e:
                if attempt == max_attempts - 1:
                    raise AIProviderError(
                        "Could not reach the AI service after multiple attempts. Please try again later."
                    ) from e

                time.sleep(2 ** attempt)
                continue

            if resp.status_code not in retryable_statuses:
                break

            if attempt == max_attempts - 1:
                break

            retry_after = resp.headers.get("Retry-After")

            try:
                delay = min(float(retry_after), 8) if retry_after else 2 ** attempt
            except ValueError:
                delay = 2 ** attempt

            time.sleep(delay)

        # Handle the final HTTP response outside the retry loop.
        if resp.status_code in (400, 401, 403):
            if resp.status_code != 400 or "API_KEY" in resp.text:
                raise AIProviderError(
                    "The AI service rejected the configured API key."
                )

        if resp.status_code == 404:
            raise AIProviderError(
                "The configured Gemini model was not found. Check AI_MODEL / GEMINI_MODEL."
            )

        if resp.status_code == 429:
            raise AIProviderError(
                "The AI service is rate limited right now. Please try again shortly."
            )

        if resp.status_code >= 400:
            raise AIProviderError(
                f"The AI service returned an error ({resp.status_code})."
            )

        try:
            data = resp.json()

            if (data.get("promptFeedback") or {}).get("blockReason"):
                raise AIProviderError(
                    "The AI service declined to process this content."
                )

            candidates = data.get("candidates") or []

            if not candidates:
                raise AIProviderError(
                    "The AI service returned no answer. Please try again."
                )

            parts = (candidates[0].get("content") or {}).get("parts") or []

            text = "".join(
                part.get("text", "")
                for part in parts
                if isinstance(part, dict) and not part.get("thought")
            )

        except (ValueError, AttributeError, TypeError) as e:
            raise AIProviderError(
                "The AI service returned an unreadable answer. Please try again."
            ) from e

        if not text.strip():
            raise AIProviderError(
                "The AI service returned an empty answer. Please try again."
            )

        return text
