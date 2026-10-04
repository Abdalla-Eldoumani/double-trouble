import io
import math
import struct
import wave

import pytest

from app import briefing
from engine.agent import run
from engine.planner import compare, explain


def wav(amplitude, seconds=1.0, rate=16000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(struct.pack("<h", int(amplitude * math.sin(i / 8))) for i in range(int(rate * seconds))))
    return buffer.getvalue()


def fake_client(monkeypatch, text):
    class STT:
        def convert(self, **kwargs):
            return type("Transcript", (), {"text": text})()

    class Client:
        speech_to_text = STT()

    monkeypatch.setattr(briefing, "_client", lambda key: Client())


def test_a_silent_recording_is_refused_before_any_api_call():
    with pytest.raises(briefing.SpeechError, match="almost silent"):
        briefing.validate_recording(wav(amplitude=30))
    briefing.validate_recording(wav(amplitude=8000))


def test_a_filler_word_in_another_script_is_not_passed_to_the_planner(monkeypatch):
    fake_client(monkeypatch, "うん。")
    with pytest.raises(briefing.SpeechError, match="English request"):
        briefing.transcribe(wav(amplitude=8000), "test-key-not-real")


def test_an_english_request_comes_through(monkeypatch):
    fake_client(monkeypatch, " Show the top 5 locations in northwest Calgary. ")
    assert briefing.transcribe(wav(amplitude=8000), "test-key-not-real") == "Show the top 5 locations in northwest Calgary."


def test_planner_reply_never_prints_float_noise():
    result = run({"w_severity": 0.75}, tune=False, constraints={"region": "SE"})
    text = explain(result, compare(None, result), [])
    assert "00000" not in text and "99999" not in text
