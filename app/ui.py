from html import escape
from pathlib import Path

CSS = (Path(__file__).resolve().parent / "style.css").read_text()
REGIONS = {"NE": "Northeast", "NW": "Northwest", "SE": "Southeast", "SW": "Southwest"}


def esc(value):
    return escape(str(value), quote=True)


def masthead():
    return (
        '<div class="dt mast"><div><span class="dot"></span>Calgary road safety'
        '<span class="muted"> &middot; 2025 traffic incident feed</span></div>'
        '<div class="muted">Double Trouble &middot; IEEE YP Industry Hackathon 2026</div></div>'
    )


def hero(title, lede, data):
    before, accent, after = title
    return (
        f'<div class="dt hero"><div class="title" role="heading" aria-level="1">'
        f'{esc(before)}<em>{esc(accent)}</em>{esc(after)}</div>'
        f'<div class="hero-side"><div class="lede">{esc(lede)}</div>'
        f'<div class="source"><b>{data["rows_loaded"]:,} rows loaded, {data["rows_dropped"]:,} set aside, '
        f'{data["rows_used"]:,} used.</b> City of Calgary Traffic Incidents, 2025. Logged from traffic camera '
        "views, so unverified, and places without cameras are under-counted. Not a police collision record."
        "</div></div></div>"
    )


def _signed(value, digits=2):
    sign = "+" if value >= 0 else "\u2212"
    # Shared credit for ties can leave a tenth of a point; never print float noise.
    return f"{sign}{abs(value):.{digits}f}" if digits else f"{sign}{round(abs(value), 1):g}"


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
    data, m, plan = result["dataset"], result["metrics"], result.get("plan")
    n = plan["constraints"]["budget"] if plan else len(result["top20"])
    overlap = plan["overlap"] if plan else m["overlap_with_baseline"]
    cells = [
        ("Incidents ranked", f'{data["rows_used"]:,}', "", f'{data["rows_dropped"]:,} stalls, signal faults and closures set aside', False),
        ("Same as count-only", f"{overlap}", f"<small>of {n}</small>",
         f"locations in both top-{n} lists", False),
    ]

    def pct(v):
        return f"{v:.2%}"

    if plan:
        diff = plan["points_agent"] - plan["points_baseline"]
        label = f"Top {n} harm caught" if plan_active(plan) else "Sep-Dec harm caught"
        cells.append((label, _signed(diff, 0), "<small>points</small>",
                      _pair("count-only", plan["points_baseline"], "these weights", plan["points_agent"], str)
                      + f'<span class="of">of {plan["points_total"]:,} Sep-Dec severity points, ranked on Jan-Aug</span>',
                      diff > 0))
    else:
        diff = 100 * (m["backtest_agent"] - m["backtest_baseline"])
        cells.append(("Sep-Dec harm caught", _signed(diff), "<small>pct pts</small>",
                      _pair("count-only", m["backtest_baseline"], "these weights", m["backtest_agent"], pct),
                      diff > 0))
    # The second split is optional in the contract; older results do not have it.
    if {"check_baseline", "check_agent"} <= m.keys():
        diff = 100 * (m["check_agent"] - m["check_baseline"])
        cells.append(("Jul-Dec test, top 20" if plan_active(plan) else "Second test, Jul-Dec",
                      _signed(diff), "<small>pct pts</small>",
                      _pair("count-only", m["check_baseline"], "these weights", m["check_agent"], pct)
                      + '<span class="of">ranked on Jan-Jun; overlaps the Sep-Dec window, so a check, not a held-out test</span>',
                      diff > 0))
    out = []
    for label, value, unit, note, gain in cells:
        if value[:1] in "+\u2212":
            value = f'<span class="sign">{value[0]}</span>{value[1:]}'
        cls = "fig-value gain" if gain else "fig-value"
        out.append(f'<div class="fig"><div class="fig-label">{esc(label)}</div>'
                   f'<div class="{cls}">{value}{unit}</div><div class="fig-note">{note}</div></div>')
    return '<div class="dt figures">' + "".join(out) + "</div>" + verdict(m, plan)


def verdict(m, plan=None):
    """One plain sentence on how big the edge is, so the figures are never read as larger than they are."""
    first = 100 * (m["backtest_agent"] - m["backtest_baseline"])
    second = 100 * (m["check_agent"] - m["check_baseline"]) if "check_agent" in m else None
    if plan_active(plan):
        c = plan["constraints"]
        where = f"{REGIONS[c['region']]} Calgary" if c["region"] else "Calgary"
        text = (f"For {where}, this top {c['budget']} caught {plan['points_agent']} of {plan['points_total']:,} "
                f"Sep-Dec severity points; a plain incident count caught {plan['points_baseline']}.")
        if c["budget"] != 20:
            text += f" Across a full top 20 these settings score {_signed(first)} percentage points on the Sep-Dec test"
            text += f" and {_signed(second)} on the Jul-Dec test." if second is not None else "."
        elif second is not None:
            text += f" On the Jul-Dec test: {_signed(second)} percentage points."
    elif first == 0 and not second:
        text = "At these weights the shortlist catches the same later severity points as a plain incident count."
    elif first > 0 and second is None:
        text = f"Ahead of a plain incident count by {first:.2f} percentage points. A small edge on one year of sparse data."
    elif first > 0 and second > 0:
        text = (f"Ahead of a plain incident count on both tests, by {first:.2f} and {second:.2f} percentage points. "
                "A small edge on one year of sparse data, not a breakthrough.")
    elif first > 0 and second is not None:
        text = (f"Ahead of a plain incident count on the Sep-Dec test ({_signed(first)} percentage points) but not on "
                f"the Jul-Dec test ({_signed(second)}). On one year of sparse data, weighting by harm changes which "
                "places make the list more than it changes how many later severity points the list catches.")
    else:
        text = (f"Against a plain incident count: {_signed(first)} percentage points on the Sep-Dec test"
                + (f", {_signed(second)} on the Jul-Dec test" if second is not None else "")
                + ".")
    return f'<div class="dt verdict">{esc(text)}</div>'


def section(number, title, note=""):
    note_html = f'<div class="sec-note">{note}</div>' if note else ""
    return (f'<div class="dt sec"><span class="sec-no">{number:02d}</span>'
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
        tags.append(f"Jul-Dec incidents \u00d7{c['recent_weight']:g}")
    return '<div class="dt tags">' + "".join(f"<span>{esc(t)}</span>" for t in tags) + "</div>"


def reply(rep, tags=""):
    return (f'<div class="dt reply"><div class="reply-side"><div class="reply-ask">You asked</div>'
            f'<q>{esc(rep["request"])}</q>{tags}</div>'
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


def shortlist(rows):
    top = max(r["score"] for r in rows) or 1
    out = ['<div class="dt ledger"><div class="lg-head"><span>#</span><span>Location</span>'
           '<span>Count</span><span>Ped/cyc</span><span>Moved</span></div>']
    for r in rows:
        delta, kind = _delta(r["baseline_rank"], r["rank"])
        hot = " hot" if r["pedestrian_or_cyclist"] else ""
        out.append(
            f'<div class="lg-row {kind}"><span class="lg-rank">{r["rank"]}</span>'
            f'<span class="lg-name">{esc(r["name"])}</span>'
            f'<span class="lg-num">{r["incidents"]}</span>'
            f'<span class="lg-num{hot}">{r["pedestrian_or_cyclist"]}</span>'
            f'<span class="lg-delta {kind}">{delta}</span>'
            f'<i class="lg-bar" style="width:{100 * r["score"] / top:.1f}%"></i></div>'
        )
    return "".join(out) + "</div>"


def movers(result, name_of):
    if not result["movers"]:
        return ('<div class="dt empty"><b>Every location keeps its count-only rank at these weights.</b> '
                'Raise the severity weight, or let the agent tune it, to see which places a pure '
                'count overlooks.</div>')
    cards = []
    # The spotlight goes to the biggest riser: the place a plain count was hiding.
    ordered = sorted(result["movers"], key=lambda m: (m["direction"] != "up", -abs(m["from_rank"] - m["to_rank"])))
    for i, mv in enumerate(ordered):
        up = mv["direction"] == "up"
        places = abs(mv["from_rank"] - mv["to_rank"])
        cards.append(
            f'<article class="mover {"up" if up else "down"}{" lead" if i == 0 else ""}">'
            f'<div class="mover-ranks"><span class="from">{mv["from_rank"]}</span>'
            f'<span class="arrow">{"&uarr;" if up else "&darr;"}</span><span class="to">{mv["to_rank"]}</span></div>'
            f'<div class="mover-dir">{"Up" if up else "Down"} {places} places</div>'
            f'<div class="mover-name">{esc(name_of(mv["location_key"]))}</div>'
            f'<div class="mover-why">{esc(mv["reason"])}</div></article>'
        )
    return '<div class="dt movers">' + "".join(cards) + "</div>"


def _clip(text, limit=46):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def slope(result, name_of, n=20):
    """Count-only rank on the left, harm rank on the right, one line per location."""
    row, top, width = 31, 54, 1240
    left_x, right_x = 490, 720
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
        f'aria-label="Count-only top {n} against the harm-ranked top {n}">',
        '<text class="head" x="0" y="20">Count only</text>',
        f'<text class="head" x="{width}" y="20" text-anchor="end">Ranked by harm</text>',
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
                     f'y="{y(rank)}">{esc(_clip(r["name"], 56))}</text>')
        delta, kind = _delta(was, rank)
        parts.append(f'<text class="dl {kind}" x="{width}" y="{y(rank)}" text-anchor="end">{delta}</text>')
        if new:
            key_cls = " key" if key in movers else ""
            parts.append(f'<path class="up{key_cls}" d="{curve(gutter, y(rank))}" '
                         f'style="animation-delay:{delay}ms"/>')
            delay += 35

    if any(k not in harm for k in base_rank) or any(k not in base_rank for k in harm):
        parts.append(f'<text class="gut" x="{left_x}" y="{gutter + 18}" text-anchor="end">below {n}</text>')
        parts.append(f'<text class="gut" x="{right_x}" y="{gutter + 18}">below {n}</text>')
    parts.append("</svg>")
    return "".join(parts)


def trace(tuned):
    its = tuned["agent_iterations"]
    top = max(it["backtest_metric"] for it in its) or 1
    chosen = next((it["iteration"] for it in its if it["weights"] == tuned["weights"]), None)
    cells = ['<div class="th">Step</div><div class="th">Severity</div><div class="th">Trend</div>'
             '<div class="th">Share of later harm caught</div><div class="th">Decision</div>']
    for it in its:
        w = it["weights"]
        state = "chosen" if it["iteration"] == chosen else "kept" if it["note"].startswith(("kept", "baseline")) else ""
        tag = '<span class="tag">chosen</span>' if state == "chosen" else ""
        width = 100 * it["backtest_metric"] / top
        cells.append(
            f'<div class="td num {state}">{it["iteration"]:02d}</div>'
            f'<div class="td num {state}">{w["w_severity"]:.2f}</div>'
            f'<div class="td num {state}">{w["w_trend"]:.2f}</div>'
            f'<div class="td bar-cell {state}"><div class="bar"><i style="width:{width:.1f}%;'
            f'animation-delay:{40 * it["iteration"]}ms"></i><b>{it["backtest_metric"]:.2%}</b></div></div>'
            f'<div class="td note {state}">{esc(it["note"])}{tag}</div>'
        )
    return '<div class="dt trace">' + "".join(cells) + "</div>"


def briefing(script, note):
    return (f'<div class="dt brief"><div class="transcript">{esc(script)}</div>'
            f'<div class="brief-note">{esc(note)}</div></div>')


DATASET_URL = "https://data.calgary.ca/Transportation-Transit/Traffic-Incidents/35ra-9556"
LICENCE_URL = "https://data.calgary.ca/stories/s/Open-Calgary-Terms-of-Use/u45n-7awa/"


def footer(claim, drop_reason):
    notes = [
        "Severity points come from words in each incident description (pedestrian, cyclist, "
        "multi-vehicle, multiple lanes blocked), not from injury records.",
        "The feed logs incidents seen on City traffic cameras, so places without cameras are under-counted.",
        f"Rows set aside: {drop_reason}.",
    ]
    return (f'<div class="dt foot"><div class="foot-claim">{esc(claim)}</div>'
            '<div class="foot-meta">' + "".join(f"<p>{esc(n)}</p>" for n in notes)
            + f'<p><a href="{DATASET_URL}" target="_blank" rel="noopener">Open Calgary, Traffic Incidents</a>. '
            f'Contains information licensed under the <a href="{LICENCE_URL}" target="_blank" rel="noopener">'
            "Open Government Licence - City of Calgary</a>.</p></div></div>")
