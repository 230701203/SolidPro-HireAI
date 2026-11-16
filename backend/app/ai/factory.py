from app.ai.anthropic_provider import AnthropicProvider
from app.ai.mock_provider import MockProvider
from app.ai.schemas import AIProvider
from app.core.config import get_settings


def get_provider() -> AIProvider:
    """Raises AIProviderError when the configured provider cannot be used. Never falls back silently to mock."""
    s = get_settings()
    if s.ai_provider == "anthropic":
        return AnthropicProvider(s.anthropic_api_key, s.ai_model, s.ai_timeout_seconds)
    return MockProvider()


def provider_status() -> dict:
    s = get_settings()
    if s.ai_provider == "anthropic":
        return {"provider": "anthropic", "model": s.ai_model, "is_mock": False, "configured": bool(s.anthropic_api_key)}
    return {"provider": "mock", "model": MockProvider.model, "is_mock": True, "configured": True}
