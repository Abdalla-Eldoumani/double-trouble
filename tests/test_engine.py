import json
import time
from pathlib import Path

import pandas as pd
import pytest

from engine.agent import run
from engine.data import CSV, load, location_key

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
                                   r"|severe weather|hazardous road|lrt gates)|police|oversized load")
    counts = raw.loc[~non_crash, "incident_info"].map(location_key).value_counts()
    base = result["baseline"]["top20"]
    assert [b["incidents"] for b in base] == counts.head(20).tolist()
    for b in base:
        assert counts[b["location_key"]] == b["incidents"]


@pytest.mark.parametrize("name, key", [
    ("Southbound Deerfoot Trail approaching Glenmore Trail SE", "deerfoot trail & glenmore trail se"),
    (" Glenmore Trail and  Deerfoot Trail SE ", "deerfoot trail & glenmore trail se"),
    ("Southbound Deerfoot Trail ramp to 16 Avenue NE", "16 avenue & deerfoot trail ne"),
    ("Soutbound Deerfoot Trail exit to McKnight Blvd NE", "deerfoot trail & mcknight boulevard ne"),
    ("Westbound Stoney Trail after McKenzie Lake Boulevard SE", "mckenzie lake boulevard & stoney trail se"),
    ("17 Avenue and 36 Street SE", "17 avenue & 36 street se"),
    ("17 Avenue and 36 Street SW", "17 avenue & 36 street sw"),
])
def test_location_key_merges_one_intersection(name, key):
    assert location_key(name) == key


def test_rows_add_up(result):
    d = result["dataset"]
    assert d["rows_loaded"] == len(pd.read_csv(CSV))
    assert d["rows_used"] + d["rows_dropped"] == d["rows_loaded"]
    assert d["rows_used"] == len(load()[0])


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
