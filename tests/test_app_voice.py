import html
import re
import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import briefing, ui  # noqa: E402

MAIN = str(ROOT / "app" / "main.py")
EXAMPLE = "We can investigate five locations in northwest Calgary. Give recent crashes twice the importance."


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    st.cache_data.clear()
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(briefing.st, "secrets", {})
    yield
    st.cache_data.clear()


def run_app():
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def page_text(at):
    return html.unescape(" ".join(md.value for md in at.markdown))


def shortlist_names(at):
    ledger = next(md.value for md in at.markdown if 'class="dt ledger"' in md.value)
    return [html.unescape(n) for n in re.findall(r'class="lg-name">(.*?)</span>', ledger)]


def ask(at, text):
    at.text_input(key="planner_text").set_value(text)
    next(b for b in at.button if b.label == "Update recommendations").click().run()
    assert not at.exception, at.exception
    reply = at.session_state["reply"]["text"]
    assert "You asked" in page_text(at) and reply in page_text(at)
    return reply


def test_typed_request_reranks_with_the_real_engine():
    at = run_app()
    reply = ask(at, EXAMPLE)
    assert "northwest Calgary" in reply and "up to 5 locations" in reply
    assert "weighted twice as much" in reply and "Backtest" not in reply
    assert "Up to 5 locations in Northwest Calgary" in page_text(at)
    assert re.search(r"Top-list overlap: \d of 5", ui.validation(at.session_state["last_result"]))
    assert at.selectbox(key="area").value == "NW"
    assert at.number_input(key="capacity").value == 5
    assert at.selectbox(key="priorities").value == "Recent activity"
    names = shortlist_names(at)
    assert len(names) == 5 and all(name.endswith("NW") for name in names)
    assert not at.warning


def test_follow_up_keeps_earlier_settings_and_reports_the_change():
    at = run_app()
    ask(at, EXAMPLE)
    reply = ask(at, "Now show me the northeast instead.")
    assert reply == "Got it. Showing northeast Calgary only."
    assert at.number_input(key="capacity").value == 5
    assert at.slider(key="recent_weight").value == 2
    assert all(name.endswith("NE") for name in shortlist_names(at))


def test_tune_respects_the_provincial_checkbox():
    at = run_app()
    at.checkbox(key="exclude_provincial").uncheck().run()
    next(b for b in at.button if b.label == "Test ranking options automatically").click().run()
    assert not at.exception, at.exception
    assert at.checkbox(key="exclude_provincial").value is False


def test_typed_request_speaks_short_reply_once_after_apply(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "test-voice")
    monkeypatch.setenv("ELEVENLABS_TTS_MODEL_ID", "test-model")
    at = run_app()  # initialize source refresh before replacing speech helpers
    calls = []

    def synthesize(text, key, **kwargs):
        # Speech starts only after the engine has applied the parsed settings.
        assert st.session_state.settings["constraints"] == {"region": "NW", "budget": 5, "recent_weight": 2}
        assert st.session_state.reply["text"] == text
        calls.append((text, key, kwargs))
        return b"ID3mocked confirmation"

    def forbidden(*args, **kwargs):
        pytest.fail("Typed planning must not invoke STT")
    monkeypatch.setattr(briefing, "synthesize", synthesize)
    monkeypatch.setattr(briefing, "transcribe", forbidden)
    at.run()
    assert not calls and not at.get("audio")
    reply = ask(at, EXAMPLE)
    assert reply.startswith("Got it.") and len(reply.split()) < 30
    assert calls == [(reply, "test-key-not-real", {"voice_id": "test-voice", "model_id": "test-model",
                                                 "action": "Reading the confirmation"})]
    assert at.session_state["reply"]["audio"] == b"ID3mocked confirmation"
    assert len(at.get("audio")) == 1 and at.get("audio")[0].proto.autoplay
    saved_reply = dict(at.session_state["reply"])
    at.toggle(key="dark_mode").set_value(True).run()
    at.run()  # focus/ordinary rerun
    assert len(calls) == 1 and at.session_state["reply"] == saved_reply
    assert len(at.get("audio")) == 1 and not at.get("audio")[0].proto.autoplay
    at.selectbox(key="area").select("NE").run()
    next(b for b in at.button if b.label == "Test ranking options automatically").click().run()
    assert not at.exception and len(calls) == 1
    assert not at.get("audio_input") and not at.get("audio")
    assert not at.error


def test_transcribe_sends_audio_to_scribe(monkeypatch):
    sent = []

    class FakeSTT:
        def convert(self, **kwargs):
            sent.append(kwargs)
            return type("Transcript", (), {"text": "  only show northwest Calgary  "})()

    class FakeClient:
        def __init__(self, api_key, timeout):
            self.speech_to_text = FakeSTT()

    monkeypatch.setattr("elevenlabs.client.ElevenLabs", FakeClient)
    import io
    import wave
    data = io.BytesIO()
    with wave.open(data, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b"\x01\x00" * 3200)
    audio = ("request.wav", data.getvalue(), "audio/wav")
    assert briefing.transcribe(audio, "test-key-not-real") == "only show northwest Calgary"
    assert sent == [{"file": audio, "model_id": briefing.STT_MODEL_ID, "language_code": "eng",
                     "tag_audio_events": False, "diarize": False,
                     "request_options": {"max_retries": 0, "timeout_in_seconds": 30}}]
