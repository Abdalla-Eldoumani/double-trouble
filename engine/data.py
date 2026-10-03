"""Load the Calgary traffic incident feed, drop non-crash rows, assign a location key."""

import re
from pathlib import Path

import pandas as pd

CSV = Path(__file__).resolve().parent.parent / "data" / "calgary_traffic_incidents_2025.csv"

SOURCE = (
    "City of Calgary, Open Calgary Traffic Incidents (2025 subset bundled with IEEE YP "
    "hackathon Case 5). The City's incident feed, not a complete police collision database. "
    "Contains information licensed under the Open Government Licence - City of Calgary."
)

# The first sentence of a description names the event type.
NON_CRASH = (
    r"^(?:stalled vehicle|traffic signal|power outage|road work|water main"
    r"|severe weather|hazardous road|lrt gates)|police|oversized load"
)
DROP_REASON = (
    "non-crash rows: the description's first sentence reports a stalled vehicle, a traffic "
    "signal fault or works, a power outage, road work, a water main, weather or a road "
    "hazard, stuck LRT gates, a police operation or a planned closure"
)

ABBREVIATIONS = {
    "av": "avenue", "ave": "avenue", "blvd": "boulevard", "cl": "close", "cr": "crescent",
    "ct": "court", "dr": "drive", "ga": "gate", "gr": "green", "hwy": "highway",
    "ln": "lane", "pl": "place", "py": "parkway", "rd": "road", "st": "street",
    "tr": "trail", "wy": "way",
}
# "soutbound" is a typo in the feed; ramps and exits belong to the interchange they serve.
DIRECTION = re.compile(r"\b(?:north|south?|east|west)bound\b|\b(?:exit|ramp)\b")
CONNECTOR = re.compile(
    r"\s+(?:and|at|approaching|after|before|near|past|between|b/w|to|onto|on"
    r"|(?:north|south|east|west) of)\s+"
)
QUADRANT = re.compile(r"\s+(ne|nw|se|sw|n|s|e|w)$")


def normalize(text: pd.Series) -> pd.Series:
    return text.str.lower().str.replace(r"\s+", " ", regex=True).str.strip()


def location_key(info: str) -> str:
    """'Northbound Deerfoot Trail approaching Glenmore Trail SE' -> 'deerfoot trail & glenmore trail se'.

    Street order is sorted so 'A and B' and 'B and A' are one intersection. The quadrant
    stays in the key because 17 Avenue and 36 Street exists in both SE and SW.
    """
    s = DIRECTION.sub("", " ".join(info.lower().split())).strip()
    m = QUADRANT.search(s)
    s = QUADRANT.sub("", s)
    streets = {
        " ".join(ABBREVIATIONS.get(w, w) for w in part.split())
        for part in CONNECTOR.split(s)
        if part.strip()
    }
    return " & ".join(sorted(streets)) + (f" {m.group(1)}" if m else "")


def load(path: Path = CSV) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv(path)
    if raw.empty:
        raise ValueError(f"{path} has no rows")
    missing = {"incident_info", "description", "start_dt", "quadrant", "longitude", "latitude"} - set(raw.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    # A row without a place cannot be ranked; the 2025 file has none but a refreshed feed may.
    located = raw.dropna(subset=["incident_info", "latitude", "longitude", "start_dt", "description"])

    desc = normalize(located["description"])
    drop = desc.str.split(".", n=1).str[0].str.contains(NON_CRASH, regex=True)
    df = located[~drop].assign(
        description=desc[~drop],
        name=located["incident_info"].str.strip(),
        start_dt=pd.to_datetime(located["start_dt"][~drop]),
    )
    df["location_key"] = df["name"].map(location_key)

    info = {
        "source": SOURCE,
        "rows_loaded": len(raw),
        "rows_dropped": len(raw) - len(df),
        "drop_reason": DROP_REASON,
        "rows_used": len(df),
        "rows_without_location": len(raw) - len(located),
        "drop_examples": located.loc[drop, "description"].drop_duplicates().head(5).tolist(),
    }
    return df, info


if __name__ == "__main__":
    df, info = load()
    for k, v in info.items():
        print(f"{k}: {v}")
    keys = df["location_key"].value_counts()
    print(f"\nname keys: {len(keys)}  incidents per key: {len(df) / len(keys):.2f}")
    print(keys.head(10).to_string())
    cells = (df["latitude"].round(3).astype(str) + "," + df["longitude"].round(3).astype(str)).value_counts()
    print(f"\nlat/lon 3-decimal cells: {len(cells)}  incidents per cell: {len(df) / len(cells):.2f}")
    print(cells.head(10).to_string())
