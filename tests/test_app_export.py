"""Focused CSV and recommendation presentation checks, without external services."""

import copy
import io
import json
from pathlib import Path

import pandas as pd
import pytest

from app import briefing, export, planning, ui
from engine.agent import run
from engine.data import load
from engine.score import add_points, signals


@pytest.fixture(scope="module")
def weighted():
    return run({"w_severity": 0.75, "w_trend": 0.5, "exclude_provincial": False},
               tune=False, constraints={"region": "NW", "budget": 5, "recent_weight": 3.0})


def test_csv_exports_only_applied_shortlist_in_rank_order(weighted):
    # Scrambling input ensures CSV ordering follows ranks, not incidental row order.
    result = copy.deepcopy(weighted)
    result["top20"].reverse()
    result["internal_session_data"] = {"api_key": "DO_NOT_EXPORT"}
    data, filename = export.shortlist_csv(result)
    assert filename == "calgary_investigation_shortlist_2025_NW_top5.csv"
    assert data.startswith(b"\xef\xbb\xbf")
    assert b"DO_NOT_EXPORT" not in data and b"internal_session_data" not in data
    table = pd.read_csv(io.BytesIO(data))
    assert list(table.columns) == export.COLUMNS
    rows = ui.recommended_rows(result)
    assert len(table) == 5
    expected_fields = {
        "Rank": "rank", "Location": "name", "Latitude": "lat", "Longitude": "lon",
        "Reported crash count": "incidents", "Pedestrian/cyclist report count": "pedestrian_or_cyclist",
        "Rank by total crashes": "baseline_rank",
    }
    for label, field in expected_fields.items():
        assert table[label].tolist() == [row[field] for row in rows]
    assert table["Selection reason"].tolist() == [ui.location_reason(row, result) for row in rows]
    for label, expected in {
        "Selected area": "Northwest Calgary", "Requested investigation capacity": 5,
        "Actual shortlist size": 5, "Incident-indicator weight": 0.75,
        "Increasing-activity weight": 0.5, "Recent-crash multiplier": 3.0,
        "Deerfoot/Stoney excluded": False, "Data period": "January–December 2025",
        "Safety priorities": planning.priority_description(planning.from_result(result)),
    }.items():
        assert table[label].tolist() == [expected] * 5
    for label in ("Latitude", "Longitude", "Incident-indicator weight", "Increasing-activity weight", "Recent-crash multiplier"):
        assert pd.api.types.is_numeric_dtype(table[label])
    for label in ("Rank", "Reported crash count", "Pedestrian/cyclist report count", "Rank by total crashes", "Requested investigation capacity", "Actual shortlist size"):
        assert pd.api.types.is_integer_dtype(table[label])
    assert pd.api.types.is_bool_dtype(table["Deerfoot/Stoney excluded"])


def test_csv_round_trips_unicode_quotes_and_commas(weighted):
    result = copy.deepcopy(weighted)
    result["top20"][0]["name"] = 'École Avenue and "A, B" Road – NW'
    table = pd.read_csv(io.BytesIO(export.shortlist_csv(result)[0]))
    assert table.loc[0, "Location"] == result["top20"][0]["name"]


def test_csv_labels_actual_size_separately_from_capacity(weighted):
    result = copy.deepcopy(weighted)
    result["plan"]["constraints"]["budget"] = 20
    result["plan"]["shortlist"] = [result["top20"][0]["location_key"]]
    table = pd.read_csv(io.BytesIO(export.shortlist_csv(result)[0]))
    assert len(table) == 1
    assert table.loc[0, "Requested investigation capacity"] == 20
    assert table.loc[0, "Actual shortlist size"] == 1
    assert export.shortlist_csv(result)[1].endswith("NW_top1.csv")
    result["plan"]["shortlist"] = []
    table = pd.read_csv(io.BytesIO(export.shortlist_csv(result)[0]))
    assert table.empty and list(table.columns) == export.COLUMNS
    assert "No locations qualify" in ui.recommendation_summary(result)


def test_summary_uses_three_leaders_and_distinguishes_dataset_scope(weighted):
    summary = ui.recommendation_summary(weighted)
    assert summary.count("<li>") == 3
    assert "5 locations recommended in Northwest Calgary" in summary
    assert "Deerfoot and Stoney included" in summary
    assert "Custom priorities" in summary and "weighted 3×" in summary
    assert "full cleaned dataset" in summary
    for row in weighted["top20"][:3]:
        assert ui.esc(row["name"]) in summary
        assert f"{row['incidents']} reported crashes" in summary
        assert f"January–June: {row['early']} crashes; July–December: {row['late']}" in summary
    assert ui.esc(weighted["top20"][3]["name"]) not in summary


@pytest.mark.parametrize("weights,recent", [({"w_severity": 1.0}, 1.0),
                                          ({"w_trend": 1.0}, 1.0), ({}, 3.0)])
def test_movers_are_actual_changes_include_dropouts_and_use_applied_criteria(weights, recent):
    result = run(weights, tune=False, constraints={"recent_weight": recent, "budget": 5})
    df, _ = load()
    observed = signals(add_points(df), "2025-01-01", "2026-01-01")
    names = briefing.location_names(result)
    output = ui.ranking_changes(result, lambda k: briefing.display_name(names, k))
    movers = result["movers"]
    assert len(movers) == 3
    assert output.count('class="ranking-change"') == len(movers)
    for mover in movers:
        assert mover["from_rank"] != mover["to_rank"]
        assert ui.esc(names[mover["location_key"]]) in output
        assert f'#{mover["from_rank"]} → #{mover["to_rank"]}' in output
        assert ("Moved higher" if mover["direction"] == "up" else "Moved lower") in output
        for field in ("incidents", "pedestrian_or_cyclist", "multi_vehicle", "multiple_lanes", "early", "late"):
            assert mover[field] == observed.at[mover["location_key"], field]
        assert ui.esc(ui.priority_effect(mover, result)) in output
    # The real engine's biggest changes extend beyond the current five leaders.
    assert {m["location_key"] for m in movers} != {r["location_key"] for r in result["top20"][:3]}
    if not result["weights"]["w_severity"]:
        assert "multi-vehicle" not in output and "blocked-lane" not in output
    if not result["weights"]["w_trend"]:
        assert "increasing crash activity" not in output
    if recent == 1:
        assert "reports weighted" not in output
    if recent == 3:
        assert any(m["from_rank"] <= 20 and m["to_rank"] > 20 for m in movers)


def test_movers_show_only_genuine_changes_and_do_not_invent_sample_evidence(weighted):
    result = copy.deepcopy(weighted)
    unchanged = {**result["movers"][0], "to_rank": result["movers"][0]["from_rank"]}
    result["movers"] = [unchanged, result["movers"][1]]
    assert ui.changed_locations(result) == [result["movers"][1]]
    output = ui.ranking_changes(result, lambda k: k)
    assert output.count('class="ranking-change"') == 1
    result["movers"] = []
    assert ui.NO_MOVEMENT not in ui.ranking_changes(result, lambda k: k)
    assert "entered and" in ui.ranking_changes(result, lambda k: k)
    fixture = json.loads((Path(__file__).resolve().parent.parent / "contract/sample_output.json").read_text())
    # The fixture lists unchanged movers; filter these while retaining its existing warnings.
    assert "No consistent ranking-change details" in ui.ranking_changes(fixture, lambda k: k)
    data, filename = export.shortlist_csv(fixture)
    assert "_sample.csv" in filename
    assert b"Sample output (engine not connected)" in data
