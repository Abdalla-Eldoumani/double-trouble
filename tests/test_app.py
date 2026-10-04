import copy
import html
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

from app import briefing, load, planning, ui  # noqa: E402

MAIN = str(ROOT / "app" / "main.py")
FIXTURE = json.loads((ROOT / "contract" / "sample_output.json").read_text())
NUMBER = r"\d[\d,]*(?:\.\d+)?"


def consistent(result):
    # The fixture's count ranks and movers contradict each other; real engine output should not.
    result = copy.deepcopy(result)
    position = {r["location_key"]: i for i, r in enumerate(result["baseline"]["top20"], start=1)}
    for extra, r in enumerate(result["top20"], start=len(position) + 1):
        r["baseline_rank"] = position.get(r["location_key"], extra)
    for m in result["movers"]:
        m["to_rank"] = m["from_rank"] + 1
    return result
TUNE_LABEL = "Test ranking options automatically"
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

    def run(weights=None, tune=True, constraints=None):
        calls.append(copy.deepcopy({"weights": weights, "tune": tune, "constraints": constraints}))
        result = consistent(FIXTURE)
        result["dataset"]["rows_used"] = 1234
        result["weights"] = dict(FIXTURE["weights"] if tune else weights or planning.DEFAULT_WEIGHTS)
        c = {**planning.DEFAULT_CONSTRAINTS, **(constraints or {})}
        result["plan"] = {
            "constraints": c,
            "shortlist": [r["location_key"] for r in result["top20"][:c["budget"]]],
            "baseline_shortlist": [r["location_key"] for r in result["baseline"]["top20"][:c["budget"]]],
            "points_baseline": 10, "points_agent": 8, "points_total": 100,
        }
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
    return {n.replace(",", "") for n in re.findall(NUMBER, str(value))}


def run_app():
    at = AppTest.from_file(MAIN, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def page_text(at):
    return html.unescape(" ".join(md.value for md in at.markdown))


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
    assert fake_engine == [{"weights": weights, "tune": False, "constraints": None}]
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
    assert {n.replace(",", "") for n in re.findall(NUMBER, body)} <= numbers_in(FIXTURE)
    first = min(FIXTURE["top20"], key=lambda r: r["rank"])
    assert briefing.spoken_name(first["name"]) in script

    changed = copy.deepcopy(FIXTURE)
    first = min(changed["top20"], key=lambda r: r["rank"])
    first["name"], first["incidents"] = "Test Street and Other Road", 4321
    changed_script = briefing.build_script(changed)
    assert "Test Street and Other Road: 4321 reported crashes" in changed_script


def test_display_name_prefers_result_name_then_tidies_key():
    names = {"a & b ne": "A Street and B Avenue NE"}
    assert briefing.display_name(names, "a & b ne") == "A Street and B Avenue NE"
    assert briefing.display_name(names, "17 avenue & 84 street se") == "17 Avenue & 84 Street SE"


def test_consistency_warnings():
    assert load.consistency_warnings(consistent(FIXTURE)) == []
    warnings = load.consistency_warnings(FIXTURE)
    assert len(warnings) == 2
    assert "Eastbound Stoney Trail and Sarcee Trail NW" in warnings[0]
    assert "3 listed movers have the same rank" in warnings[1]

    wrong_overlap = consistent(FIXTURE)
    wrong_overlap["metrics"]["overlap_with_baseline"] = 20
    assert load.consistency_warnings(wrong_overlap) == [
        "Reported overlap is 20 but the two lists share 17 locations."]


def test_page_on_fixture_shows_banner_and_result_numbers(no_engine):
    at = run_app()
    assert load.FALLBACK_BANNER in [w.value for w in at.warning]
    data = FIXTURE["dataset"]
    assert any(f"{data['rows_used']:,} used" in md.value for md in at.markdown)
    overlap = f"Top-list overlap: {FIXTURE['metrics']['overlap_with_baseline']} of {len(FIXTURE['top20'])}"
    assert overlap in ui.validation(at.session_state["last_result"])
    assert briefing.FOOTER in at.markdown[-1].value
    assert at.slider(key="w_severity").value == FIXTURE["weights"]["w_severity"]
    assert PLAY_LABEL not in [b.label for b in at.button]
    assert at.selectbox(key="area").disabled
    assert at.slider(key="w_severity").disabled


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
        "constraints": planning.DEFAULT_CONSTRAINTS,
    }

    button(at, TUNE_LABEL).click().run()
    assert not at.exception, at.exception
    assert fake_engine[-1]["tune"] is True
    assert at.slider(key="w_severity").value == FIXTURE["weights"]["w_severity"]
    assert at.slider(key="w_trend").value == FIXTURE["weights"]["w_trend"]
    assert at.checkbox(key="exclude_provincial").value == FIXTURE["weights"]["exclude_provincial"]
    assert at.session_state["tuned"]["agent_iterations"] == FIXTURE["agent_iterations"]


def test_page_with_real_engine():
    from engine.agent import run

    default, tuned = run(tune=False), run(tune=True)
    at = run_app()
    assert not at.warning, [w.value for w in at.warning]
    assert any(f"{default['dataset']['rows_used']:,} used" in md.value for md in at.markdown)
    assert at.slider(key="w_severity").value == default["weights"]["w_severity"]
    assert at.checkbox(key="exclude_provincial").value == default["weights"]["exclude_provincial"]

    button(at, TUNE_LABEL).click().run()
    assert not at.exception, at.exception
    assert not at.warning, [w.value for w in at.warning]
    assert at.slider(key="w_severity").value == tuned["weights"]["w_severity"]
    assert at.slider(key="w_trend").value == tuned["weights"]["w_trend"]
    overlap = f"Top-list overlap: {tuned['metrics']['overlap_with_baseline']} of {len(tuned['top20'])}"
    page = page_text(at)
    assert overlap in ui.validation(at.session_state["last_result"])
    for row in tuned["top20"]:
        assert row["name"] in page
    for row in tuned["top20"][:3]:
        assert ui.location_reason(row, tuned) in page
    for it in tuned["agent_iterations"]:
        assert it in at.session_state["tuned"]["agent_iterations"]


def test_sample_ui_never_calls_speech_even_with_a_key(no_engine, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")
    def forbidden(*args, **kwargs):
        pytest.fail("UI phase must not invoke speech or inspect credentials")
    for name in ("api_key", "synthesize", "transcribe"):
        monkeypatch.setattr(briefing, name, forbidden)
    at = run_app()
    assert not at.exception, at.exception
    assert not at.error
    assert PLAY_LABEL not in [b.label for b in at.button]
    assert not at.get("audio_input") and not at.get("audio")


def test_slope_draws_one_line_per_location_and_escapes_names():
    result = consistent(FIXTURE)
    result["top20"][0]["name"] = "A & B <Street>"
    svg = ui.slope(result, lambda key: key)
    base = {b["location_key"] for b in result["baseline"]["top20"]}
    new = [r for r in result["top20"] if r["location_key"] not in base]
    assert svg.count("<path ") == len(base) + len(new)
    assert "A &amp; B &lt;Street&gt;" in svg and "<Street>" not in svg


def test_trace_marks_only_the_chosen_weights():
    tuned = copy.deepcopy(FIXTURE)
    tuned["weights"] = tuned["agent_iterations"][1]["weights"]
    out = ui.trace(tuned)
    assert out.count('<span class="tag">chosen</span>') == 1
    assert out.index("chosen") > out.index(tuned["agent_iterations"][0]["note"])
