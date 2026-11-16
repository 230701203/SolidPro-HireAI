from dataclasses import dataclass
from typing import Protocol


class SpeechProviderError(Exception):
    """The provider is misconfigured or the call failed. The message is safe to show to staff."""


@dataclass
class Transcript:
    text: str
    confidence: float | None  # 0..1, None when the provider cannot say


class SpeechProvider(Protocol):
    name: str
    model: str
    is_mock: bool

    def transcribe(self, data: bytes, mime: str) -> Transcript: ...
