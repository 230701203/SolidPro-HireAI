"""OpenAI-compatible `/audio/transcriptions` provider (plain httpx).

NOTE: covered by tests with a mocked HTTP transport only. It has NOT been run against a live service (no key in
development). Known limitation of any language-model based recogniser: it may silently "fix" a mispronounced or
missing word, which can hide omissions, so transcripts stay advisory and reviewers can always listen to the audio.
The expected sentence is deliberately NOT sent as a prompt, to avoid biasing the transcript towards it.
"""

import math

import httpx

from app.speech.schemas import SpeechProviderError, Transcript

_EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/mp4": "mp4"}


class OpenAISpeechProvider:
    name = "openai"
    is_mock = False

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise SpeechProviderError("Speech-to-text is set to 'openai' but STT_API_KEY is empty.")
        self.api_key, self.model, self.base_url, self.timeout, self._transport = api_key, model, base_url.rstrip("/"), timeout, transport

    def transcribe(self, data: bytes, mime: str) -> Transcript:
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                r = client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={"model": self.model, "response_format": "verbose_json", "temperature": "0", "language": "en"},
                    files={"file": (f"answer.{_EXT.get(mime, 'webm')}", data, mime)},
                )
        except httpx.HTTPError as exc:
            raise SpeechProviderError("The speech service could not be reached.") from exc
        if r.status_code != 200:
            raise SpeechProviderError(f"The speech service returned HTTP {r.status_code}.")
        try:
            body = r.json()
            text = str(body.get("text", "")).strip()
        except ValueError as exc:
            raise SpeechProviderError("The speech service returned an unreadable response.") from exc
        segs = [s for s in body.get("segments") or [] if isinstance(s, dict)]
        confidence = None
        logs = [s["avg_logprob"] for s in segs if isinstance(s.get("avg_logprob"), (int, float))]
        if logs:
            confidence = max(0.0, min(1.0, math.exp(sum(logs) / len(logs))))
            if any(isinstance(s.get("no_speech_prob"), (int, float)) and s["no_speech_prob"] > 0.6 for s in segs):
                confidence = min(confidence, 0.3)  # probably silence or noise
        return Transcript(text=text, confidence=confidence)
