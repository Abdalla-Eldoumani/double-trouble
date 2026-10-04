import html
import re
import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import briefing  # noqa: E402

MAIN = str(ROOT / "app" / "main.py")
EXAMPLE = "We can investigate five locations in northwest Calgary. Give recent crashes twice the importance."


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
    assert "Northwest Calgary" in reply and "Up to 5 locations" in reply
    assert "twice the importance" in reply and "Backtest" not in reply
    assert "Up to 5 locations in Northwest Calgary" in page_text(at)
    assert re.search(r"Top-list overlap: \d of 5", page_text(at))
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
    assert "Northeast Calgary" in reply
    assert "Up to 5 locations" in reply and "twice the importance" in reply
    assert all(name.endswith("NE") for name in shortlist_names(at))


def test_tune_respects_the_provincial_checkbox():
    at = run_app()
    at.checkbox(key="exclude_provincial").uncheck().run()
    next(b for b in at.button if b.label == "Test ranking options automatically").click().run()
    assert not at.exception, at.exception
    assert at.checkbox(key="exclude_provincial").value is False


def test_typed_ui_never_invokes_speech_when_a_key_is_set(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")
    def forbidden(*args, **kwargs):
        pytest.fail("UI phase must not invoke speech or inspect credentials")
    for name in ("api_key", "synthesize", "transcribe"):
        monkeypatch.setattr(briefing, name, forbidden)
    at = run_app()
    reply = ask(at, EXAMPLE)
    assert "Updated:" in reply
    at.selectbox(key="area").select("NE").run()
    next(b for b in at.button if b.label == "Test ranking options automatically").click().run()
    assert not at.exception
    assert not at.get("audio_input") and not at.get("audio")
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
