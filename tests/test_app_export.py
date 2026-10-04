import copy
import io
import json
from pathlib import Path

import pandas as pd
import pytest

from app import export
from engine.agent import run

FIXTURE = json.loads((Path(__file__).resolve().parent.parent / "contract" / "sample_output.json").read_text())


@pytest.fixture(scope="module")
def planned():
    return run({"w_severity": 0.75, "w_trend": 0.5, "exclude_provincial": False},
               tune=False, constraints={"region": "NW", "budget": 5, "recent_weight": 3.0})


def test_csv_holds_only_the_shortlist_in_rank_order(planned):
    result = copy.deepcopy(planned)
    result["top20"].reverse()
    result["session"] = {"api_key": "DO_NOT_EXPORT"}
    data, name = export.shortlist_csv(result)
    assert name == "calgary_safety_shortlist_2025_NW_top5.csv"
    assert data.startswith(b"\xef\xbb\xbf")
    assert b"DO_NOT_EXPORT" not in data
    table = pd.read_csv(io.BytesIO(data))
    assert list(table.columns) == export.COLUMNS
    rows = export.shortlist_rows(result)
    assert [r["location_key"] for r in rows] == planned["plan"]["shortlist"]
    for column, field in {"Rank": "rank", "Location": "name", "Incidents": "incidents",
                          "Pedestrian or cyclist": "pedestrian_or_cyclist", "Count-only rank": "baseline_rank",
                          "Reason": "reason"}.items():
        assert table[column].tolist() == [r[field] for r in rows]
    for column, value in {"Area": "Northwest Calgary", "Locations to visit": 5, "Severity weight": 0.75,
                          "Trend weight": 0.5, "Jul-Dec multiplier": 3.0,
                          "Deerfoot and Stoney left out": False}.items():
        assert table[column].tolist() == [value] * 5
    assert table["Data"].str.contains("Open Government Licence").all()


def test_csv_round_trips_accents_quotes_and_commas(planned):
    result = copy.deepcopy(planned)
    first = next(r for r in result["top20"] if r["location_key"] == result["plan"]["shortlist"][0])
    first["name"] = 'École Avenue and "A, B" Road NW'
    table = pd.read_csv(io.BytesIO(export.shortlist_csv(result)[0]))
    assert table.loc[0, "Location"] == first["name"]


def test_csv_of_an_empty_shortlist_still_has_headers(planned):
    result = copy.deepcopy(planned)
    result["plan"]["shortlist"] = []
    data, name = export.shortlist_csv(result)
    table = pd.read_csv(io.BytesIO(data))
    assert table.empty and list(table.columns) == export.COLUMNS
    assert name.endswith("_top0.csv")


def test_csv_from_the_sample_file_says_so():
    data, name = export.shortlist_csv(FIXTURE)
    assert name.endswith("_sample.csv")
    assert b"Sample file, engine not connected" in data
    assert len(pd.read_csv(io.BytesIO(data))) == len(FIXTURE["top20"])
