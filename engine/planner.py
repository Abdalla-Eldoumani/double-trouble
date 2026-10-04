"""Turn a spoken or typed planning request into engine settings, then explain what changed.

Rules, not a language model: every phrase it understands is listed here, it runs offline,
and the same words always give the same settings.
"""

import re

from engine.agent import DEFAULT_CONSTRAINTS, MAX_RECENT_WEIGHT, TOP_N

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
MULTIPLIERS = {
    "twice": 2, "double": 2, "two times": 2, "2x": 2, "2 times": 2,
    "three times": 3, "triple": 3, "3x": 3, "3 times": 3,
    "four times": 4, "4x": 4, "4 times": 4, "five times": 5, "5x": 5, "5 times": 5,
}
REGION_NAMES = {"NE": "northeast", "NW": "northwest", "SE": "southeast", "SW": "southwest"}
REGION_PATTERNS = {
    code: rf"\b(?:{name[:5]}[\s-]?{name[5:]}|{code.lower()})\b" for code, name in REGION_NAMES.items()
}
CITYWIDE = r"\b(?:all (?:of )?calgary|whole city|entire city|city[\s-]?wide|every quadrant|all quadrants|everywhere)\b"
BUDGET = (
    r"\b(?:top|only|just|budget (?:of|for)|investigate|visit|fix|afford|study|handle|look at|pick)"
    r"\s+(?:the\s+)?(?:top\s+)?(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\b"
    r"|\b(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\s+(?:intersections|locations|sites|spots|places)\b"
)
SEVERITY_ON = r"\b(?:pedestrian|cyclist|vulnerable|severity|severe|harm|injur\w*|serious)"
SEVERITY_OFF = r"\b(?:count only|just count|raw count|ignore severity|crash count only|only the count)\b"
PROVINCIAL_IN = r"\b(?:include|add|show|with)\s+(?:the\s+)?(?:provincial|highways?|deerfoot|stoney)"
PROVINCIAL_OUT = r"\b(?:exclude|without|drop|remove|hide|no)\s+(?:the\s+)?(?:provincial|highways?|deerfoot|stoney)|city roads only"
TUNE = r"\b(?:tune|optimi[sz]e|best weights|best ranking automatically|you (?:choose|pick|decide))\b"
RESET = r"\b(?:reset|start over|clear (?:everything|all|settings))\b"


def _number(token: str) -> int:
    return int(token) if token.isdigit() else NUMBER_WORDS[token]


def parse(text: str) -> dict:
    """Settings the request asks for, and a plain list of what was understood.

    Only settings the request mentions appear, so a follow-up ("now only northeast")
    keeps everything it does not mention.
    """
    t = " ".join(text.lower().replace("’", "'").split())
    constraints, weights, heard = {}, {}, []
    tune = False

    if re.search(RESET, t):
        return {"constraints": dict(DEFAULT_CONSTRAINTS), "weights": {}, "tune": False,
                "reset": True, "heard": ["reset to the default settings"]}

    if re.search(r"\brecen(?:t|cy)|\blately\b|\blatest\b", t):
        if re.search(r"\b(?:ignore|stop|no longer|don't|do not)\b[^.]*\brecen", t) or "equally" in t:
            constraints["recent_weight"] = 1.0
            heard.append("recent crashes count the same as older ones")
        else:
            factor = next((f for phrase, f in MULTIPLIERS.items() if re.search(rf"\b{re.escape(phrase)}\b", t)), None)
            if factor is None and re.search(r"\b(?:prioriti[sz]e|weight|favou?r|emphasi[sz]e|focus)\w*\b", t):
                factor = 2
            if factor is not None:
                factor = min(factor, MAX_RECENT_WEIGHT)
                constraints["recent_weight"] = float(factor)
                times = "twice" if factor == 2 else f"{factor:g} times"
                heard.append(f"crashes from July to December count {times}")

    if re.search(CITYWIDE, t):
        constraints["region"] = None
        heard.append("all of Calgary")
    else:
        found = [code for code, pattern in REGION_PATTERNS.items() if re.search(pattern, t)]
        if len(found) == 1:
            constraints["region"] = found[0]
            heard.append(f"{REGION_NAMES[found[0]]} Calgary only")
        elif len(found) > 1:
            heard.append("more than one quadrant named, so the area was left unchanged")

    m = re.search(BUDGET, t)
    if m:
        asked = _number(m.group(1) or m.group(2))
        budget = max(1, min(asked, TOP_N))
        constraints["budget"] = budget
        heard.append(f"a budget of {budget} intersections" + (f" (the most it ranks is {TOP_N})" if asked > TOP_N else ""))

    if re.search(SEVERITY_OFF, t):
        weights["w_severity"] = 0.0
        heard.append("rank by crash count only")
    elif re.search(SEVERITY_ON, t):
        weights["w_severity"] = 1.0
        heard.append("rank by harm, so pedestrian, cyclist and multi-vehicle crashes weigh more")

    if re.search(PROVINCIAL_OUT, t):
        weights["exclude_provincial"] = True
        heard.append("City roads only, Deerfoot and Stoney left out")
    elif re.search(PROVINCIAL_IN, t):
        weights["exclude_provincial"] = False
        heard.append("Deerfoot and Stoney included")

    if re.search(TUNE, t):
        tune = True
        heard.append("let the agent pick the weights by backtest")

    return {"constraints": constraints, "weights": weights, "tune": tune, "reset": False, "heard": heard}


def display(key: str) -> str:
    """'mcknight boulevard & metis trail ne' -> 'McKnight Boulevard and Metis Trail NE'."""
    words = key.split()
    quadrant = words[-1].upper() if words and words[-1] in ("ne", "nw", "se", "sw", "n", "s", "e", "w") else ""
    out = []
    for w in words[:-1] if quadrant else words:
        if w == "&":
            out.append("and")
        elif w.startswith("mc") and len(w) > 2:
            out.append("Mc" + w[2:].capitalize())
        else:
            out.append(w.capitalize())
    return " ".join(out + [quadrant]).strip()


def _names(keys: list[str], limit: int = 3) -> str:
    # Spoken aloud, so long lists are cut rather than read in full.
    shown = ", ".join(display(k) for k in keys[:limit])
    return shown + (f", and {len(keys) - limit} more" if len(keys) > limit else "")


def compare(previous: dict | None, current: dict) -> dict:
    """Which locations entered, left or moved inside the shortlist, by key."""
    new = current["plan"]["shortlist"]
    if previous is None:
        return {"entered": [], "left": [], "moved": [], "first": True}
    old = previous["plan"]["shortlist"]
    moved = [(k, old.index(k) + 1, new.index(k) + 1) for k in new if k in old and old.index(k) != new.index(k)]
    return {
        "entered": [k for k in new if k not in old],
        "left": [k for k in old if k not in new],
        "moved": moved,
        "first": False,
        "previous_constraints": previous["plan"]["constraints"],
    }


def explain(current: dict, comparison: dict, heard: list[str]) -> str:
    """A short spoken summary built only from the numbers in the result."""
    plan = current["plan"]
    c = plan["constraints"]
    rows = {r["location_key"]: r for r in current["top20"]}
    where = f"{REGION_NAMES[c['region']]} Calgary" if c["region"] else "Calgary"
    parts = []
    if heard:
        parts.append("Got it: " + "; ".join(heard) + ".")
    else:
        parts.append("I did not catch a setting I can change, so the list is the same.")

    n = len(plan["shortlist"])
    lead = rows[plan["shortlist"][0]] if plan["shortlist"] else None
    if lead:
        detail = f"{lead['incidents']} incidents"
        if lead["pedestrian_or_cyclist"]:
            detail += f", {lead['pedestrian_or_cyclist']} with a pedestrian or cyclist"
        parts.append(f"Top of the {n} for {where}: {display(lead['location_key'])}, {detail}.")

    if not comparison["first"]:
        before = comparison["previous_constraints"]
        if (before["region"], before["budget"]) != (c["region"], c["budget"]):
            # A new area or budget replaces the whole list, so name the change, not every location.
            was = f"{REGION_NAMES[before['region']]} Calgary" if before["region"] else "Calgary"
            parts.append(f"That replaces the top {before['budget']} for {was}.")
        elif comparison["entered"] or comparison["left"]:
            if comparison["entered"]:
                parts.append(f"{len(comparison['entered'])} new: " + _names(comparison["entered"], 2) + ".")
            if comparison["left"]:
                parts.append(f"{len(comparison['left'])} dropped: " + _names(comparison["left"], 2) + ".")
        else:
            parts.append("Same locations as before" + (", in a new order." if comparison["moved"] else "."))

    gap = plan["points_agent"] - plan["points_baseline"]
    if gap > 0:
        verdict = f"{gap} more than a plain crash count"
    elif gap < 0:
        verdict = f"{-gap} fewer than a plain crash count"
    else:
        verdict = "the same as a plain crash count"
    parts.append(
        f"Backtest: ranked on January to August, this top {n} caught {plan['points_agent']} of "
        f"{plan['points_total']} September to December severity points, {verdict}."
    )
    return " ".join(parts)
