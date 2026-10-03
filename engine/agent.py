"""Shortlist agent: plan a weight grid, backtest each candidate, keep the best, explain the result.

    python -m engine.agent --out out/result.json
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from engine.data import load
from engine.score import TOP_N, add_points, baseline, rank, signals

YEAR = ("2025-01-01", "2026-01-01")
# Rank on Jan to Aug, score on Sep to Dec.
TRAIN, TEST = ("2025-01-01", "2025-09-01"), ("2025-09-01", "2026-01-01")
# A second, independent split to check the chosen weights were not a fluke of the first.
CHECK_TRAIN, CHECK_TEST = ("2025-01-01", "2025-07-01"), ("2025-07-01", "2026-01-01")

GRID = [(s, t) for t in (0.0, 0.5, 1.0) for s in (0.0, 0.25, 0.5, 0.75, 1.0)]
DEFAULT_WEIGHTS = {"w_severity": 0.0, "w_trend": 0.0, "exclude_provincial": False}

METRIC_NAME = "share of Sep-Dec severity points captured by a top 20 ranked on Jan-Aug"
CHECK_METRIC_NAME = "share of Jul-Dec severity points captured by a top 20 ranked on Jan-Jun"


def check_weights(weights: dict | None) -> dict:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    unknown = set(w) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise ValueError(f"unknown weight keys: {sorted(unknown)}")
    for k in ("w_severity", "w_trend"):
        if isinstance(w[k], bool) or not isinstance(w[k], (int, float)) or not 0 <= w[k] <= 1:
            raise ValueError(f"{k} must be a number in [0, 1], got {w[k]!r}")
        w[k] = float(w[k])
    if not isinstance(w["exclude_provincial"], bool):
        raise ValueError(f"exclude_provincial must be true or false, got {w['exclude_provincial']!r}")
    return w


def backtest(df: pd.DataFrame, train: tuple, test: tuple, w: dict) -> tuple[float, int, int]:
    """Share of test-window severity points that fall in the train-window top 20."""
    top = rank(signals(df, *train), w["w_severity"], w["w_trend"], w["exclude_provincial"]).head(TOP_N)
    later = signals(df, *test)
    if w["exclude_provincial"]:
        later = later[~later["provincial"]]
    total = int(later["severity_points"].sum())
    caught = int(later["severity_points"].reindex(top.index, fill_value=0).sum())
    return caught / total, caught, total


def _weights(s: float, t: float, exclude: bool) -> dict:
    return {"w_severity": s, "w_trend": t, "exclude_provincial": exclude}


def search(df: pd.DataFrame, exclude: bool) -> tuple[dict, list]:
    # Simplest candidates first, and a candidate replaces the best only if strictly better,
    # so a tie always keeps the simpler weights.
    plan = sorted(GRID, key=lambda st: (st[0] + st[1], st[1]))
    iterations, best, best_caught = [], None, -1
    for i, (s, t) in enumerate(plan):
        w = _weights(s, t, exclude)
        share, caught, total = backtest(df, TRAIN, TEST, w)
        if best is None:
            note = f"baseline: count-only captures {caught} of {total} points"
        elif caught > best_caught:
            note = f"kept: {caught} points beats best so far {best_caught}"
        elif caught == best_caught:
            note = f"rejected: ties best so far at {caught} points, simpler weights kept"
        else:
            note = f"rejected: {caught} points, below best so far {best_caught}"
        if caught > best_caught:
            best, best_caught = w, caught
        iterations.append({"iteration": i, "weights": w, "backtest_metric": round(share, 4), "note": note})
    return best, iterations


def describe(row: pd.Series) -> str:
    parts = [f"{row['incidents']} incidents"]
    if row["pedestrian_or_cyclist"]:
        parts.append(f"{row['pedestrian_or_cyclist']} involved a pedestrian or cyclist")
    if row["multi_vehicle"]:
        parts.append(f"{row['multi_vehicle']} were multi-vehicle")
    if row["multiple_lanes"]:
        parts.append(f"{row['multiple_lanes']} blocked multiple lanes")
    parts.append(f"{row['early']} in Jan-Jun vs {row['late']} in Jul-Dec")
    return ", ".join(parts)


def mover_reason(row: pd.Series, avg: float, w: dict) -> str:
    n, sev = row["incidents"], row["severity_points"]
    mix = f"{row['pedestrian_or_cyclist']} pedestrian or cyclist, {row['multi_vehicle']} multi-vehicle"
    rate = f"{sev / n:.2f} severity points per incident vs {avg:.2f} across both top-20 lists"
    if row["rank"] < row["baseline_rank"]:
        why = f"{rate}: of its {n} incidents, {mix}"
    else:
        why = f"{n} incidents but only {rate}: {mix}"
    if w["w_trend"] and row["late"] != row["early"]:
        change = "rose" if row["late"] > row["early"] else "fell"
        why += f"; incidents {change} from {row['early']} in Jan-Jun to {row['late']} in Jul-Dec"
    return why


def run(weights: dict | None = None, tune: bool = True) -> dict:
    w = check_weights(weights)
    df, info = load()
    df = add_points(df)

    if tune:
        w, iterations = search(df, w["exclude_provincial"])
    else:
        share, caught, total = backtest(df, TRAIN, TEST, w)
        iterations = [{
            "iteration": 0, "weights": w, "backtest_metric": round(share, 4),
            "note": f"given weights, not tuned: {caught} of {total} points",
        }]

    count_only = _weights(0.0, 0.0, w["exclude_provincial"])
    sig = signals(df, *YEAR)
    base = baseline(sig, w["exclude_provincial"])
    final = rank(sig, w["w_severity"], w["w_trend"], w["exclude_provincial"])
    final["baseline_rank"] = base["rank"].reindex(final.index)
    top = final.head(TOP_N)
    base_top = set(base.index[:TOP_N])

    places = df.groupby("location_key").agg(
        name=("name", lambda s: s.mode().iloc[0]),
        lat=("latitude", "median"),
        lon=("longitude", "median"),
        quadrant=("quadrant", lambda s: s.mode().iloc[0]),
    )

    top20 = []
    for key, r in top.iterrows():
        p = places.loc[key]
        top20.append({
            "location_key": key,
            "name": p["name"],
            "lat": round(float(p["lat"]), 5),
            "lon": round(float(p["lon"]), 5),
            "quadrant": p["quadrant"],
            "rank": int(r["rank"]),
            "baseline_rank": int(r["baseline_rank"]),
            "score": round(float(r["score"]), 2),
            "incidents": int(r["incidents"]),
            "severity_points": int(r["severity_points"]),
            "pedestrian_or_cyclist": int(r["pedestrian_or_cyclist"]),
            "in_baseline_top20": key in base_top,
            "reason": describe(r),
        })

    # Movers come from either top 20, so a location that fell off the list can be explained too.
    pool = final.loc[final.index.isin(top.index) | final.index.isin(base_top)]
    change = (pool["baseline_rank"] - pool["rank"]).abs()
    avg = pool["severity_points"].sum() / pool["incidents"].sum()
    movers = [
        {
            "location_key": key,
            "direction": "up" if pool.at[key, "rank"] < pool.at[key, "baseline_rank"] else "down",
            "from_rank": int(pool.at[key, "baseline_rank"]),
            "to_rank": int(pool.at[key, "rank"]),
            "reason": mover_reason(pool.loc[key], avg, w),
        }
        for key in change[change > 0].sort_values(ascending=False, kind="stable").index[:3]
    ]

    base_share = backtest(df, TRAIN, TEST, count_only)[0]
    agent_share = backtest(df, TRAIN, TEST, w)[0]
    return {
        "schema_version": 1,
        "dataset": {k: info[k] for k in ("source", "rows_loaded", "rows_dropped", "drop_reason", "rows_used")},
        "baseline": {
            "name": "count-only",
            "top20": [{"location_key": k, "incidents": int(n)} for k, n in base["incidents"].head(TOP_N).items()],
        },
        "weights": w,
        "agent_iterations": iterations,
        "metrics": {
            "overlap_with_baseline": len(set(top.index) & base_top),
            "backtest_metric_name": METRIC_NAME,
            "backtest_baseline": round(base_share, 4),
            "backtest_agent": round(agent_share, 4),
            "check_metric_name": CHECK_METRIC_NAME,
            "check_baseline": round(backtest(df, CHECK_TRAIN, CHECK_TEST, count_only)[0], 4),
            "check_agent": round(backtest(df, CHECK_TRAIN, CHECK_TEST, w)[0], 4),
        },
        "movers": movers,
        "top20": top20,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("out/result.json"))
    ap.add_argument("--w-severity", type=float)
    ap.add_argument("--w-trend", type=float)
    ap.add_argument("--exclude-provincial", action="store_true")
    ap.add_argument("--no-tune", action="store_true", help="score the given weights instead of searching")
    a = ap.parse_args()
    given = {"exclude_provincial": a.exclude_provincial}
    if a.w_severity is not None:
        given["w_severity"] = a.w_severity
    if a.w_trend is not None:
        given["w_trend"] = a.w_trend
    result = run(given, tune=not a.no_tune)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2) + "\n")
    m = result["metrics"]
    print(f"wrote {a.out}: weights {result['weights']}")
    print(f"backtest Jan-Aug -> Sep-Dec: count-only {m['backtest_baseline']}, chosen {m['backtest_agent']}")
    print(f"check    Jan-Jun -> Jul-Dec: count-only {m['check_baseline']}, chosen {m['check_agent']}")
    print(f"overlap with count-only top 20: {m['overlap_with_baseline']}")


if __name__ == "__main__":
    main()
