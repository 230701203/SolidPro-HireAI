"""Speech-to-text layer for Repeat the Sentence. Providers return a transcript plus a confidence in [0, 1].

A transcript is evidence for a reviewer, never a verdict: low confidence, empty text or errors are flagged for a person
to listen to the recording.
"""
from app.core.config import get_settings
from app.speech.mock_provider import MockSpeechProvider
from app.speech.openai_provider import OpenAISpeechProvider
from app.speech.schemas import SpeechProvider, SpeechProviderError, Transcript


def get_speech_provider() -> SpeechProvider:
    """Raises SpeechProviderError if the configured provider cannot be used. Never falls back silently to mock."""
    s = get_settings()
    if s.stt_provider == "openai":
        return OpenAISpeechProvider(s.stt_api_key, s.stt_model, s.stt_base_url, s.stt_timeout_seconds)
    return MockSpeechProvider()


def speech_status() -> dict:
    s = get_settings()
    if s.stt_provider == "openai":
        return {"provider": "openai", "model": s.stt_model, "is_mock": False, "configured": bool(s.stt_api_key)}
    return {"provider": "mock", "model": MockSpeechProvider.model, "is_mock": True, "configured": True}


__all__ = ["SpeechProvider", "SpeechProviderError", "Transcript", "get_speech_provider", "speech_status"]
