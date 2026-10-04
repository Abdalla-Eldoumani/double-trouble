"""Shortlist agent: plan a weight grid, backtest each candidate, keep the best, explain the result.

    python -m engine.agent --out out/result.json
"""

import argparse
import functools
import json
from pathlib import Path

import pandas as pd

from engine.data import CSV, load
from engine.score import TOP_N, add_points, baseline, rank, signals

YEAR = ("2025-01-01", "2026-01-01")
# Rank on Jan to Aug, score on Sep to Dec.
TRAIN, TEST = ("2025-01-01", "2025-09-01"), ("2025-09-01", "2026-01-01")
# A second split as a consistency check. Jul-Dec contains Sep-Dec, so it is not a held-out test.
CHECK_TRAIN, CHECK_TEST = ("2025-01-01", "2025-07-01"), ("2025-07-01", "2026-01-01")

GRID = [(s, t) for t in (0.0, 0.5, 1.0) for s in (0.0, 0.25, 0.5, 0.75, 1.0)]
# Deerfoot and Stoney are maintained by the province, not the City (docs/FACTS.md).
DEFAULT_WEIGHTS = {"w_severity": 0.0, "w_trend": 0.0, "exclude_provincial": True}

# What a planner can ask for on top of the weights: recent incidents counted more, one quadrant, a smaller budget.
DEFAULT_CONSTRAINTS = {"recent_weight": 1.0, "region": None, "budget": TOP_N}
REGIONS = ("NE", "NW", "SE", "SW")
MAX_RECENT_WEIGHT = 5.0

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


def check_constraints(constraints: dict | None) -> dict:
    c = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    unknown = set(c) - set(DEFAULT_CONSTRAINTS)
    if unknown:
        raise ValueError(f"unknown constraint keys: {sorted(unknown)}")
    r = c["recent_weight"]
    if isinstance(r, bool) or not isinstance(r, (int, float)) or not 1 <= r <= MAX_RECENT_WEIGHT:
        raise ValueError(f"recent_weight must be a number in [1, {MAX_RECENT_WEIGHT:g}], got {r!r}")
    c["recent_weight"] = float(r)
    if c["region"] is not None and c["region"] not in REGIONS:
        raise ValueError(f"region must be one of {REGIONS} or None, got {c['region']!r}")
    b = c["budget"]
    if isinstance(b, bool) or not isinstance(b, int) or not 1 <= b <= TOP_N:
        raise ValueError(f"budget must be a whole number from 1 to {TOP_N}, got {b!r}")
    return c


def backtest(
    df: pd.DataFrame, train: tuple, test: tuple, w: dict,
    recent_weight: float = 1.0, keep: set | None = None, n: int = TOP_N,
) -> tuple[float, float, int]:
    """Share of test-window severity points that fall in the train-window top n.

    Locations tied on score at the cut share the remaining places equally, so the
    alphabetical tie-break used for display never decides who wins a backtest.
    """
    sig = signals(df, *train, recent_weight=recent_weight)
    ranked = rank(sig, w["w_severity"], w["w_trend"], w["exclude_provincial"], keep)
    later = signals(df, *test)
    if w["exclude_provincial"]:
        later = later[~later["provincial"]]
    if keep is not None:
        later = later[later.index.isin(keep)]
    points = later["severity_points"]
    total = int(points.sum())
    if len(ranked) <= n:
        caught = float(points.reindex(ranked.index, fill_value=0).sum())
    else:
        cut = ranked["score"].iloc[n - 1]
        above = ranked.index[ranked["score"] > cut]
        tied = ranked.index[ranked["score"] == cut]
        caught = float(points.reindex(above, fill_value=0).sum()
                       + (n - len(above)) * points.reindex(tied, fill_value=0).mean())
    caught = round(caught, 1)
    # An area with no later incidents (a small quadrant, a narrow window) scores zero, not a crash.
    share = caught / total if total else 0.0
    return share, int(caught) if caught.is_integer() else caught, total


def _weights(s: float, t: float, exclude: bool) -> dict:
    return {"w_severity": s, "w_trend": t, "exclude_provincial": exclude}


def search(
    df: pd.DataFrame, exclude: bool, recent_weight: float = 1.0, keep: set | None = None, n: int = TOP_N,
) -> tuple[dict, list]:
    # Simplest candidates first, and a candidate replaces the best only if strictly better,
    # so a tie always keeps the simpler weights.
    plan = sorted(GRID, key=lambda st: (st[0] + st[1], st[1]))
    iterations, best, best_caught = [], None, -1
    for i, (s, t) in enumerate(plan):
        w = _weights(s, t, exclude)
        share, caught, total = backtest(df, TRAIN, TEST, w, recent_weight, keep, n)
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


def _share(k: int, n: int, what: str) -> str:
    return f"none of its {n} incidents {what}" if k == 0 else f"{k} of its {n} incidents {what}"


def mover_reason(row: pd.Series, avg: float, w: dict) -> str:
    n, sev = row["incidents"], row["severity_points"]
    ped, multi = row["pedestrian_or_cyclist"], row["multi_vehicle"]
    rate = f"{sev / n:.2f} severity points per incident against {avg:.2f} across both top-20 lists"
    if row["rank"] < row["baseline_rank"]:
        lead = _share(ped, n, "involved a pedestrian or cyclist") if ped else _share(multi, n, "were multi-vehicle")
        why = f"{lead[0].upper()}{lead[1:]}, so it scores {rate}"
    else:
        peds = "none" if ped == 0 else f"only {ped}"
        multis = "none were" if multi == 0 else f"{multi} {'was' if multi == 1 else 'were'}"
        why = f"{n} incidents, but {peds} involved a pedestrian or cyclist and {multis} multi-vehicle: {rate}"
    if w["w_trend"] and row["late"] != row["early"]:
        change = "rose" if row["late"] > row["early"] else "fell"
        why += f"; incidents {change} from {row['early']} in Jan-Jun to {row['late']} in Jul-Dec"
    return why


@functools.lru_cache(maxsize=1)
def _prepare(loader, csv_mtime: float) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Load and score the CSV once per file version and loader; every run after that only re-ranks."""
    df, info = loader()
    df = add_points(df)
    places = df.groupby("location_key").agg(
        name=("display_name", lambda s: s.mode().iloc[0]),
        lat=("latitude", "median"),
        lon=("longitude", "median"),
        quadrant=("quadrant", lambda s: s.mode().iloc[0]),
    )
    # A merged location keeps the quadrant of its key, whichever report its name came from.
    tag = places.index.str.extract(r" (ne|nw|se|sw|n|s|e|w)$", expand=False).str.upper().fillna("")
    stem = places["name"].str.replace(r" (?:NE|NW|SE|SW|N|S|E|W)$", "", regex=True)
    places["name"] = (stem + " " + tag).str.strip().to_numpy()
    return df, info, places


def run(weights: dict | None = None, tune: bool = True, constraints: dict | None = None) -> dict:
    w = check_weights(weights)
    c = check_constraints(constraints)
    df, info, places = _prepare(load, CSV.stat().st_mtime)
    keep = set(places.index[places["quadrant"] == c["region"]]) if c["region"] else None
    recent = c["recent_weight"]

    if tune:
        # Tune for the shortlist the planner can afford, not always a top 20.
        w, iterations = search(df, w["exclude_provincial"], recent, keep, c["budget"])
    else:
        share, caught, total = backtest(df, TRAIN, TEST, w, recent, keep, c["budget"])
        iterations = [{
            "iteration": 0, "weights": w, "backtest_metric": round(share, 4),
            "note": f"given weights, not tuned: {caught} of {total} points",
        }]

    count_only = _weights(0.0, 0.0, w["exclude_provincial"])
    sig = signals(df, *YEAR, recent_weight=recent)
    base = baseline(sig, w["exclude_provincial"], keep)
    final = rank(sig, w["w_severity"], w["w_trend"], w["exclude_provincial"], keep)
    final["baseline_rank"] = base["rank"].reindex(final.index)
    top = final.head(TOP_N)
    base_top = set(base.index[:TOP_N])

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
            "multi_vehicle": int(r["multi_vehicle"]),
            "multiple_lanes": int(r["multiple_lanes"]),
            "early": int(r["early"]),
            "late": int(r["late"]),
            "in_baseline_top20": key in base_top,
            "reason": describe(r),
        })

    # Movers come from either top 20, so a location that fell off the list can be explained too.
    pool = final.loc[final.index.isin(top.index) | final.index.isin(base_top)]
    change = (pool["baseline_rank"] - pool["rank"]).abs()
    avg = pool["severity_points"].sum() / pool["incidents"].sum() if pool["incidents"].sum() else 0.0
    movers = [
        {
            "location_key": key,
            "name": places.at[key, "name"],
            "direction": "up" if pool.at[key, "rank"] < pool.at[key, "baseline_rank"] else "down",
            "from_rank": int(pool.at[key, "baseline_rank"]),
            "to_rank": int(pool.at[key, "rank"]),
            "reason": mover_reason(pool.loc[key], avg, w),
            # Optional counts, so a location that fell off the list can be explained too.
            "incidents": int(pool.at[key, "incidents"]),
            "pedestrian_or_cyclist": int(pool.at[key, "pedestrian_or_cyclist"]),
            "multi_vehicle": int(pool.at[key, "multi_vehicle"]),
            "multiple_lanes": int(pool.at[key, "multiple_lanes"]),
            "early": int(pool.at[key, "early"]),
            "late": int(pool.at[key, "late"]),
        }
        for key in change[change > 0].sort_values(ascending=False, kind="stable").index[:3]
    ]

    base_share = backtest(df, TRAIN, TEST, count_only, 1.0, keep)[0]
    agent_share = backtest(df, TRAIN, TEST, w, recent, keep)[0]
    n = c["budget"]
    plan_base = backtest(df, TRAIN, TEST, count_only, 1.0, keep, n)
    plan_agent = backtest(df, TRAIN, TEST, w, recent, keep, n)
    where = f"the {c['region']} quadrant" if c["region"] else "the city"
    return {
        "schema_version": 1,
        "dataset": {k: info[k] for k in ("source", "rows_loaded", "rows_dropped", "drop_reason", "rows_used")},
        "baseline": {
            "name": "count-only",
            "top20": [
                {"location_key": k, "name": places.at[k, "name"], "incidents": int(n)}
                for k, n in base["incidents"].head(TOP_N).items()
            ],
        },
        "weights": w,
        "agent_iterations": iterations,
        "metrics": {
            "overlap_with_baseline": len(set(top.index) & base_top),
            "backtest_metric_name": METRIC_NAME + (f" in the {c['region']} quadrant" if c["region"] else ""),
            "backtest_baseline": round(base_share, 4),
            "backtest_agent": round(agent_share, 4),
            "check_metric_name": CHECK_METRIC_NAME + (f" in the {c['region']} quadrant" if c["region"] else ""),
            "check_baseline": round(backtest(df, CHECK_TRAIN, CHECK_TEST, count_only, 1.0, keep)[0], 4),
            "check_agent": round(backtest(df, CHECK_TRAIN, CHECK_TEST, w, recent, keep)[0], 4),
        },
        "plan": {
            "constraints": c,
            "shortlist": list(top.index[:n]),
            "baseline_shortlist": list(base.index[:n]),
            "overlap": len(set(top.index[:n]) & set(base.index[:n])),
            "metric_name": f"share of Sep-Dec severity points in {where} captured by a top {n} ranked on Jan-Aug",
            "backtest_baseline": round(plan_base[0], 4),
            "backtest_agent": round(plan_agent[0], 4),
            "points_baseline": plan_base[1],
            "points_agent": plan_agent[1],
            "points_total": plan_agent[2],
        },
        "movers": movers,
        "top20": top20,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("out/result.json"))
    ap.add_argument("--w-severity", type=float)
    ap.add_argument("--w-trend", type=float)
    ap.add_argument("--exclude-provincial", action=argparse.BooleanOptionalAction, help="default: on")
    ap.add_argument("--no-tune", action="store_true", help="score the given weights instead of searching")
    a = ap.parse_args()
    given = {}
    if a.exclude_provincial is not None:
        given["exclude_provincial"] = a.exclude_provincial
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
