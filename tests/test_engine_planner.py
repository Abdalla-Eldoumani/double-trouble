import re
import time

import pytest

from engine.agent import DEFAULT_CONSTRAINTS, run
from engine.planner import compare, display, explain, parse

EXAMPLE = ("Prioritize recent crashes twice as much, only show northwest Calgary, "
           "and assume we can only investigate five intersections.")


@pytest.fixture(scope="module")
def baseline_result():
    return run(tune=False)


@pytest.fixture(scope="module")
def example_result():
    return run(tune=False, constraints=parse(EXAMPLE)["constraints"])


def numbers(value):
    if isinstance(value, dict):
        return set().union(*(numbers(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(numbers(v) for v in value)) if value else set()
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float)):
        return {f"{value:g}"}
    return set(re.findall(r"\d+", str(value)))


@pytest.mark.parametrize("text, constraints, weights, tune", [
    (EXAMPLE, {"recent_weight": 2.0, "region": "NW", "budget": 5}, {}, False),
    ("now show me the north-east instead", {"region": "NE"}, {}, False),
    ("top 10 across the whole city", {"region": None, "budget": 10}, {}, False),
    ("count recent crashes three times", {"recent_weight": 3.0}, {}, False),
    ("ignore recency", {"recent_weight": 1.0}, {}, False),
    ("focus on pedestrians and cyclists", {}, {"w_severity": 1.0}, False),
    ("just count crashes, raw count", {}, {"w_severity": 0.0}, False),
    ("include Deerfoot and Stoney", {}, {"exclude_provincial": False}, False),
    ("city roads only", {}, {"exclude_provincial": True}, False),
    ("let the agent tune it", {}, {}, True),
    ("what is the weather like", {}, {}, False),
    ("don't use severity", {}, {"w_severity": 0.0}, False),
    ("no severity weighting please", {}, {"w_severity": 0.0}, False),
    ("don't exclude deerfoot", {}, {"exclude_provincial": False}, False),
    ("weight recent incidents 10 times", {"recent_weight": 5.0}, {}, False),
    ("recent x3", {"recent_weight": 3.0}, {}, False),
    ("look at 16 Avenue and 19 Street NE", {"region": "NE"}, {}, False),
    ("our budget is 6", {"budget": 6}, {}, False),
    ("let the agent decide", {}, {}, True),
])

def test_parse(text, constraints, weights, tune):
    p = parse(text)
    assert p["constraints"] == constraints
    assert p["weights"] == weights
    assert p["tune"] is tune


def test_reset_phrasings():
    for text in ("reset", "start again", "back to defaults"):
        assert parse(text)["reset"] is True


def test_parse_clamps_budget_and_names_both_quadrants():
    assert parse("we can investigate 50 intersections")["constraints"] == {"budget": 20}
    p = parse("northwest and southeast")
    assert "region" not in p["constraints"]
    assert any("more than one quadrant" in h for h in p["heard"])


def test_reset_restores_defaults():
    assert parse("reset")["constraints"] == DEFAULT_CONSTRAINTS


def test_constraints_shape_the_result(example_result):
    plan = example_result["plan"]
    assert plan["constraints"] == {"recent_weight": 2.0, "region": "NW", "budget": 5}
    assert len(plan["shortlist"]) == 5 and len(plan["baseline_shortlist"]) == 5
    assert all(r["quadrant"] == "NW" for r in example_result["top20"])
    assert [r["location_key"] for r in example_result["top20"][:5]] == plan["shortlist"]
    assert 0 <= plan["points_agent"] <= plan["points_total"]


def test_no_constraints_matches_defaults(baseline_result):
    assert baseline_result["plan"]["constraints"] == DEFAULT_CONSTRAINTS
    same = run(tune=False, constraints=DEFAULT_CONSTRAINTS)
    assert same == baseline_result


def test_recency_reorders_but_count_only_baseline_does_not_move(baseline_result):
    recent = run(tune=False, constraints={"recent_weight": 5.0})
    assert recent["baseline"] == baseline_result["baseline"]
    assert [r["location_key"] for r in recent["top20"]] != [r["location_key"] for r in baseline_result["top20"]]


@pytest.mark.parametrize("bad", [{"recent_weight": 0.5}, {"recent_weight": 6}, {"region": "N"},
                                 {"budget": 0}, {"budget": 21}, {"budget": 5.0}, {"area": "NW"}])
def test_bad_constraints_are_rejected(bad):
    with pytest.raises(ValueError):
        run(tune=False, constraints=bad)


def test_explanation_uses_only_result_numbers(baseline_result, example_result):
    p = parse(EXAMPLE)
    text = explain(example_result, compare(baseline_result, example_result), p["heard"])
    lead = next(r for r in example_result["top20"] if r["location_key"] == example_result["plan"]["shortlist"][0])
    assert lead["name"] in text
    allowed = numbers(example_result) | numbers(baseline_result) | {"2025"}
    assert set(re.findall(r"\d+", text)) <= allowed


def test_compare_names_entries_and_exits(baseline_result):
    severe = run({"w_severity": 1.0}, tune=False)
    diff = compare(baseline_result, severe)
    old, new = baseline_result["plan"]["shortlist"], severe["plan"]["shortlist"]
    assert set(diff["entered"]) == set(new) - set(old)
    assert set(diff["left"]) == set(old) - set(new)
    assert compare(None, severe)["first"] is True


def test_constrained_tuned_run_is_under_two_seconds():
    start = time.perf_counter()
    run(constraints={"recent_weight": 2.0, "region": "NW", "budget": 5})
    assert time.perf_counter() - start < 2.0
