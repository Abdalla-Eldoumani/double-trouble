"""Per-location signals and the weighted score."""

import pandas as pd

# Severity points per incident. These are judgment calls, stated so they can be argued with.
BASE_POINTS = 1  # every crash counts, so a location never scores below its own count
PEDESTRIAN_OR_CYCLIST_POINTS = 3  # an unprotected road user was hit; EMS attended most of these rows
MULTI_VEHICLE_POINTS = 1  # two or more vehicles means more people exposed per crash
MULTIPLE_LANES_POINTS = 1  # blocking several lanes is a proxy for a larger crash

PEDESTRIAN_OR_CYCLIST = r"pedestrian|cyclist"
MULTI_VEHICLE = r"multi-vehicle|two vehicle"
MULTIPLE_LANES = r"blocking multiple lanes"

# Name pattern only. Whether these are provincial is sourced in docs/FACTS.md, not here.
PROVINCIAL = r"deerfoot|stoney"

TOP_N = 20


def add_points(df: pd.DataFrame) -> pd.DataFrame:
    d = df["description"]
    out = df.assign(
        pedestrian_or_cyclist=d.str.contains(PEDESTRIAN_OR_CYCLIST, regex=True).astype(int),
        multi_vehicle=d.str.contains(MULTI_VEHICLE, regex=True).astype(int),
        multiple_lanes=d.str.contains(MULTIPLE_LANES, regex=False).astype(int),
    )
    out["severity_points"] = (
        BASE_POINTS
        + PEDESTRIAN_OR_CYCLIST_POINTS * out["pedestrian_or_cyclist"]
        + MULTI_VEHICLE_POINTS * out["multi_vehicle"]
        + MULTIPLE_LANES_POINTS * out["multiple_lanes"]
    )
    return out


def signals(df: pd.DataFrame, start: str, end: str, recent_weight: float = 1.0) -> pd.DataFrame:
    """One row per location for incidents in [start, end). Trend compares the two halves.

    Windows are whole months, so the halves split on a month boundary (Jan-Jun vs Jul-Dec).
    recent_weight counts each late-half incident that many times in the weighted columns;
    the raw counts stay as they are.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    months = (end.year - start.year) * 12 + end.month - start.month
    mid = start + pd.DateOffset(months=months // 2)
    w = df[(df["start_dt"] >= start) & (df["start_dt"] < end)]
    late = (w["start_dt"] >= mid).astype(int)
    weight = 1 + (recent_weight - 1) * late
    g = w.assign(late=late, weight=weight, weighted_points=w["severity_points"] * weight).groupby("location_key")
    sig = g.agg(
        incidents=("severity_points", "size"),
        severity_points=("severity_points", "sum"),
        pedestrian_or_cyclist=("pedestrian_or_cyclist", "sum"),
        multi_vehicle=("multi_vehicle", "sum"),
        multiple_lanes=("multiple_lanes", "sum"),
        late=("late", "sum"),
        weighted_incidents=("weight", "sum"),
        weighted_points=("weighted_points", "sum"),
    )
    sig["early"] = sig["incidents"] - sig["late"]
    # +1 smoothing keeps a 0 -> 1 location from reading as an infinite rise.
    sig["trend"] = (sig["late"] + 1) / (sig["early"] + 1)
    sig["provincial"] = sig.index.str.contains(PROVINCIAL, regex=True)
    return sig


def rank(
    sig: pd.DataFrame, w_severity: float, w_trend: float, exclude_provincial: bool, keep: set | None = None
) -> pd.DataFrame:
    """All locations, best first. Ties break on incidents, then key, so the order is stable.

    keep limits the ranking to those location keys (a quadrant chosen by the planner).
    """
    s = sig[~sig["provincial"]] if exclude_provincial else sig
    if keep is not None:
        s = s[s.index.isin(keep)]
    mix = (1 - w_severity) * s["weighted_incidents"] + w_severity * s["weighted_points"]
    out = s.assign(score=mix * s["trend"] ** w_trend).reset_index()
    out = out.sort_values(["score", "incidents", "location_key"], ascending=[False, False, True])
    out["rank"] = range(1, len(out) + 1)
    return out.set_index("location_key")


def baseline(sig: pd.DataFrame, exclude_provincial: bool, keep: set | None = None) -> pd.DataFrame:
    # Count-only means raw counts, so recency weighting never leaks into the baseline.
    raw = sig.assign(weighted_incidents=sig["incidents"], weighted_points=sig["severity_points"])
    return rank(raw, 0.0, 0.0, exclude_provincial, keep)
