"""CSV handoff of the applied result, with no session state or filesystem writes."""

import pandas as pd

from app import planning, ui

COLUMNS = [
    "Rank", "Location", "Latitude", "Longitude", "Reported crash count",
    "Pedestrian/cyclist report count", "Rank by total crashes", "Selection reason",
    "Data period", "Selected area", "Requested investigation capacity", "Actual shortlist size",
    "Safety priorities", "Incident-indicator weight", "Increasing-activity weight",
    "Recent-crash multiplier", "Deerfoot/Stoney excluded", "Road scope", "Data status",
]


def shortlist_csv(result):
    """Return Excel-friendly UTF-8 bytes and a filename based on actual area and size."""
    settings = planning.from_result(result)
    w, c = settings["weights"], settings["constraints"]
    rows = ui.recommended_rows(result)
    area = f"{ui.REGIONS[c['region']]} Calgary" if c["region"] else "All Calgary"
    sample = not bool(result.get("plan"))
    records = []
    for row in rows:
        records.append({
            "Rank": row["rank"], "Location": row["name"],
            "Latitude": row["lat"], "Longitude": row["lon"],
            "Reported crash count": row["incidents"],
            "Pedestrian/cyclist report count": row["pedestrian_or_cyclist"],
            "Rank by total crashes": row["baseline_rank"],
            "Selection reason": ui.location_reason(row, result),
            "Data period": "January–December 2025", "Selected area": area,
            "Requested investigation capacity": c["budget"], "Actual shortlist size": len(rows),
            "Safety priorities": planning.priority_description(settings),
            "Incident-indicator weight": w["w_severity"], "Increasing-activity weight": w["w_trend"],
            "Recent-crash multiplier": c["recent_weight"],
            "Deerfoot/Stoney excluded": w["exclude_provincial"],
            "Road scope": "Exclude Deerfoot/Stoney by location name" if w["exclude_provincial"] else "Include Deerfoot/Stoney",
            "Data status": "Sample output (engine not connected)" if sample else "Current engine result",
        })
    data = pd.DataFrame(records, columns=COLUMNS).to_csv(index=False).encode("utf-8-sig")
    region = c["region"] or "AllCalgary"
    suffix = "_sample" if sample else ""
    filename = f"calgary_investigation_shortlist_2025_{region}_top{len(rows)}{suffix}.csv"
    return data, filename
