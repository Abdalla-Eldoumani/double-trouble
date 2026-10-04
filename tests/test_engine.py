import json
import time
from pathlib import Path

import pandas as pd
import pytest

from engine.agent import run
from engine.data import CSV, load, location_key, merge_quadrant_variants

FIXTURE = json.loads((Path(__file__).resolve().parent.parent / "contract" / "sample_output.json").read_text())


@pytest.fixture(scope="module")
def result():
    return run()


def same_shape(expected, actual, path="$"):
    """Every key in the fixture is present in the output with the same JSON type."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        for k, v in expected.items():
            if k.startswith("_"):
                continue
            assert k in actual, f"{path}.{k} missing"
            same_shape(v, actual[k], f"{path}.{k}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), path
        for i, item in enumerate(actual):
            same_shape(expected[0], item, f"{path}[{i}]")
    elif isinstance(expected, bool):
        assert isinstance(actual, bool), path
    elif isinstance(expected, (int, float)):
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool), path
    else:
        assert isinstance(actual, type(expected)), f"{path}: {type(actual).__name__}"


def test_output_matches_contract(result):
    same_shape(FIXTURE, result)
    json.dumps(result)


def test_given_weights_match_contract_too():
    same_shape(FIXTURE, run({"w_severity": 1.0, "exclude_provincial": True}, tune=False))


def test_top20_is_20_unique_keys(result):
    keys = [r["location_key"] for r in result["top20"]]
    assert len(keys) == 20 and len(set(keys)) == 20
    assert [r["rank"] for r in result["top20"]] == list(range(1, 21))


def test_baseline_is_true_count_only_order(result):
    raw = pd.read_csv(CSV)
    first = raw["description"].str.lower().str.replace(r"\s+", " ", regex=True).str.split(".", n=1).str[0]
    non_crash = first.str.contains(r"^\s*(?:stalled vehicle|traffic signal|power outage|road work|water main"
                                   r"|severe weather|hazardous road|lrt gates|due to road conditions|road closed"
                                   r"|(?:the )?road is closed|the \w+ ramp is closed|cfd )|police|oversized load")
    kept = raw.loc[~non_crash]
    keys = merge_quadrant_variants(kept.assign(location_key=kept["incident_info"].map(location_key)))
    counts = keys.value_counts()
    counts = counts[~counts.index.str.contains("deerfoot|stoney")]
    base = result["baseline"]["top20"]
    assert [b["incidents"] for b in base] == counts.head(20).tolist()
    for b in base:
        assert counts[b["location_key"]] == b["incidents"]


def test_quadrant_variants_of_one_crossing_merge_but_distant_ones_do_not():
    df, _ = load()
    keys = set(df["location_key"])
    assert "glenmore trail & macleod trail sw" in keys
    assert not keys & {"glenmore trail & macleod trail s", "glenmore trail & macleod trail se"}
    frame = pd.DataFrame({
        "location_key": ["a & b se"] * 3 + ["a & b sw", "a & b s"],
        "latitude": [51.0, 51.0, 51.0, 51.0, 51.001],
        "longitude": [-114.0, -114.0, -114.0, -114.2, -114.0],
    })
    assert merge_quadrant_variants(frame).tolist() == ["a & b se"] * 3 + ["a & b sw", "a & b se"]


def test_feed_misspellings_join_their_location():
    assert location_key("Macloed Trail and 11 Avenue SE") == "11 avenue & macleod trail se"
    assert location_key("Calffrobe bridge and Deerfoot Trail SE") == "calf robe bridge & deerfoot trail se"
    assert location_key("Country Hills Boulevard and Deer Foot Trail NE") == "country hills boulevard & deerfoot trail ne"
    assert location_key("Crowchild SW and Glenmore Trail") == location_key("Crowchild Trail and Glenmore Trail")


@pytest.mark.parametrize("name, key", [
    ("Southbound Deerfoot Trail approaching Glenmore Trail SE", "deerfoot trail & glenmore trail se"),
    (" Glenmore Trail and  Deerfoot Trail SE ", "deerfoot trail & glenmore trail se"),
    ("Southbound Deerfoot Trail ramp to 16 Avenue NE", "16 avenue & deerfoot trail ne"),
    ("Soutbound Deerfoot Trail exit to McKnight Blvd NE", "deerfoot trail & mcknight boulevard ne"),
    ("Westbound Stoney Trail after McKenzie Lake Boulevard SE", "mckenzie lake boulevard & stoney trail se"),
    ("17 Avenue and 36 Street SE", "17 avenue & 36 street se"),
    ("17 Avenue and 36 Street SW", "17 avenue & 36 street sw"),
    ("Westbound 64 Avenue at Deerfoot NE", "64 avenue & deerfoot trail ne"),
    ("Sarcee Trail and Stoney T NW", "sarcee trail & stoney trail nw"),
    ("Southbound Deerfoot Trail and17 Avenue SE", "17 avenue & deerfoot trail se"),
    ("Northbound 194 Avenue on ramp to Macleod Trail SE", "194 avenue & macleod trail se"),
    ("39 Avenue NE &amp; 32 Street NE", "32 street & 39 avenue ne"),
    ("Highland Drive and Centre Street N", "centre street & highland drive n"),
])
def test_location_key_merges_one_intersection(name, key):
    assert location_key(name) == key


def test_rows_add_up(result):
    d = result["dataset"]
    assert d["rows_loaded"] == len(pd.read_csv(CSV))
    assert d["rows_used"] + d["rows_dropped"] == d["rows_loaded"]
    assert d["rows_used"] == len(load()[0])


def test_provincial_roads_excluded_by_default(result):
    assert result["weights"]["exclude_provincial"] is True
    keys = [r["location_key"] for r in result["top20"]] + [b["location_key"] for b in result["baseline"]["top20"]]
    assert not any("deerfoot" in k or "stoney" in k for k in keys)


def test_provincial_roads_can_be_included():
    out = run({"exclude_provincial": False}, tune=False)
    assert any("deerfoot" in r["location_key"] for r in out["top20"])


def test_no_tune_returns_given_weights():
    w = {"w_severity": 0.75, "w_trend": 0.5, "exclude_provincial": True}
    out = run(w, tune=False)
    assert out["weights"] == w
    assert len(out["agent_iterations"]) == 1


def test_tune_tries_15_candidates_and_keeps_one(result):
    its = result["agent_iterations"]
    assert len(its) == 15
    best = max(i["backtest_metric"] for i in its)
    assert result["metrics"]["backtest_agent"] == best


def test_movers_explain_their_own_numbers():
    out = run({"w_severity": 1.0, "exclude_provincial": True}, tune=False)
    assert len(out["movers"]) == 3
    for m in out["movers"]:
        assert m["from_rank"] != m["to_rank"]
        assert (m["direction"] == "up") == (m["to_rank"] < m["from_rank"])
    assert len({m["reason"] for m in out["movers"]}) == 3


@pytest.mark.parametrize("bad", [{"w_severity": 2}, {"w_trend": -0.1}, {"exclude_provincial": "yes"}, {"w_sev": 1}])
def test_bad_weights_are_rejected(bad):
    with pytest.raises(ValueError):
        run(bad, tune=False)


def test_run_is_under_two_seconds():
    start = time.perf_counter()
    run()
    assert time.perf_counter() - start < 2.0


def test_count_only_and_movers_carry_display_names(result):
    names = {r["location_key"]: r["name"] for r in result["top20"]}
    for entry in result["baseline"]["top20"] + result["movers"]:
        assert entry["name"].strip()
        assert names.get(entry["location_key"], entry["name"]) == entry["name"]


def test_ties_at_the_cut_share_credit():
    from engine.agent import TEST, TRAIN, backtest
    from engine.score import add_points

    df, _ = load()
    df = add_points(df)
    w = {"w_severity": 0.0, "w_trend": 0.0, "exclude_provincial": True}
    share, caught, total = backtest(df, TRAIN, TEST, w)
    whole = [backtest(df, TRAIN, TEST, w, n=k)[1] for k in (19, 20, 21)]
    # Credit grows by the mean of the tied group per extra place, never by one arbitrary pick.
    assert whole[0] <= caught <= whole[2]
    assert abs((whole[2] - caught) - (caught - whole[0])) < 0.11
    assert share == caught / total


def test_tuning_uses_the_planner_budget():
    out = run(tune=True, constraints={"budget": 5})
    assert out["plan"]["points_agent"] >= out["plan"]["points_baseline"]
    assert all(it["iteration"] == i for i, it in enumerate(out["agent_iterations"]))
