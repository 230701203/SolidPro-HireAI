"""Gemini provider over a mocked HTTP transport, plus provider selection."""

import json

import httpx
import pytest

from app.ai.factory import get_provider, provider_status
from app.ai.gemini_provider import GeminiProvider
from app.ai.schemas import AIProviderError, GenerationInput
from tests.test_analysis import GOOD, _input, _transport


def _reply(obj) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}, "finishReason": "STOP"}]}


def test_gemini_analysis_sends_key_in_header_and_safe_prompt():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(url=str(req.url), key=req.headers["x-goog-api-key"], body=json.loads(req.content))
        return httpx.Response(200, json=_reply(GOOD))

    out = GeminiProvider("g-test", "gemini-2.5-flash", client=_transport(handler)).analyze_resume(_input())
    assert out.match_score == 100  # 140 clamped
    assert seen["url"].endswith("/models/gemini-2.5-flash:generateContent") and "g-test" not in seen["url"]
    assert seen["key"] == "g-test"
    assert "untrusted" in seen["body"]["systemInstruction"]["parts"][0]["text"]
    assert "<resume>" in seen["body"]["contents"][0]["parts"][0]["text"]
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_ignores_thought_parts_and_reads_fenced_json():
    body = {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": "```json\n" + json.dumps(GOOD) + "\n```"}]}}]}
    assert GeminiProvider("k", "m", client=_transport(lambda r: httpx.Response(200, json=body))).analyze_resume(_input()).match_score == 100


@pytest.mark.parametrize("status,body,fragment", [
    (401, {}, "API key"), (403, {}, "API key"), (400, {"error": {"status": "INVALID_ARGUMENT", "message": "API_KEY_INVALID"}}, "API key"),
    (400, {"error": {"message": "bad request"}}, "error (400)"), (404, {}, "model was not found"), (429, {}, "rate limited"), (500, {}, "error (500)"),
    (200, {"candidates": []}, "no answer"), (200, {"promptFeedback": {"blockReason": "SAFETY"}}, "declined"),
    (200, {"candidates": [{"content": {"parts": [{"text": "great candidate!"}]}}]}, "unreadable"),
    (200, {"candidates": [{"content": {"parts": [{"text": ""}]}}]}, "empty"),
])
def test_gemini_failures_are_safe_messages(status, body, fragment):
    p = GeminiProvider("g-secret", "m", client=_transport(lambda r: httpx.Response(status, json=body)))
    with pytest.raises(AIProviderError) as e:
        p.analyze_resume(_input())
    assert fragment in str(e.value) and "g-secret" not in str(e.value)

def test_gemini_network_error_missing_key_and_bad_model_name():
    def boom(req):
        raise httpx.ConnectError("down")

    with pytest.raises(AIProviderError, match="Could not reach"):
        GeminiProvider("k", "m", client=_transport(boom)).analyze_resume(_input())
    with pytest.raises(AIProviderError, match="GEMINI_API_KEY"):
        GeminiProvider("", "m")
    with pytest.raises(AIProviderError, match="model name"):
        GeminiProvider("k", "m/../../x")  # cannot be used to redirect the request path


def _gen(**kw) -> GenerationInput:
    base = dict(job_title="Engineer", job_description="d", required_skills=["Python"], preferred_skills=[], required_qualifications=None,
                candidate_skills=["Python"], candidate_projects=[], candidate_experience_years=2, resume_text="r", difficulty="easy", count=2)
    return GenerationInput(**{**base, **kw})


def test_gemini_generates_questions_and_drops_invalid_items():
    good = {"text": "What does len([1, 2, 3]) return?", "options": ["1", "2", "3", "4"], "correct_index": 2, "explanation": "Three items.",
            "difficulty": "easy", "topic": "Python", "skill": "Python", "q_type": "technical"}
    bad = {**good, "options": ["1", "1", "3", "4"]}
    p = GeminiProvider("k", "m", client=_transport(lambda r: httpx.Response(200, json=_reply({"questions": [good, bad]}))))
    qs = p.generate_mcq(_gen())
    assert len(qs) == 1 and qs[0].correct_index == 2
    s = GeminiProvider("k", "m", client=_transport(lambda r: httpx.Response(200, json=_reply({"sentences": [{"text": "The team reviewed the drawing before the meeting.", "difficulty": "easy"}]}))))
    assert len(s.generate_sentences(_gen())) == 1


def test_factory_selects_gemini_and_never_falls_back_silently(monkeypatch):
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr("app.ai.factory.get_settings", lambda: s.model_copy(update={"ai_provider": "gemini", "gemini_api_key": "g", "gemini_model": "gemini-2.5-flash"}))
    assert get_provider().name == "gemini"
    assert provider_status() == {"provider": "gemini", "model": "gemini-2.5-flash", "is_mock": False, "configured": True}
    monkeypatch.setattr("app.ai.factory.get_settings", lambda: s.model_copy(update={"ai_provider": "gemini", "gemini_api_key": ""}))
    with pytest.raises(AIProviderError):
        get_provider()
    assert provider_status()["configured"] is False

def test_gemini_retries_temporary_server_error(monkeypatch):
    import app.ai.gemini_provider as gemini_module

    calls = {"count": 0}

    def handler(req):
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json=_reply(GOOD))

    monkeypatch.setattr(gemini_module.time, "sleep", lambda seconds: None)

    provider = GeminiProvider("k", "m", client=_transport(handler))
    result = provider.analyze_resume(_input())

    assert result.match_score == 100
    assert calls["count"] == 3


def test_gemini_stops_after_maximum_retries(monkeypatch):
    import app.ai.gemini_provider as gemini_module

    calls = {"count": 0}

    def handler(req):
        calls["count"] += 1
        return httpx.Response(503, json={"error": "temporary"})

    monkeypatch.setattr(gemini_module.time, "sleep", lambda seconds: None)

    provider = GeminiProvider("k", "m", client=_transport(handler))

    with pytest.raises(AIProviderError, match=r"error \(503\)"):
        provider.analyze_resume(_input())

    assert calls["count"] == 3


def test_gemini_does_not_retry_permanent_error(monkeypatch):
    import app.ai.gemini_provider as gemini_module

    calls = {"count": 0}

    def handler(req):
        calls["count"] += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    monkeypatch.setattr(gemini_module.time, "sleep", lambda seconds: None)

    provider = GeminiProvider("k", "m", client=_transport(handler))

    with pytest.raises(AIProviderError, match=r"error \(400\)"):
        provider.analyze_resume(_input())

    assert calls["count"] == 1
