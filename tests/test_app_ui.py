"""UI-phase behavior checks against the existing engine and real Streamlit widgets."""
import copy
import html
import json
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app import export, planning, ui
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
    assert at.selectbox(key="area").value == planning.ui_region(plan["constraints"]["region"])
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
    summaries = [node.proto.body for node in at.get("html")
                 if 'class="dt recommendation-summary"' in node.proto.body]
    assert len(summaries) == 1 and summaries[0] == ui.recommendation_summary(result)
    assert summaries[0].count("<li>") == min(3, len(rows))
    assert len(at.download_button) == 1
    assert at.download_button(key="export_shortlist").label == "Export investigation shortlist"
    assert at.download_button(key="export_shortlist").disabled == (not rows)
    expected_changes = ui.changed_locations(result)
    if expected_changes:
        changes = next(md.value for md in at.markdown if 'class="dt ranking-changes"' in md.value)
        assert changes.count('class="ranking-change"') == len(expected_changes)
        for mover in expected_changes:
            assert f'#{mover["from_rank"]} → #{mover["to_rank"]}' in changes
    else:
        assert ui.NO_MOVEMENT in text(at)
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
    assert [e.label for e in at.expander] == ["Advanced controls", "About the data and attribution"]
    assert all(not e.proto.expanded for e in at.expander)
    assert_consistent(at)
    ask(at, EXAMPLE)
    at.slider(key="w_severity").set_value(0.65).run()
    at.checkbox(key="exclude_provincial").uncheck().run()
    click(at, "Reset settings")
    assert at.session_state["settings"] == {"weights": DEFAULT_WEIGHTS, "constraints": DEFAULT_CONSTRAINTS}
    assert_consistent(at)


def test_summary_and_download_update_with_all_planning_inputs(monkeypatch):
    downloads = []
    original_download = st.download_button

    def capture(*args, **kwargs):
        downloads.append(dict(kwargs))
        return original_download(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)
    at = app()

    def check():
        import io

        result = at.session_state["last_result"]
        data = pd.read_csv(io.BytesIO(downloads[-1]["data"]))
        rows = ui.recommended_rows(result)
        assert data["Location"].tolist() == [r["name"] for r in rows]
        assert data["Rank"].tolist() == [r["rank"] for r in rows]
        assert data["Requested investigation capacity"].tolist() == [at.number_input(key="capacity").value] * len(rows)
        assert data["Deerfoot/Stoney excluded"].tolist() == [at.checkbox(key="exclude_provincial").value] * len(rows)
        assert data["Incident-indicator weight"].tolist() == [at.slider(key="w_severity").value] * len(rows)
        assert data["Increasing-activity weight"].tolist() == [at.slider(key="w_trend").value] * len(rows)
        assert data["Recent-crash multiplier"].tolist() == [at.slider(key="recent_weight").value] * len(rows)
        assert downloads[-1]["file_name"] == export.shortlist_csv(result)[1]
        assert_consistent(at)

    check()
    ask(at, EXAMPLE)
    check()
    at.selectbox(key="area").select("NE").run()
    check()
    at.selectbox(key="priorities").select("Pedestrians and cyclists").run()
    check()
    at.number_input(key="capacity").set_value(10).run()
    check()
    at.checkbox(key="exclude_provincial").uncheck().run()
    check()
    click(at, "Test ranking options automatically")
    check()
    assert at.expander[0].label == "Advanced controls" and not at.expander[0].proto.expanded


def test_summary_is_visible_before_map_and_sliders_use_honest_labels():
    at = app()
    nodes = list(at.main)
    summary_pos = next(i for i, node in enumerate(nodes) if node.type == "html" and 'class="dt recommendation-summary"' in node.proto.body)
    export_pos = next(i for i, node in enumerate(nodes) if node.type == "download_button")
    map_pos = next(i for i, node in enumerate(nodes) if node.type == "deck_gl_json_chart")
    assert summary_pos < export_pos < map_pos
    assert at.slider(key="w_severity").label == "Give more priority to pedestrian/cyclist and other crash indicators"
    assert at.slider(key="w_trend").label == "Give more priority to locations with increasing crashes"
    assert at.slider(key="recent_weight").label == "Give more priority to recent crashes"
    captions = " ".join(c.value for c in at.caption)
    assert "do not exclude other crash types" in captions
    assert "not confirmed injury severity" in captions
    assert "July–December 2025" in at.slider(key="recent_weight").help


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
    assert at.selectbox(key="area").value == "ALL"
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
    assert any('class="dt agent-result"' in node.proto.body for node in at.get("html"))
    assert_consistent(at)
    ask(at, "City roads only.")
    result = at.session_state["last_result"]
    assert all(not any(road in r["location_key"] for road in ("deerfoot", "stoney"))
               for r in result["top20"] + result["baseline"]["top20"])
    assert at.session_state["tuned"] == tuned
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
    ped = row["pedestrian_or_cyclist"]
    assert (f"{ped} pedestrian or cyclist" if ped else "no pedestrian or cyclist reports") in ui.location_reason(row, result)


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
        "location_key": "a & b ne", "name": "A and B NE", "display_name": "A and B NE", "latitude": 51.05,
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
    result = at.session_state["last_result"]
    assert "not available (no evaluation-period proxy points)" in ui.validation(result)
    assert_consistent(at)


def test_empty_evaluation_has_no_division_error():
    df, _ = load()
    df = add_points(df)
    share, caught, total = backtest(df, ("2025-01-01", "2025-09-01"),
                                   ("2025-09-01", "2026-01-01"), DEFAULT_WEIGHTS, keep=set())
    assert (share, caught, total) == (0.0, 0, 0)


@pytest.mark.parametrize("area,region", [("ALL", None), ("NW", "NW"), ("NE", "NE"), ("SW", "SW"), ("SE", "SE")])
def test_area_boundary_round_trip(area, region):
    assert planning.engine_region(area) == region
    assert planning.ui_region(region) == area
    with pytest.raises(ValueError):
        planning.engine_region(None)


def test_all_calgary_persists_across_every_planning_rerun(monkeypatch):
    downloads = []
    original = st.download_button

    def capture(*args, **kwargs):
        downloads.append(kwargs["data"])
        return original(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)
    at = app()
    at.selectbox(key="area").select("NW").run()
    at.selectbox(key="area").select("ALL").run()

    def check():
        assert not at.exception
        assert at.selectbox(key="area").value == "ALL"
        assert at.session_state["settings"]["constraints"]["region"] is None
        # Verify the serialized value the browser receives, not just Python state.
        assert at.selectbox(key="area").proto.options[0] == "All Calgary"
        if at.selectbox(key="area").proto.set_value:
            assert at.selectbox(key="area").proto.raw_value == "All Calgary"
        assert_consistent(at)

    check()
    at.run()  # unrelated rerun after focus leaves the widget
    check()
    at.number_input(key="capacity").set_value(5).run()
    check()
    at.selectbox(key="priorities").select("Pedestrians and cyclists").run()
    check()
    for key, value in [("w_severity", .65), ("w_trend", .35), ("recent_weight", 3.0)]:
        at.slider(key=key).set_value(value).run()
        check()
    click(at, "Test ranking options automatically")
    check()
    ask(at, "Top 10 across the whole city.")
    check()
    before_settings = copy.deepcopy(at.session_state["settings"])
    before_result = copy.deepcopy(at.session_state["last_result"])
    before_reply = copy.deepcopy(at.session_state["reply"])
    before_csv = downloads[-1]
    at.toggle(key="dark_mode").set_value(True).run()
    check()
    assert at.session_state["dark_mode"] is True
    assert at.session_state["settings"] == before_settings
    assert at.session_state["last_result"] == before_result
    assert at.session_state["reply"] == before_reply
    assert downloads[-1] == before_csv
    at.run()  # export uses on_click="ignore"; this also checks a rerun cannot clear area
    check()
    assert downloads[-1] == before_csv
    click(at, "Reset settings")
    check()
    assert at.session_state["dark_mode"] is True
    assert at.session_state["settings"] == {"weights": DEFAULT_WEIGHTS, "constraints": DEFAULT_CONSTRAINTS}
    at.toggle(key="dark_mode").set_value(False).run()
    check()


def test_theme_retains_quadrant_planner_and_tuning_state():
    at = app()
    assert at.toggle(key="dark_mode").value is False
    ask(at, EXAMPLE)
    click(at, "Test ranking options automatically")
    saved = {k: copy.deepcopy(at.session_state[k]) for k in ("settings", "tuned", "planner_text", "tuning_confirmation", "last_result")}
    csv_before = export.shortlist_csv(saved["last_result"])
    at.toggle(key="dark_mode").set_value(True).run()
    for key, value in saved.items():
        assert at.session_state[key] == value
    assert at.selectbox(key="area").value == "NW"
    assert export.shortlist_csv(at.session_state["last_result"]) == csv_before
    ask(at, "City roads only.")
    assert at.toggle(key="dark_mode").value is True
    assert_consistent(at)


def test_stale_presentation_refresh_preserves_applied_plan(monkeypatch):
    at = app()
    ask(at, EXAMPLE)
    at.toggle(key="dark_mode").set_value(True).run()
    saved = {key: copy.deepcopy(at.session_state[key])
             for key in ("settings", "last_result", "reply", "planner_text", "dark_mode")}
    # Simulate the observed long-lived server retaining an older presentation
    # module after the script has changed. It must render the current summary
    # again without losing the user's plan or recomputing different results.
    monkeypatch.setattr(ui, "_source_mtime_ns", -1, raising=False)
    monkeypatch.setattr(ui, "recommendation_summary", lambda result: "")
    monkeypatch.setattr(ui, "hero", lambda *args: "Old cached presentation")
    at.run()
    for key, value in saved.items():
        assert at.session_state[key] == value
    assert "Old cached presentation" not in text(at)
    assert_consistent(at)


def test_membership_and_order_messages_do_not_depend_on_mover_metadata():
    result = run(tune=False, constraints={"budget": 5})
    assert ui.recommendation_change(result) == ui.NO_MOVEMENT
    result["plan"]["baseline_shortlist"] = list(reversed(result["plan"]["shortlist"]))
    assert ui.recommendation_change(result) == "Your selected priorities recommend the same locations in a different order."
    assert ui.NO_MOVEMENT not in ui.ranking_changes(result, lambda k: k)
    result["plan"]["baseline_shortlist"] = result["plan"]["shortlist"][:-1] + ["outside location"]
    output = ui.ranking_changes(result, lambda k: k)
    assert "1 entered and 1 left the shortlist" in output
    assert ui.NO_MOVEMENT not in output
    assert "experiment" not in output and "test ranking" not in output


def test_rank_explanations_lead_with_actual_applied_signals():
    result = run({"w_severity": 1.0, "w_trend": 1.0}, tune=False, constraints={"budget": 5, "recent_weight": 2})
    output = ui.ranking_changes(result, lambda k: k)
    assert ui.PRIORITY_NOTE in output
    assert output.count('class="ranking-change"') <= 3
    assert "Outside the current shortlist." in output
    assert output.index('<p>') < output.index('class="rank-note"')
    for mover in ui.changed_locations(result):
        if mover["multi_vehicle"]:
            assert f'{mover["multi_vehicle"]} multi-vehicle reports' in output
        assert f'{mover["late"]} July–December reports receive 2× importance' in output
    assert "dedicated" not in output


def test_no_dense_validation_or_decorative_section_numbers_in_presentation():
    at = app()
    click(at, "Test ranking options automatically")
    page = text(at)
    assert "How your priorities affect the recommendations" in page
    assert "What changed from ranking by crash totals?" not in page
    assert "How we tested the ranking" not in page
    assert 'class="sec-no"' not in page
    assert 'class="dt trace"' not in page and 'class="dt validation"' not in page
    assert not at.dataframe
    result = at.session_state["last_result"]
    assert len(result["agent_iterations"]) == 15
    assert result["metrics"] and result["baseline"] and result["plan"]["points_total"]


def test_summary_uses_only_current_counts_and_escapes_names():
    result = run(tune=False, constraints={"region": "NE", "budget": 5})
    result["top20"][0]["name"] = '<unsafe & location>'
    output = ui.recommendation_summary(result)
    assert "5 locations recommended in Northeast Calgary" in output
    assert "Applied priorities: Crash totals" in output
    assert "Deerfoot and Stoney excluded by location name" in output
    assert '&lt;unsafe &amp; location&gt;' in output
    assert "before area and road filters" in output
    assert 'role="region"' in output and '<section' not in output


def test_agent_button_runs_the_weight_search_and_states_what_it_kept():
    at = app()
    click(at, "Let the agent pick the weights")
    result = at.session_state["last_result"]
    assert len(result["agent_iterations"]) == 15
    panel = next(node.proto.body for node in at.get("html") if 'class="dt agent-result"' in node.proto.body)
    assert panel_reports_result(panel, result)
    assert_consistent(at)


def panel_reports_result(panel, result):
    w = result["weights"]
    return (f'{w["w_severity"]:.2f}' in panel and f'{w["w_trend"]:.2f}' in panel
            and f'{len(result["agent_iterations"])} weight options' in panel)


def test_counts_are_pluralised_and_zero_reads_as_none():
    row = {"incidents": 1, "pedestrian_or_cyclist": 0, "multi_vehicle": 1, "multiple_lanes": 2}
    reason = ui.location_reason(row)
    assert "Recorded 1 crash, with no pedestrian or cyclist reports." in reason
    assert "1 report involving several vehicles" in reason and "2 reports of more than one lane blocked" in reason
    assert "1 reports" not in reason and "0 reports" not in reason
