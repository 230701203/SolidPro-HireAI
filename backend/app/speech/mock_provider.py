"""Development speech provider. It cannot understand audio.

It only "transcribes" recordings that carry an explicit marker (used by tests and demos):
    MOCKSTT:the expected sentence          -> confidence 0.95
    MOCKSTT[0.40]:the expected sentence    -> confidence 0.40
Every real recording gets an empty transcript, which the evaluation flags for a person to listen to. This is deliberate:
a mock must never invent a plausible-looking score for someone's voice.
"""

import re

from app.speech.schemas import Transcript

_MARK = re.compile(rb"MOCKSTT(?:\[(\d(?:\.\d+)?)\])?:([^\x00]*)")


class MockSpeechProvider:
    name = "mock"
    model = "marker-reader-v1"
    is_mock = True

    def transcribe(self, data: bytes, mime: str) -> Transcript:
        m = _MARK.search(data)
        if not m:
            return Transcript(text="", confidence=None)
        conf = float(m.group(1)) if m.group(1) else 0.95
        return Transcript(text=m.group(2).decode("utf-8", "ignore").strip(), confidence=max(0.0, min(1.0, conf)))
