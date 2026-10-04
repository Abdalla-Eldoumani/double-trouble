from html import escape
from base64 import b64encode
from functools import lru_cache
from pathlib import Path

CSS_PATH = Path(__file__).resolve().parent / "style.css"
REGIONS = {"NE": "Northeast", "NW": "Northwest", "SE": "Southeast", "SW": "Southwest"}
PHOTO_CREDITS = ("Page photographs (illustrative scenes outside Calgary): "
                 "[Frak Lopez / Unsplash](https://unsplash.com/photos/FI_jpaK_fzQ), "
                 "[Unsplash License](https://unsplash.com/license); "
                 "[Life Of Pix / Pexels](https://www.pexels.com/photo/man-wearing-hard-hat-standing-8159/), "
                 "[Pexels License](https://www.pexels.com/license/). Cropped and resized for this page.")


def theme_css(dark=False):
    """Session-local palette; never mutates Streamlit's process-wide config."""
    palette = ("--paper:#171e25;--paper-deep:#27323d;--card:#202a34;"
               "--ink:#f0f4f8;--ink-soft:#c1ccd6;--ink-faint:#aebcc9;--rule:#465666;"
               "--signal:#ff887b;--signal-wash:#392b30;--same:#8194a6;"
               "--road-opacity:.10;--road-overlay:rgba(23,30,37,.40);--equipment-filter:brightness(.88);"
               "--slider-track-filter:brightness(1.6);color-scheme:dark;" if dark else
               "--paper:#f4f6f8;--paper-deep:#e8edf2;--card:#ffffff;"
               "--ink:#202830;--ink-soft:#52606d;--ink-faint:#52606d;--rule:#d4dce4;"
               "--signal:#b7322c;--signal-wash:#fcebea;--same:#738393;"
               "--road-opacity:.12;--road-overlay:rgba(244,246,248,.25);--equipment-filter:none;"
               "--slider-track-filter:none;color-scheme:light;")
    # :root also reaches menus and tooltips mounted outside the app container.
    # Read on reruns: the running checkout must not retain import-time CSS.
    road = photo_uri("road-intersection-frak-lopez.jpg")
    return (CSS_PATH.read_text() + "\n:root {" + palette + "}"
            + ('\n[data-testid="stMainBlockContainer"]::before {background-image: '
               f'linear-gradient(var(--road-overlay), var(--road-overlay)), url("{road}");}}' if road else ""))


@lru_cache(maxsize=2)
def photo_uri(filename):
    """Embed small local JPEGs; missing assets leave a clean, usable header."""
    path = Path(__file__).resolve().parent / "assets" / filename
    return "data:image/jpeg;base64," + b64encode(path.read_bytes()).decode() if path.is_file() else ""


def esc(value):
    return escape(str(value), quote=True)


def recommended_rows(result):
    rows = sorted(result["top20"], key=lambda r: r["rank"])
    if result.get("plan"):
        keys = set(result["plan"]["shortlist"])
        rows = [r for r in rows if r["location_key"] in keys]
    return rows


def current_settings(settings):
    from app.planning import summary
    return f'<div class="dt settings-summary">Current settings: {esc(summary(settings))}</div>'


def location_reason(row, result=None, compact=False):
    parts = [f"Recorded {row['incidents']} crashes, including {row['pedestrian_or_cyclist']} reports involving pedestrians or cyclists."]
    indicators = []
    for key, label in (("multi_vehicle", "multi-vehicle reports"), ("multiple_lanes", "reports of multiple blocked lanes")):
        if row.get(key):
            indicators.append(f"{row[key]} {label}")
    if indicators:
        parts.append("Also recorded " + " and ".join(indicators) + ".")
    if result:
        w = result["weights"]
        recent = result.get("plan", {}).get("constraints", {}).get("recent_weight", 1)
        if compact:
            priorities = []
            if w["w_severity"]:
                priorities.append("incident indicators")
            if w["w_trend"]:
                priorities.append("increasing activity")
            if recent != 1:
                priorities.append("July–December reports")
            parts.append("Additional importance for " + ", ".join(priorities) + "." if priorities else
                         "Selected by total reported crashes.")
            return " ".join(parts)
        if w["w_severity"]:
            parts.append("Incident indicators receive additional importance in this ranking.")
        elif not w["w_trend"] and recent == 1:
            parts.append("Selected by total reported crashes.")
        if (recent != 1 or w["w_trend"]) and {"early", "late"} <= row.keys():
            parts.append(f"January–June: {row['early']} crashes; July–December: {row['late']}.")
            if recent != 1:
                parts.append(f"July–December reports receive {recent:g}× importance.")
            if w["w_trend"]:
                parts.append("The ranking also considers the ratio of later to earlier activity.")
    return " ".join(parts)


def text_briefing(result):
    rows = recommended_rows(result)
    if not rows:
        return "No locations qualify for the current settings."
    return " ".join(f"#{r['rank']}, {r['name']}. {location_reason(r, result)}" for r in rows[:5])


def location_evidence(row, result):
    """Compact observed counts, selected for the criteria actually applied."""
    facts = []
    if "incidents" in row:
        facts.append(f"{row['incidents']} reported crashes")
    if "pedestrian_or_cyclist" in row:
        facts.append(f"{row['pedestrian_or_cyclist']} pedestrian/cyclist reports")
    if result["weights"]["w_severity"]:
        for key, label in (("multi_vehicle", "multi-vehicle reports"),
                           ("multiple_lanes", "reports of multiple blocked lanes")):
            if row.get(key):
                facts.append(f"{row[key]} {label}")
    recent = result.get("plan", {}).get("constraints", {}).get("recent_weight", 1)
    if (recent != 1 or result["weights"]["w_trend"]) and {"early", "late"} <= row.keys():
        facts.append(f"January–June: {row['early']} crashes; July–December: {row['late']}")
    return "; ".join(facts) + "." if facts else "Incident detail is unavailable in this sample output."


def summary_reason(row, result):
    """One factual reason per leading recommendation, with no technical score."""
    if result["weights"]["w_severity"]:
        return location_evidence(row, result)
    if (result["weights"]["w_trend"] or
            result.get("plan", {}).get("constraints", {}).get("recent_weight", 1) != 1):
        return location_evidence(row, result)
    return f"{row['incidents']} reported crashes; selected by total crash reports."


def summary_details(result):
    """Shared applied area, priorities, road scope and rows for text and speech."""
    from app import planning

    settings = planning.from_result(result)
    c, w = settings["constraints"], settings["weights"]
    rows = recommended_rows(result)
    area = f"{REGIONS[c['region']]} Calgary" if c["region"] else "All Calgary"
    road_scope = "Deerfoot and Stoney excluded by location name" if w["exclude_provincial"] else "Deerfoot and Stoney included"
    return {"area": area, "rows": rows, "road_scope": road_scope,
            "priorities": planning.priority_description(settings), "settings": settings}


def recommendation_summary(result):
    details = summary_details(result)
    rows, area, road_scope = details["rows"], details["area"], details["road_scope"]
    overview = f"{len(rows)} locations recommended in {area} · {road_scope}."
    items = "".join(f'<li><b>{esc(r["name"])}</b> — {esc(summary_reason(r, result))}</li>' for r in rows[:3])
    body = f'<ul>{items}</ul>' if rows else '<p>No locations qualify for the applied area and road scope.</p>'
    return ('<div class="dt recommendation-summary" role="region" aria-label="Recommendation summary">'
            '<h3 id="recommendation-summary">Recommendation summary</h3>'
            f'<p>{esc(overview)}</p><p>Applied priorities: {esc(details["priorities"])}.</p>'
            f'{body}<div class="summary-note">Location counts cover January–December 2025. '
            'The crash total above covers the full cleaned dataset, before area and road filters.</div></div>')


NO_MOVEMENT = "Your selected priorities recommend the same locations in the same order."
PRIORITY_NOTE = "These changes reflect your selected priorities, not changes in actual crash frequency."


def recommendation_change(result):
    """Compare ordered recommendations, not just mover metadata or shared ranks."""
    current = [r["location_key"] for r in recommended_rows(result)]
    base = (result["plan"]["baseline_shortlist"] if result.get("plan") else
            [r["location_key"] for r in result["baseline"]["top20"][:len(current)]])
    if current == base:
        return NO_MOVEMENT
    if set(current) == set(base):
        return "Your selected priorities recommend the same locations in a different order."
    added, removed = len(set(current) - set(base)), len(set(base) - set(current))
    return f"Your selected priorities change the recommended locations: {added} entered and {removed} left the shortlist."


def priority_effect(row, result):
    """Explain only applied score signals, without attributing a move to one signal."""
    w = result["weights"]
    c = result.get("plan", {}).get("constraints", {})
    effects = []
    if w["w_severity"]:
        indicators = []
        for key, label in (("pedestrian_or_cyclist", "pedestrian/cyclist reports"),
                           ("multi_vehicle", "multi-vehicle reports"),
                           ("multiple_lanes", "reports of multiple blocked lanes")):
            if row.get(key):
                indicators.append(f"{row[key]} {label}")
        if indicators:
            effects.append("Your incident priorities give additional importance to this location’s "
                           + ", ".join(indicators) + ".")
        elif all(key in row for key in ("pedestrian_or_cyclist", "multi_vehicle", "multiple_lanes")):
            effects.append("No additional incident indicators are recorded here; other locations can receive extra importance for those reports.")
    if w["w_trend"] and {"early", "late"} <= row.keys():
        effects.append(f"Reports went from {row['early']} in January–June to {row['late']} in July–December; "
                       "your priorities also consider later activity relative to earlier activity.")
    if c.get("recent_weight", 1) != 1 and "late" in row:
        effects.append(f"Its {row['late']} July–December reports receive {c['recent_weight']:g}× importance in crash counts and indicator points.")
    return " ".join(effects) or "Its position reflects the combined applied priorities relative to other eligible locations."


def changed_locations(result):
    """Actual movers across either top 20, including locations outside today's shortlist."""
    changes, seen = [], set()
    for mover in result["movers"]:
        key = mover["location_key"]
        if mover["from_rank"] != mover["to_rank"] and key not in seen:
            changes.append(mover)
            seen.add(key)
        if len(changes) == 3:
            break
    return changes


def ranking_changes(result, name_of):
    changes = changed_locations(result)
    context = recommendation_change(result)
    if not changes:
        if not result.get("plan") and any(r["rank"] != r["baseline_rank"] for r in result["top20"]):
            # The legacy sample has contradictory ranks and unchanged mover entries.
            return '<div class="dt empty">No consistent ranking-change details are available in this sample output.</div>'
        return f'<div class="dt empty">{esc(context)}</div>'
    current = {r["location_key"]: r for r in result["top20"]}
    baseline = {r["location_key"]: r for r in result["baseline"]["top20"]}
    selected = {r["location_key"] for r in recommended_rows(result)}
    cards = []
    for mover in changes:
        key = mover["location_key"]
        # Existing contracts need not include the optional counts on movers.
        evidence = {**baseline.get(key, {}), **current.get(key, {}), **mover}
        direction = "Moved higher" if mover["to_rank"] < mover["from_rank"] else "Moved lower"
        cards.append(
            '<article class="ranking-change">'
            f'<h3>{esc(name_of(key))}</h3>'
            f'<p>{esc(priority_effect(evidence, result))}</p>'
            f'<div class="rank-note">{direction}: #{mover["from_rank"]} → #{mover["to_rank"]} '
            '(total crashes → selected priorities).'
            + (' Outside the current shortlist.' if key not in selected else '')
            + '</div></article>'
        )
    from app import planning
    criteria = planning.priority_description(planning.from_result(result))
    return ('<div class="dt ranking-changes"><div class="change-context">'
            f'{esc(context)} Applied priorities: {esc(criteria)}. '
            'The rank details compare the two top-20 lists, including locations outside your shortlist. '
            'Positions depend on the combined criteria and other eligible locations.</div>'
            + "".join(cards) + f'<p class="rank-note">{PRIORITY_NOTE}</p></div>')


def validation(result):
    """Display shares and signed differences, retaining negative and undefined outcomes."""
    m, plan = result["metrics"], result.get("plan")
    out = ['<div class="dt validation"><p>We select locations using an earlier period, then measure '
           'incident-based proxy points recorded at those locations in a later period.</p>'
           '<p>The custom severity score is a description-based proxy: 1 point per crash, '
           '+3 for pedestrian/cyclist involvement, +1 for multi-vehicle involvement, and +1 for '
           'multiple blocked lanes. Indicators can overlap. These are not injury counts or verified injury-severity measurements.</p>']

    def comparison(label, base, current, total=None):
        if total == 0:
            shares = "Total crashes: not available · Current priorities: not available"
            diff = "Difference: not available (no evaluation-period proxy points)."
        else:
            shares = f"Total crashes: {base:.2%} · Current priorities: {current:.2%}"
            diff = f"Difference: {_signed(100 * (current - base))} percentage points."
        return f'<div class="validation-row"><b>{esc(label)}</b><div>{shares}</div><div>{diff}</div></div>'

    if plan:
        total = plan["points_total"]
        base = plan["points_baseline"] / total if total else 0
        current = plan["points_agent"] / total if total else 0
        out.append(comparison(f"Primary validation · up to {plan['constraints']['budget']} locations · January–August → September–December 2025", base, current, total))
        gap = plan["points_agent"] - plan["points_baseline"]
        out.append(f'<p>Total crashes: {plan["points_baseline"]} proxy points; current priorities: {plan["points_agent"]} '
                   f'of {total} eligible later-period proxy points. Difference: {_signed(gap, 0)} proxy points.</p>')
        if plan["points_baseline"]:
            change = 100 * gap / plan["points_baseline"]
            out.append(f'<p>Relative change in proxy points: {_signed(change)}% (different from the percentage-point difference in shares).</p>')
        else:
            out.append('<p>Relative percentage change is not available because the baseline has zero proxy points.</p>')
        overlap = len(set(plan["shortlist"]) & set(plan["baseline_shortlist"]))
    else:
        overlap = len({r["location_key"] for r in recommended_rows(result)} &
                      {r["location_key"] for r in result["baseline"]["top20"]})
    out.append(f'<p>Top-list overlap: {overlap} of {len(recommended_rows(result))} recommended locations also appear in the equivalent crash-total list.</p>')
    out.append(comparison("Primary validation · up to 20 locations · January–August → September–December 2025",
                          m["backtest_baseline"], m["backtest_agent"], m.get("backtest_points_total")))
    if {"check_baseline", "check_agent"} <= m.keys():
        out.append(comparison("Secondary validation · up to 20 locations · January–June → July–December 2025",
                              m["check_baseline"], m["check_agent"], m.get("check_points_total")))
        out.append('<p>The secondary split is not used by the automatic search. Its months overlap the primary evaluation; '
                   'it is not an independent holdout test.</p>')
    out.append('<p>Automatic search uses the primary evaluation to choose weights, so its result is a tuning result. '
               'For validation, recency multiplies the later half of each training window: May–August in the primary split '
               'and April–June in the secondary split. Evaluation points are unweighted. '
               'These historical checks do not demonstrate crash reduction, identify the best intervention, or establish future performance.</p></div>')
    return "".join(out)


def masthead():
    return (
        '<div class="dt mast"><div><span class="dot"></span>Calgary road safety'
        '<span class="muted"> &middot; 2025 traffic incident feed</span></div>'
        '<div class="muted">Double Trouble &middot; IEEE YP Industry Hackathon 2026</div></div>'
    )


def hero(title, lede, data):
    before, accent, after = title
    equipment = photo_uri("safety-vest-hardhat-life-of-pix.jpg")
    imagery = (f'<img class="hero-equipment" src="{equipment}" alt="" aria-hidden="true" width="320" height="320">' if equipment else "")
    return (
        '<div class="dt hero"><div class="hero-copy"><div class="title" role="heading" aria-level="1">'
        f'{esc(before)}<em>{esc(accent)}</em>{esc(after)}</div>'
        f'<div class="hero-side"><div class="lede">{esc(lede)}</div></div></div>{imagery}</div>'
    )


def _signed(value, digits=2):
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.{digits}f}" if digits else f"{sign}{abs(value)}"


def _pair(base_label, base, agent_label, agent, fmt):
    top = max(base, agent) or 1
    return (
        '<div class="pair">'
        f'<span class="pl">{base_label}</span><span class="pb"><i style="width:{100 * base / top:.1f}%"></i></span>'
        f'<span class="pv">{fmt(base)}</span>'
        f'<span class="pl">{agent_label}</span><span class="pb us"><i style="width:{100 * agent / top:.1f}%"></i></span>'
        f'<span class="pv">{fmt(agent)}</span></div>'
    )


def plan_active(plan):
    c = (plan or {}).get("constraints")
    return bool(c) and (c["budget"] != 20 or bool(c["region"]) or c["recent_weight"] != 1)


def figures(result):
    rows = recommended_rows(result)
    plan = result.get("plan")
    baseline = (plan["baseline_shortlist"] if plan else
                [r["location_key"] for r in result["baseline"]["top20"][:len(rows)]])
    beyond = len({r["location_key"] for r in rows} - set(baseline))
    cells = [
        ("Reported crashes analyzed", f'{result["dataset"]["rows_used"]:,}', "Full 2025 dataset after cleaning; before area and road filters."),
        ("Locations recommended", str(len(rows)), "The current shortlist within your investigation capacity."),
        ("Selected beyond crash totals", str(beyond), "These locations enter the shortlist when your additional priorities are considered."),
    ]
    out = []
    for label, value, note in cells:
        out.append(f'<div class="fig"><div class="fig-label">{esc(label)}</div>'
                   f'<div class="fig-value">{value}</div><div class="fig-note">{esc(note)}</div></div>')
    return '<div class="dt figures">' + "".join(out) + "</div>"


def recommendation_link():
    """Make the single, below-controls summary discoverable from the opening view."""
    return ('<div class="dt recommendation-link">'
            '<a href="#recommendation-summary">View current recommendations ↓</a></div>')


def section(number, title, note=""):
    note_html = f'<div class="sec-note">{note}</div>' if note else ""
    return ('<div class="dt sec">'
            f'<div class="sec-title" role="heading" aria-level="2">{esc(title)}</div>{note_html}</div>')


def card_head(title, note="", state="", agent_set=False):
    chip = f'<div class="ctl-state{" agent" if agent_set else ""}">{esc(state)}</div>' if state else ""
    note_html = f'<div class="card-note">{esc(note)}</div>' if note else ""
    return f'<div class="dt ctl-head"><div class="ctl-title">{esc(title)}</div>{chip}</div>{note_html}'


def plan_tags(plan):
    if not plan_active(plan):
        return ""
    c = plan["constraints"]
    tags = [f"Top {c['budget']}", f"{REGIONS[c['region']]} only" if c["region"] else "All of Calgary"]
    if c["recent_weight"] != 1:
        tags.append(f"Jul-Dec crashes x{c['recent_weight']:g}")
    return '<div class="dt tags">' + "".join(f"<span>{esc(t)}</span>" for t in tags) + "</div>"


def reply(rep):
    return (f'<div class="dt reply"><div class="reply-ask">You asked: <q>{esc(rep["request"])}</q></div>'
            f'<div class="reply-text">{esc(rep["text"])}</div></div>')


def legend():
    return ('<div class="dt legend"><span><i class="up"></i>Moved up</span>'
            '<span><i class="down"></i>Moved down</span><span><i class="same"></i>Same rank</span>'
            '<span>Larger circle, higher harm score</span></div>')


def _delta(was, rank):
    if was > rank:
        return f"\u2191{was - rank}", "up"
    if was < rank:
        return f"\u2193{rank - was}", "down"
    return "=", "same"


def shortlist(rows, result=None):
    out = ['<div class="dt ledger"><div class="lg-head"><span>Rank</span><span>Location and reported incidents</span></div>']
    for r in rows:
        out.append(
            f'<div class="lg-row"><span class="lg-rank">{r["rank"]}</span><div>'
            f'<span class="lg-name">{esc(r["name"])}</span>'
            f'<div class="lg-detail">{esc(location_reason(r, result, compact=True))}</div></div></div>'
        )
    return "".join(out) + "</div>"


def movers(result, name_of):
    rows = recommended_rows(result)[:3]
    if not rows:
        return '<div class="dt empty">There are no recommended locations to explain at these settings.</div>'
    cards = []
    for i, r in enumerate(rows):
        cards.append(
            f'<article class="mover{" lead" if i == 0 else ""}">'
            f'<div class="mover-dir">Recommendation #{r["rank"]}</div>'
            f'<div class="mover-name">{esc(name_of(r["location_key"]))}</div>'
            f'<div class="mover-why">{esc(location_reason(r, result))}</div>'
            f'<div class="rank-note">Ranked #{r["rank"]} with your priorities; '
            f'#{r["baseline_rank"]} by total crashes.</div></article>'
        )
    return '<div class="dt movers">' + "".join(cards) + "</div>"


def _clip(text, limit=46):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def slope(result, name_of, n=20):
    """Count-only rank on the left, harm rank on the right, one line per location."""
    row, top, width = 31, 54, 1240
    left_x, right_x = 500, 740
    base = [b["location_key"] for b in result["baseline"]["top20"][:n]]
    base_rank = {k: i for i, k in enumerate(base, start=1)}
    harm = {r["location_key"]: r for r in result["top20"] if r["rank"] <= n}
    rows = max(len(base), len(harm), 1)
    gutter = top + rows * row + 14

    def y(rank):
        return top + (rank - 1) * row

    def curve(y1, y2):
        mid = (left_x + right_x) / 2
        return f"M{left_x + 8} {y1 - 5} C{mid} {y1 - 5},{mid} {y2 - 5},{right_x - 8} {y2 - 5}"

    movers = {m["location_key"] for m in result["movers"]}
    parts = [
        f'<svg class="dt slope" viewBox="0 0 {width} {gutter + 30}" role="img" '
        f'aria-label="Top {n} by total crashes compared with current priorities">',
        '<text class="head" x="0" y="20">Total crashes</text>',
        f'<text class="head" x="{width}" y="20" text-anchor="end">Current priorities</text>',
    ]
    for i in range(rows):
        if i % 2 == 0:
            parts.append(f'<rect class="band" x="0" y="{y(i + 1) - 21}" width="{width}" height="{row}" rx="4"/>')

    delay = 0
    for key, rank in base_rank.items():
        cls = "nm" if key in harm else "nm gone"
        parts.append(f'<text class="rk" x="26" y="{y(rank)}" text-anchor="end">{rank}</text>')
        parts.append(f'<text class="{cls}" x="40" y="{y(rank)}">{esc(_clip(name_of(key), 56))}</text>')
        if key in harm:
            to = harm[key]["rank"]
            kind = "up" if to < rank else "down" if to > rank else "same"
            key_cls = " key" if key in movers else ""
            parts.append(f'<path class="{kind}{key_cls}" d="{curve(y(rank), y(to))}" '
                         f'style="animation-delay:{delay}ms"/>')
        else:
            parts.append(f'<path class="gone" d="{curve(y(rank), gutter)}"/>')
        delay += 35

    for key, r in harm.items():
        rank, was = r["rank"], r["baseline_rank"]
        new = key not in base_rank
        parts.append(f'<text class="rk" x="{right_x + 30}" y="{y(rank)}" text-anchor="end">{rank}</text>')
        parts.append(f'<text class="nm{" new" if new else ""}" x="{right_x + 44}" '
                     f'y="{y(rank)}">{esc(_clip(r["name"], 50))}</text>')
        delta, kind = _delta(was, rank)
        parts.append(f'<text class="dl {kind}" x="{width}" y="{y(rank)}" text-anchor="end">{delta}</text>')
        if new:
            key_cls = " key" if key in movers else ""
            parts.append(f'<path class="up{key_cls}" d="{curve(gutter, y(rank))}" '
                         f'style="animation-delay:{delay}ms"/>')
            delay += 35

    parts.append(f'<text class="gut" x="{left_x}" y="{gutter + 4}" text-anchor="end">below {n}</text>')
    parts.append(f'<text class="gut" x="{right_x}" y="{gutter + 4}">below {n}</text>')
    parts.append("</svg>")
    return "".join(parts)


def trace(tuned):
    its = tuned["agent_iterations"]
    top = max(it["backtest_metric"] for it in its) or 1
    chosen = next((it["iteration"] for it in its if it["weights"] == tuned["weights"]), None)
    cells = ['<div class="th">Step</div><div class="th">Indicators</div><div class="th">Increasing activity</div>'
             '<div class="th">Share of later proxy points</div><div class="th">Decision</div>']
    for it in its:
        w = it["weights"]
        state = "chosen" if it["iteration"] == chosen else "kept" if it["note"].startswith(("kept", "baseline")) else ""
        tag = '<span class="tag">chosen</span>' if state == "chosen" else ""
        width = 100 * it["backtest_metric"] / top
        share = "N/A" if tuned["metrics"].get("backtest_points_total") == 0 else f'{it["backtest_metric"]:.2%}'
        note = it["note"]
        if tuned.get("plan", {}).get("constraints", {}).get("recent_weight", 1) != 1:
            # Zero indicator/trend weights still apply recency during this candidate search.
            note = note.replace("count-only", "zero indicator/activity weights")
        cells.append(
            f'<div class="td num {state}">{it["iteration"]:02d}</div>'
            f'<div class="td num {state}">{w["w_severity"]:.2f}</div>'
            f'<div class="td num {state}">{w["w_trend"]:.2f}</div>'
            f'<div class="td bar-cell {state}"><div class="bar"><i style="width:{width:.1f}%;'
            f'animation-delay:{40 * it["iteration"]}ms"></i><b>{share}</b></div></div>'
            f'<div class="td note {state}">{esc(note)}{tag}</div>'
        )
    return '<div class="dt trace">' + "".join(cells) + "</div>"


def briefing(script, note):
    return (f'<div class="dt brief"><div class="transcript">{esc(script)}</div>'
            f'<div class="brief-note">{esc(note)}</div></div>')


def footer(claim, drop_reason):
    meta = f'<div class="foot-meta">Rows set aside: {esc(drop_reason)}</div>' if drop_reason else ""
    return (f'<div class="dt foot"><div class="foot-claim">{esc(claim)}</div>'
            f'{meta}</div>')
