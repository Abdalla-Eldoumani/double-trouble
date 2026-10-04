"""Presentation defaults and presets; the ranking engine remains authoritative."""

DEFAULT_WEIGHTS = {"w_severity": 0.0, "w_trend": 0.0, "exclude_provincial": True}
DEFAULT_CONSTRAINTS = {"recent_weight": 1.0, "region": None, "budget": 20}
AREA_OPTIONS = {"ALL": "All Calgary", "NW": "Northwest", "NE": "Northeast",
                "SW": "Southwest", "SE": "Southeast"}


def engine_region(area):
    """Translate the explicit UI selection without changing the engine contract."""
    if area not in AREA_OPTIONS:
        raise ValueError(f"Unknown area: {area!r}")
    return None if area == "ALL" else area


def ui_region(region):
    return "ALL" if region is None else region


def widget_values(settings):
    """One-way mirrors of authoritative applied settings, before widget creation."""
    c = settings["constraints"]
    return {**settings["weights"], "area": ui_region(c["region"]),
            "capacity": c["budget"], "recent_weight": c["recent_weight"],
            "priorities": preset_name(settings)}


PRESETS = {
    "Crash totals": (0.0, 0.0, 1.0),
    "Balanced priorities": (0.5, 0.5, 1.0),
    "Pedestrians and cyclists": (1.0, 0.0, 1.0),
    "Recent activity": (0.0, 0.0, 2.0),
}
PRESET_NOTES = {
    "Crash totals": "Ranks by the total number of reported crashes in 2025.",
    "Balanced priorities": "Combines crash totals and incident indicators, with additional importance for increasing activity.",
    "Pedestrians and cyclists": "Adds importance to pedestrian and cyclist reports, and also to multi-vehicle and blocked-lane indicators.",
    "Recent activity": "Gives July–December crashes twice the importance of January–June crashes.",
    "Custom priorities": "Your planner request or advanced weights do not match a preset.",
}


def preset_name(settings):
    w, c = settings["weights"], settings["constraints"]
    values = (w["w_severity"], w["w_trend"], c["recent_weight"])
    return next((label for label, preset in PRESETS.items() if values == preset), "Custom priorities")


def from_result(result):
    return {"weights": dict(result["weights"]),
            "constraints": dict(result.get("plan", {}).get("constraints", DEFAULT_CONSTRAINTS))}


def priority_description(settings):
    """Readable applied criteria, including custom settings, without implying a filter."""
    w, c = settings["weights"], settings["constraints"]
    criteria = []
    if w["w_severity"]:
        criteria.append("pedestrian/cyclist, multi-vehicle and blocked-lane indicators")
    if w["w_trend"]:
        criteria.append("increasing crash activity")
    if c["recent_weight"] != 1:
        criteria.append(f"July–December 2025 reports weighted {c['recent_weight']:g}×")
    label = preset_name(settings)
    return label + (": " + "; ".join(criteria) if criteria else "")


def summary(settings):
    from app.ui import REGIONS

    w, c = settings["weights"], settings["constraints"]
    area = f"{REGIONS[c['region']]} Calgary" if c["region"] else "All Calgary"
    parts = [area, f"Up to {c['budget']} locations", preset_name(settings)]
    if c["recent_weight"] != 1:
        times = "twice" if c["recent_weight"] == 2 else f"{c['recent_weight']:g} times"
        parts.append(f"July–December incidents given {times} the importance")
    if preset_name(settings) == "Custom priorities":
        if w["w_severity"]:
            parts.append("Additional importance for incident indicators")
        if w["w_trend"]:
            parts.append("Additional importance for increasing activity")
    parts.append("Deerfoot and Stoney excluded" if w["exclude_provincial"] else "Deerfoot and Stoney included")
    return " · ".join(parts)


def confirmation(asked, settings):
    """Short spoken reply: requested fields, using only their applied values."""
    w, c = settings["weights"], settings["constraints"]
    weight_fields, constraint_fields = asked["weights"], asked["constraints"]
    area = f"{AREA_OPTIONS[c['region']].lower()} Calgary" if c["region"] else "all Calgary"
    if asked["reset"]:
        roads = "excluded" if w["exclude_provincial"] else "included"
        return (f"Got it. Reset to {area}, up to {c['budget']} locations, "
                f"{preset_name(settings).lower()}, with Deerfoot and Stoney {roads}.")
    if asked["tune"]:
        weight_fields = {**weight_fields, "w_severity": w["w_severity"], "w_trend": w["w_trend"]}
    parts = []
    if "budget" in constraint_fields:
        parts.append(f"Showing up to {c['budget']} locations in {area}")
    elif "region" in constraint_fields:
        parts.append(f"Showing {area}" + (" only" if c["region"] else " again"))
    if "recent_weight" in constraint_fields:
        if c["recent_weight"] == 1:
            recency = "July to December crashes weighted the same as earlier crashes"
        else:
            times = "twice" if c["recent_weight"] == 2 else f"{c['recent_weight']:g} times"
            recency = f"July to December crashes weighted {times} as much"
        if parts:
            parts[-1] += ", with " + recency
        else:
            parts.append(recency)
    if "w_severity" in weight_fields:
        parts.append("Pedestrian, cyclist, multi-vehicle and blocked-lane reports " +
                     ("have added importance" if w["w_severity"] else "have no extra weighting"))
    if "w_trend" in weight_fields:
        parts.append("Increasing crash activity " +
                     ("has added importance" if w["w_trend"] else "has no extra weighting"))
    if "exclude_provincial" in weight_fields:
        parts.append("Deerfoot and Stoney " + ("excluded" if w["exclude_provincial"] else "included"))
    prefix = "Got it. Ranking options tested. " if asked["tune"] else "Got it. "
    return prefix + ". ".join(parts) + "."
