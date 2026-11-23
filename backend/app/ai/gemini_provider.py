"""Google Gemini provider (generateContent REST API over plain httpx, no SDK).

It reuses the prompts, JSON parsing and item validation of the Anthropic provider, so both behave the same way:
resume text is delimited as untrusted data, only valid items are kept, and failures become safe messages.

NOTE: covered by tests that use a mocked HTTP transport. Not run against the live API in development.
"""

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
            # Gemini 2.5 models count internal "thinking" against the output limit, so leave generous room.
            "generationConfig": {"temperature": 0, "maxOutputTokens": max(max_tokens * 4, 4096), "responseMimeType": "application/json"},
        }
        url = f"{API_BASE}/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "content-type": "application/json"}  # key in a header, never in the URL or logs
        try:
            if self._client is not None:
                resp = self._client.post(url, json=body, headers=headers)
            else:
                with httpx.Client(timeout=self.timeout) as c:
                    resp = c.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise AIProviderError("Could not reach the AI service. Please try again later.") from e
        if resp.status_code in (400, 401, 403):
            # Gemini reports a bad key as 400 API_KEY_INVALID as well as 401/403.
            if resp.status_code != 400 or "API_KEY" in resp.text:
                raise AIProviderError("The AI service rejected the configured API key.")
        if resp.status_code == 404:
            raise AIProviderError("The configured Gemini model was not found. Check AI_MODEL / GEMINI_MODEL.")
        if resp.status_code == 429:
            raise AIProviderError("The AI service is rate limited right now. Please try again shortly.")
        if resp.status_code >= 400:
            raise AIProviderError(f"The AI service returned an error ({resp.status_code}).")
        try:
            data = resp.json()
            if (data.get("promptFeedback") or {}).get("blockReason"):
                raise AIProviderError("The AI service declined to process this content.")
            cands = data.get("candidates") or []
            if not cands:
                raise AIProviderError("The AI service returned no answer. Please try again.")
            parts = (cands[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        except (ValueError, AttributeError, TypeError) as e:
            raise AIProviderError("The AI service returned an unreadable answer. Please try again.") from e
        if not text.strip():
            raise AIProviderError("The AI service returned an empty answer. Please try again.")
        return text
