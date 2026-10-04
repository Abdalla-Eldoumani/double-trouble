"""The shortlist on screen as a CSV a traffic safety team can open in a spreadsheet."""

import pandas as pd

from app.ui import REGIONS

COLUMNS = [
    "Rank", "Location", "Latitude", "Longitude", "Incidents", "Pedestrian or cyclist",
    "Multi-vehicle", "More than one lane blocked", "Count-only rank", "Harm score", "Reason",
    "Area", "Locations to visit", "Severity weight", "Trend weight", "Jul-Dec multiplier",
    "Deerfoot and Stoney left out", "Data",
]
DATA_NOTE = ("City of Calgary Traffic Incidents, 2025, logged from traffic camera views; "
             "Open Government Licence - City of Calgary")


def shortlist_rows(result):
    """The rows the page shows: the planner's shortlist when there is one, else the top 20."""
    rows = sorted(result["top20"], key=lambda r: r["rank"])
    plan = result.get("plan")
    if plan:
        keep = set(plan["shortlist"])
        rows = [r for r in rows if r["location_key"] in keep]
    return rows


def shortlist_csv(result):
    """UTF-8 with a byte-order mark so Excel reads accents and dashes; the name says what is inside."""
    plan = (result.get("plan") or {}).get("constraints") or {}
    region, budget = plan.get("region"), plan.get("budget", len(result["top20"]))
    w = result["weights"]
    rows = shortlist_rows(result)
    sample = not result.get("plan")
    records = [{
        "Rank": r["rank"], "Location": r["name"], "Latitude": r["lat"], "Longitude": r["lon"],
        "Incidents": r["incidents"], "Pedestrian or cyclist": r["pedestrian_or_cyclist"],
        "Multi-vehicle": r.get("multi_vehicle"), "More than one lane blocked": r.get("multiple_lanes"),
        "Count-only rank": r["baseline_rank"], "Harm score": r["score"], "Reason": r["reason"],
        "Area": f"{REGIONS[region]} Calgary" if region else "All of Calgary", "Locations to visit": budget,
        "Severity weight": w["w_severity"], "Trend weight": w["w_trend"],
        "Jul-Dec multiplier": plan.get("recent_weight", 1.0),
        "Deerfoot and Stoney left out": w["exclude_provincial"],
        "Data": "Sample file, engine not connected" if sample else DATA_NOTE,
    } for r in rows]
    data = pd.DataFrame(records, columns=COLUMNS).to_csv(index=False).encode("utf-8-sig")
    name = f"calgary_safety_shortlist_2025_{region or 'citywide'}_top{len(rows)}{'_sample' if sample else ''}.csv"
    return data, name
