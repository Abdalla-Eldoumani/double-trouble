import json
from pathlib import Path

import streamlit as st

FIXTURE = Path(__file__).resolve().parent.parent / "contract" / "sample_output.json"
FALLBACK_BANNER = "Showing sample data, engine not connected."

# Only the fields this app reads. Extra fields are ignored so the engine can add optional ones.
REQUIRED = {
    "dataset": ["source", "rows_loaded", "rows_dropped", "drop_reason", "rows_used"],
    "baseline": ["top20"],
    "weights": ["w_severity", "w_trend", "exclude_provincial"],
    "metrics": ["overlap_with_baseline", "backtest_metric_name", "backtest_baseline", "backtest_agent"],
}
REQUIRED_ITEMS = {
    "top20": ["location_key", "name", "lat", "lon", "rank", "baseline_rank", "score",
              "incidents", "pedestrian_or_cyclist", "reason"],
    "movers": ["location_key", "direction", "from_rank", "to_rank", "reason"],
    "agent_iterations": ["iteration", "weights", "backtest_metric", "note"],
}


class ResultShapeError(ValueError):
    pass


def validate(result):
    problems = []
    for section, keys in REQUIRED.items():
        if not isinstance(result.get(section), dict):
            problems.append(f"missing section '{section}'")
            continue
        problems += [f"missing '{section}.{k}'" for k in keys if k not in result[section]]
    for section, keys in REQUIRED_ITEMS.items():
        items = result.get(section)
        if not isinstance(items, list):
            problems.append(f"missing list '{section}'")
            continue
        for i, item in enumerate(items):
            problems += [f"missing '{section}[{i}].{k}'" for k in keys if k not in item]
    baseline = result.get("baseline")
    if isinstance(baseline, dict) and isinstance(baseline.get("top20"), list):
        for i, item in enumerate(baseline["top20"]):
            problems += [f"missing 'baseline.top20[{i}].{k}'"
                         for k in ("location_key", "incidents") if k not in item]
    return problems


def consistency_warnings(result):
    """Contradictions inside a well-formed result, shown on the page rather than hidden."""
    warnings = []
    position = {r["location_key"]: i for i, r in enumerate(result["baseline"]["top20"], start=1)}
    disagree = []
    for r in result["top20"]:
        if r["location_key"] in position:
            wrong = position[r["location_key"]] != r["baseline_rank"]
        else:
            wrong = r["baseline_rank"] <= len(position)
        if wrong:
            disagree.append(r["name"])
    if disagree:
        warnings.append(f"Count-only rank differs between the two lists for {len(disagree)} "
                        f"locations: {', '.join(disagree)}.")
    overlap = len(position.keys() & {r["location_key"] for r in result["top20"]})
    if overlap != result["metrics"]["overlap_with_baseline"]:
        warnings.append(f"Reported overlap is {result['metrics']['overlap_with_baseline']} "
                        f"but the two lists share {overlap} locations.")
    unchanged = [m["location_key"] for m in result["movers"] if m["from_rank"] == m["to_rank"]]
    if unchanged:
        warnings.append(f"{len(unchanged)} listed movers have the same rank before and after.")
    return warnings


@st.cache_data(show_spinner=False)
def _load_fixture():
    return json.loads(FIXTURE.read_text())


@st.cache_data(show_spinner="Ranking locations...")
def _run_engine(weights, tune, constraints=None):
    from engine.agent import run
    # Only pass constraints once the planner has set some, so older engines keep working.
    if constraints is None:
        return run(weights=weights, tune=tune)
    return run(weights=weights, tune=tune, constraints=constraints)


def get_result(weights=None, tune=False, constraints=None):
    try:
        import engine.agent  # noqa: F401
    except ImportError as exc:
        st.warning(FALLBACK_BANNER)
        st.caption(f"Engine import failed: {exc}. The weight controls do not change sample data.")
        result = _load_fixture()
    else:
        result = _run_engine(weights, tune, constraints)
    problems = validate(result)
    if problems:
        raise ResultShapeError("The result is missing fields the app needs: " + "; ".join(problems))
    return result
