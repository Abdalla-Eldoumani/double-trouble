"""UI-phase behavior checks against the existing engine and real Streamlit widgets."""
import copy
import html
import json
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app import planning, ui
from engine.agent import DEFAULT_CONSTRAINTS, DEFAULT_WEIGHTS, backtest, run
from engine.data import load
from engine.planner import parse
from engine.score import add_points, baseline, signals

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "We can investigate five locations in northwest Calgary. Give recent crashes twice the importance."


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    st.cache_data.clear()
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    yield
    st.cache_data.clear()


def app():
    at = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=60).run()
    assert not at.exception
    return at


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, at.exception


def ask(at, text):
    at.text_input(key="planner_text").set_value(text)
    click(at, "Update recommendations")


def text(at):
    return html.unescape(" ".join(md.value for md in at.markdown))


def assert_consistent(at):
    result = at.session_state["last_result"]
    plan = result["plan"]
    rows = ui.recommended_rows(result)
    assert at.session_state["settings"] == planning.from_result(result)
    assert at.selectbox(key="area").value == plan["constraints"]["region"]
    assert at.number_input(key="capacity").value == plan["constraints"]["budget"]
    assert at.selectbox(key="priorities").value == planning.preset_name(planning.from_result(result))
    for name in ("w_severity", "w_trend"):
        assert at.slider(key=name).value == result["weights"][name]
    assert at.slider(key="recent_weight").value == plan["constraints"]["recent_weight"]
    assert len(rows) == len(plan["shortlist"])
    beyond = len(set(plan["shortlist"]) - set(plan["baseline_shortlist"]))
    figures = ui.figures(result)
    assert f'Locations recommended</div><div class="fig-value">{len(rows)}</div>' in figures
    assert f'Selected beyond crash totals</div><div class="fig-value">{beyond}</div>' in figures
    assert figures in " ".join(md.value for md in at.markdown)
    charts = at.get("deck_gl_json_chart")
    if rows:
        assert len(charts) == 1
        deck = json.loads(charts[0].proto.json)
        assert {r["location_key"] for r in deck["layers"][0]["data"]} == set(plan["shortlist"])
        ledger = next(md.value for md in at.markdown if 'class="dt ledger"' in md.value)
        assert ledger.count('class="lg-name"') == len(rows)
    else:
        assert not charts


def test_opening_defaults_and_reset_are_truthful():
    assert planning.DEFAULT_WEIGHTS == DEFAULT_WEIGHTS
    assert planning.DEFAULT_CONSTRAINTS == DEFAULT_CONSTRAINTS
    at = app()
    assert at.selectbox(key="priorities").value == "Crash totals"
    assert at.session_state["last_result"]["agent_iterations"][0]["note"].startswith("given weights, not tuned")
    assert "Where should Calgary focus its next" in text(at)
    assert "Why these locations are priorities" in text(at)
    assert [e.label for e in at.expander] == ["Advanced controls", "How we tested the ranking", "Briefing summary", "About the data"]
    assert all(not e.proto.expanded for e in at.expander)
    assert_consistent(at)
    ask(at, EXAMPLE)
    at.slider(key="w_severity").set_value(0.65).run()
    at.checkbox(key="exclude_provincial").uncheck().run()
    click(at, "Reset settings")
    assert at.session_state["settings"] == {"weights": DEFAULT_WEIGHTS, "constraints": DEFAULT_CONSTRAINTS}
    assert_consistent(at)


def test_control_and_planner_changes_retain_other_fields():
    at = app()
    ask(at, EXAMPLE)
    assert_consistent(at)
    at.slider(key="w_severity").set_value(0.65).run()
    at.slider(key="w_trend").set_value(0.35).run()
    at.selectbox(key="area").select("NE").run()
    assert at.session_state["settings"]["constraints"] == {"region": "NE", "budget": 5, "recent_weight": 2.0}
    assert at.selectbox(key="priorities").value == "Custom priorities"
    assert at.slider(key="w_severity").value == 0.65
    ask(at, "Top 10 across the whole city.")
    assert at.selectbox(key="area").value is None
    assert at.number_input(key="capacity").value == 10
    assert at.slider(key="w_severity").value == 0.65
    assert at.slider(key="w_trend").value == 0.35
    assert at.slider(key="recent_weight").value == 2
    assert_consistent(at)


@pytest.mark.parametrize("capacity", [5, 10, 20])
def test_capacity_controls_map_list_and_kpis(capacity):
    at = app()
    at.number_input(key="capacity").set_value(capacity).run()
    assert len(ui.recommended_rows(at.session_state["last_result"])) == capacity
    assert_consistent(at)


@pytest.mark.parametrize("preset", list(planning.PRESETS))
def test_presets_keep_area_capacity_and_road_scope(preset):
    at = app()
    ask(at, EXAMPLE)
    at.checkbox(key="exclude_provincial").uncheck().run()
    at.selectbox(key="priorities").select(preset).run()
    s, t, r = planning.PRESETS[preset]
    assert at.session_state["settings"] == {
        "weights": {"w_severity": s, "w_trend": t, "exclude_provincial": False},
        "constraints": {"budget": 5, "region": "NW", "recent_weight": r},
    }
    assert_consistent(at)


def test_road_scope_and_tuning_preserve_constraints():
    at = app()
    ask(at, EXAMPLE)
    at.checkbox(key="exclude_provincial").uncheck().run()
    click(at, "Test ranking options automatically")
    tuned = at.session_state["tuned"]
    assert tuned["weights"]["exclude_provincial"] is False
    assert tuned["plan"]["constraints"] == {"region": "NW", "budget": 5, "recent_weight": 2.0}
    assert len(tuned["agent_iterations"]) == 15
    assert at.success
    assert_consistent(at)
    ask(at, "City roads only.")
    result = at.session_state["last_result"]
    assert all(not any(road in r["location_key"] for road in ("deerfoot", "stoney"))
               for r in result["top20"] + result["baseline"]["top20"])
    assert "previous search" in " ".join(c.value for c in at.caption)
    assert_consistent(at)


def test_unrecognized_request_preserves_settings_and_rankings():
    at = app()
    ask(at, EXAMPLE)
    before = copy.deepcopy(at.session_state["last_result"])
    ask(at, "What is the weather like?")
    assert at.session_state["last_result"] == before
    assert at.session_state["reply"]["text"].startswith("Settings unchanged.")
    assert_consistent(at)


@pytest.mark.parametrize("phrase", [EXAMPLE, "Focus on pedestrians and cyclists.", "Top 10 across the whole city.", "City roads only."])
def test_visible_requests_are_supported(phrase):
    parsed = parse(phrase)
    assert parsed["weights"] or parsed["constraints"]
    if phrase == EXAMPLE:
        assert parsed["constraints"] == {"region": "NW", "budget": 5, "recent_weight": 2.0}


def test_baseline_comparison_matches_eligibility_capacity_and_period():
    weights = {"w_severity": 0.65, "w_trend": 0.35, "exclude_provincial": True}
    result = run(weights, tune=False, constraints={"region": "NW", "budget": 5, "recent_weight": 3.0})
    df, _ = load()
    keep = set(df.groupby("location_key")["quadrant"].agg(lambda s: s.mode().iloc[0]).loc[lambda q: q == "NW"].index)
    expected = baseline(signals(add_points(df), "2025-01-01", "2026-01-01"), True, keep).head(5)
    assert result["plan"]["baseline_shortlist"] == list(expected.index)
    assert result["plan"]["overlap"] == len(set(result["plan"]["shortlist"]) & set(expected.index))


def test_unchanged_rankings_explain_the_recommended_locations():
    result = run(tune=False, constraints={"budget": 5})
    assert not result["movers"]
    reasons = ui.movers(result, lambda k: k)
    assert "Recorded" in reasons and "Selected by total reported crashes" in reasons
    assert "There are no" not in reasons
    row = result["top20"][0]
    assert row["early"] + row["late"] == row["incidents"]
    assert str(row["pedestrian_or_cyclist"]) in ui.location_reason(row, result)


def test_validation_preserves_negative_values_and_units():
    result = run({"w_severity": 1.0, "w_trend": 1.0}, tune=False, constraints={"budget": 5})
    # Explicit unfavorable values check presentation independently of dataset changes.
    result["plan"].update(points_baseline=20, points_agent=10, points_total=100)
    result["metrics"].update(backtest_baseline=0.2, backtest_agent=0.1, check_baseline=0.3, check_agent=0.1)
    output = ui.validation(result)
    assert "-10.00 percentage points" in output
    assert "-10 proxy points" in output
    assert "-50.00%" in output
    assert "-20.00 percentage points" in output
    assert "not an independent holdout" in output
    assert "not injury counts" in output


@pytest.mark.parametrize("area, expected", [("NE", 1), ("NW", 0)])
def test_sparse_and_empty_results_are_rendered_truthfully(monkeypatch, area, expected):
    import engine.agent as agent
    df = pd.DataFrame([{
        "location_key": "a & b ne", "name": "A and B NE", "latitude": 51.05,
        "longitude": -114.0, "quadrant": "NE", "start_dt": pd.Timestamp("2025-02-01"),
        "description": "two vehicle incident.",
    }])
    info = {"rows_used": 1, "rows_loaded": 1, "rows_dropped": 0, "source": "Synthetic test data", "drop_reason": "none"}
    monkeypatch.setattr(agent, "load", lambda: (df.copy(), info))
    at = app()
    at.selectbox(key="area").select(area).run()
    assert not at.exception, at.exception
    assert len(ui.recommended_rows(at.session_state["last_result"])) == expected
    assert f"{expected} locations qualify" in " ".join(i.value for i in at.info)
    assert "not available (no evaluation-period proxy points)" in text(at)
    assert_consistent(at)


def test_empty_evaluation_has_no_division_error():
    df, _ = load()
    df = add_points(df)
    share, caught, total = backtest(df, ("2025-01-01", "2025-09-01"),
                                   ("2025-09-01", "2026-01-01"), DEFAULT_WEIGHTS, keep=set())
    assert (share, caught, total) == (0.0, 0, 0)
