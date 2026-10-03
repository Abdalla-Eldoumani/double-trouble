import copy
import importlib
import json
import re
import sys
import types
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import briefing, load  # noqa: E402

MAIN = str(ROOT / "app" / "main.py")
FIXTURE = json.loads((ROOT / "contract" / "sample_output.json").read_text())
TUNE_LABEL = "Let the agent tune it"
PLAY_LABEL = "Play the morning safety briefing"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    st.cache_data.clear()
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    yield
    st.cache_data.clear()


@pytest.fixture
def no_engine(monkeypatch):
    # A None entry makes the import raise even after the real engine exists.
    monkeypatch.setitem(sys.modules, "engine.agent", None)


@pytest.fixture
def fake_engine(monkeypatch):
    calls = []

    def run(weights=None, tune=True):
        calls.append({"weights": weights, "tune": tune})
        result = copy.deepcopy(FIXTURE)
        result["dataset"]["rows_used"] = 1234
        return result

    agent = types.ModuleType("engine.agent")
    agent.run = run
    package = types.ModuleType("engine")
    package.agent = agent
    monkeypatch.setitem(sys.modules, "engine", package)
    monkeypatch.setitem(sys.modules, "engine.agent", agent)
    return calls


def numbers_in(value):
    if isinstance(value, dict):
        return set().union(*(numbers_in(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(numbers_in(v) for v in value)) if value else set()
    if isinstance(value, bool):
        return set()
    if isinstance(value, (int, float)):
        return {str(value), f"{value:g}"}
    return set(re.findall(r"\d+(?:\.\d+)?", str(value)))


def run_app():
    at = AppTest.from_file(MAIN, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_modules_import():
    for name in ("app.load", "app.briefing"):
        importlib.import_module(name)


def test_get_result_falls_back_to_fixture(no_engine, monkeypatch):
    shown = []
    monkeypatch.setattr(load.st, "warning", shown.append)
    assert load.get_result() == FIXTURE
    assert shown == [load.FALLBACK_BANNER]


def test_get_result_uses_engine_when_present(fake_engine, monkeypatch):
    shown = []
    monkeypatch.setattr(load.st, "warning", shown.append)
    weights = {"w_severity": 0.2, "w_trend": 0.0, "exclude_provincial": False}
    assert load.get_result(weights, tune=False)["dataset"]["rows_used"] == 1234
    assert fake_engine == [{"weights": weights, "tune": False}]
    assert shown == []


def test_get_result_rejects_missing_fields(fake_engine, monkeypatch):
    broken = copy.deepcopy(FIXTURE)
    del broken["metrics"]["overlap_with_baseline"]
    del broken["top20"][0]["lat"]
    monkeypatch.setattr(sys.modules["engine.agent"], "run", lambda **kw: broken)
    with pytest.raises(load.ResultShapeError, match=r"metrics\.overlap_with_baseline.*top20\[0\]\.lat"):
        load.get_result()


def test_briefing_uses_only_result_values():
    script = briefing.build_script(FIXTURE)
    body = script.replace(briefing.FOOTER, "")
    assert set(re.findall(r"\d+(?:\.\d+)?", body)) <= numbers_in(FIXTURE)
    for row in sorted(FIXTURE["top20"], key=lambda r: r["rank"])[:5]:
        assert row["name"] in script

    changed = copy.deepcopy(FIXTURE)
    first = min(changed["top20"], key=lambda r: r["rank"])
    first["name"], first["incidents"] = "Test Street and Other Road", 4321
    changed_script = briefing.build_script(changed)
    assert "Test Street and Other Road, with 4321 incidents" in changed_script


def test_page_on_fixture_shows_banner_and_result_numbers(no_engine):
    at = run_app()
    assert load.FALLBACK_BANNER in [w.value for w in at.warning]
    data = FIXTURE["dataset"]
    assert any(f"{data['rows_used']:,} used" in md.value for md in at.markdown)
    overlap = f"{FIXTURE['metrics']['overlap_with_baseline']} of {len(FIXTURE['top20'])} the same"
    assert any(overlap in h.value for h in at.subheader)
    assert briefing.FOOTER in at.markdown[-1].value
    assert at.slider(key="w_severity").value == FIXTURE["weights"]["w_severity"]
    assert PLAY_LABEL not in [b.label for b in at.button]


def test_every_control_runs_against_engine(fake_engine):
    at = run_app()
    assert not at.warning
    assert any("1,234 used" in md.value for md in at.markdown)

    at.slider(key="w_severity").set_value(0.8).run()
    at.slider(key="w_trend").set_value(0.3).run()
    at.checkbox(key="exclude_provincial").check().run()
    assert not at.exception, at.exception
    assert fake_engine[-1] == {
        "weights": {"w_severity": 0.8, "w_trend": 0.3, "exclude_provincial": True},
        "tune": False,
    }

    button(at, TUNE_LABEL).click().run()
    assert not at.exception, at.exception
    assert fake_engine[-1]["tune"] is True
    assert at.slider(key="w_severity").value == FIXTURE["weights"]["w_severity"]
    assert at.slider(key="w_trend").value == FIXTURE["weights"]["w_trend"]
    assert at.checkbox(key="exclude_provincial").value == FIXTURE["weights"]["exclude_provincial"]
    assert any(it["note"] in str(t.value) for t in at.table for it in FIXTURE["agent_iterations"])


def test_briefing_audio_is_cached_per_script(no_engine, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")
    requests = []

    class FakeTTS:
        def convert(self, **kwargs):
            requests.append(kwargs)
            return iter([b"ID3", b"audio"])

    class FakeClient:
        def __init__(self, api_key):
            self.text_to_speech = FakeTTS()

    monkeypatch.setattr("elevenlabs.client.ElevenLabs", FakeClient)
    at = run_app()
    button(at, PLAY_LABEL).click().run()
    button(at, PLAY_LABEL).click().run()
    assert not at.exception, at.exception
    assert not at.error
    assert len(requests) == 1
    assert requests[0]["text"] == briefing.build_script(FIXTURE)
