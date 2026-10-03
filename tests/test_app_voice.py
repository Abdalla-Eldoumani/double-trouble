import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import briefing  # noqa: E402

MAIN = str(ROOT / "app" / "main.py")
EXAMPLE = ("Prioritize recent crashes twice as much, only show northwest Calgary, "
           "and assume we can only investigate five intersections.")


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    st.cache_data.clear()
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    yield
    st.cache_data.clear()


def run_app():
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def ask(at, text):
    at.text_input(key="planner_text").set_value(text)
    next(b for b in at.button if b.label == "Run request").click().run()
    assert not at.exception, at.exception
    return next(i.value for i in at.info if "You asked" in i.value)


def test_typed_request_reranks_with_the_real_engine():
    at = run_app()
    reply = ask(at, EXAMPLE)
    assert "northwest Calgary only" in reply and "a budget of 5 intersections" in reply
    assert "count twice" in reply and "Backtest" in reply
    assert any(h.value == "Top 5 on the map" for h in at.subheader)
    assert any(h.value.endswith("of 5 the same as count-only") for h in at.subheader)
    ranked = at.table[-1].value
    assert len(ranked) == 5 and all(name.endswith("NW") for name in ranked["Location"])
    assert not at.warning


def test_follow_up_keeps_earlier_settings_and_reports_the_change():
    at = run_app()
    ask(at, EXAMPLE)
    reply = ask(at, "Now show me the northeast instead.")
    assert "northeast Calgary only" in reply
    assert "replaces the top 5 for northwest Calgary" in reply
    assert all(name.endswith("NE") for name in at.table[-1].value["Location"])


def test_tune_respects_the_provincial_checkbox():
    at = run_app()
    at.checkbox(key="exclude_provincial").uncheck().run()
    next(b for b in at.button if b.label == "Let the agent tune it").click().run()
    assert not at.exception, at.exception
    assert at.checkbox(key="exclude_provincial").value is False


def test_spoken_reply_uses_elevenlabs_when_a_key_is_set(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")
    spoken = []

    class FakeTTS:
        def convert(self, **kwargs):
            spoken.append(kwargs["text"])
            return iter([b"ID3", b"audio"])

    class FakeClient:
        def __init__(self, api_key):
            self.text_to_speech = FakeTTS()

    monkeypatch.setattr("elevenlabs.client.ElevenLabs", FakeClient)
    at = run_app()
    reply = ask(at, EXAMPLE)
    assert spoken and spoken[-1] in reply
    assert not at.error


def test_transcribe_sends_audio_to_scribe(monkeypatch):
    sent = []

    class FakeSTT:
        def convert(self, **kwargs):
            sent.append(kwargs)
            return type("Transcript", (), {"text": "  only show northwest Calgary  "})()

    class FakeClient:
        def __init__(self, api_key):
            self.speech_to_text = FakeSTT()

    monkeypatch.setattr("elevenlabs.client.ElevenLabs", FakeClient)
    audio = ("request.wav", b"RIFF", "audio/wav")
    assert briefing.transcribe(audio, "test-key-not-real") == "only show northwest Calgary"
    assert sent == [{"file": audio, "model_id": briefing.STT_MODEL_ID}]
