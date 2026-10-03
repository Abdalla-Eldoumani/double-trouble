from html import escape
from pathlib import Path

CSS = (Path(__file__).resolve().parent / "style.css").read_text()


def esc(value):
    return escape(str(value), quote=True)


def masthead():
    return (
        '<div class="dt mast"><div><span class="dot"></span>Calgary road safety'
        '<span class="muted"> &middot; 2025 traffic incident feed</span></div>'
        '<div class="muted">Double Trouble &middot; IEEE YP Industry Hackathon 2026</div></div>'
    )


def hero(title, lede, data):
    source = data["source"].rstrip(". ") + "."
    if "not a complete police collision database" not in source:
        source += " This is the City's incident feed, not a complete police collision database."
    return (
        f'<div class="dt hero"><div class="title" role="heading" aria-level="1">{esc(title)}</div>'
        f'<div><div class="lede">{esc(lede)}</div>'
        f'<div class="source"><b>{data["rows_loaded"]:,} rows loaded, {data["rows_dropped"]:,} dropped, '
        f'{data["rows_used"]:,} used.</b> {esc(source)}</div></div></div>'
    )


def _points(diff):
    sign = "+" if diff >= 0 else "-"
    return f"{sign}{abs(diff):.2f}"


def figures(result):
    data, m = result["dataset"], result["metrics"]
    cells = [
        ("Crashes ranked", f'{data["rows_used"]:,}', "",
         f'{data["rows_dropped"]:,} non-crash rows set aside'),
        ("Same as count-only", f'{m["overlap_with_baseline"]}', f'<small>of {len(result["top20"])}</small>',
         "locations in both top-20 lists"),
    ]
    splits = [("Sep-Dec harm caught", "backtest_baseline", "backtest_agent")]
    # The second split is optional in the contract; older results do not have it.
    if {"check_baseline", "check_agent"} <= m.keys():
        splits.append(("Jul-Dec check", "check_baseline", "check_agent"))
    for label, base, agent in splits:
        diff = 100 * (m[agent] - m[base])
        cells.append((label, _points(diff), "<small>pts</small>",
                      f'<span class="mono">{m[base]:.2%}</span> count-only, '
                      f'<span class="mono">{m[agent]:.2%}</span> these weights', diff > 0))
    out = []
    for label, value, unit, note, *gain in cells:
        cls = "fig-value gain" if gain and gain[0] else "fig-value"
        out.append(f'<div class="fig"><div class="fig-label">{label}</div>'
                   f'<div class="{cls}">{value}{unit}</div><div class="fig-note">{note}</div></div>')
    return '<div class="dt figures">' + "".join(out) + "</div>"


def section(number, title, note=""):
    note_html = f'<div class="sec-note">{note}</div>' if note else ""
    return (f'<div class="dt sec"><span class="sec-no">{number:02d}</span>'
            f'<div class="sec-title" role="heading" aria-level="2">{esc(title)}</div>{note_html}</div>')


def controls_head(state, agent_set):
    cls = "ctl-state agent" if agent_set else "ctl-state"
    return (f'<div class="dt ctl-head"><div class="ctl-title">How much should harm count?</div>'
            f'<div class="{cls}">{esc(state)}</div></div>')


def legend():
    return ('<div class="dt legend"><span><i class="up"></i>Moved up</span>'
            '<span><i class="down"></i>Moved down</span><span><i class="same"></i>Same rank</span>'
            '<span>Larger circle, higher harm score</span></div>')


def movers(result, name_of):
    if not result["movers"]:
        return ('<div class="dt empty"><b>Every location keeps its count-only rank at these weights.</b> '
                'Raise the severity weight, or let the agent tune it, to see which places a pure '
                'count overlooks.</div>')
    cards = []
    for mv in result["movers"]:
        up = mv["direction"] == "up"
        arrow = "&uarr;" if up else "&darr;"
        places = abs(mv["from_rank"] - mv["to_rank"])
        cards.append(
            f'<article class="mover {"up" if up else "down"}"><div class="mover-top">'
            f'<div><div class="mover-name">{esc(name_of(mv["location_key"]))}</div>'
            f'<div class="mover-dir">{"Up" if up else "Down"} {places} places</div></div>'
            f'<div class="mover-ranks"><span class="from">{mv["from_rank"]}</span>'
            f'<span class="arrow">{arrow}</span><span class="to">{mv["to_rank"]}</span></div></div>'
            f'<div class="mover-why">{esc(mv["reason"])}</div></article>'
        )
    return '<div class="dt movers">' + "".join(cards) + "</div>"


def _clip(text, limit=46):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def slope(result, name_of):
    """Count-only rank on the left, harm rank on the right, one line per location."""
    row, top, width = 31, 54, 1240
    left_x, right_x = 500, 740
    base = [b["location_key"] for b in result["baseline"]["top20"]]
    base_rank = {k: i for i, k in enumerate(base, start=1)}
    harm = {r["location_key"]: r for r in result["top20"]}
    n = max(len(base), len(harm))
    gutter = top + n * row + 14

    def y(rank):
        return top + (rank - 1) * row

    def curve(y1, y2):
        mid = (left_x + right_x) / 2
        return f"M{left_x + 8} {y1 - 5} C{mid} {y1 - 5},{mid} {y2 - 5},{right_x - 8} {y2 - 5}"

    movers = {m["location_key"] for m in result["movers"]}
    parts = [
        f'<svg class="dt slope" viewBox="0 0 {width} {gutter + 30}" role="img" '
        f'aria-label="Count-only top 20 against the harm-ranked top 20">',
        f'<text class="head" x="0" y="20">Count only</text>',
        f'<text class="head" x="{width}" y="20" text-anchor="end">Ranked by harm</text>',
    ]
    for i in range(n):
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
        if was > rank:
            delta, kind = f"\u2191{was - rank}", "up"
        elif was < rank:
            delta, kind = f"\u2193{rank - was}", "down"
        else:
            delta, kind = "=", "same"
        parts.append(f'<text class="dl {kind}" x="{width}" y="{y(rank)}" text-anchor="end">{delta}</text>')
        if new:
            key_cls = " key" if key in movers else ""
            parts.append(f'<path class="up{key_cls}" d="{curve(gutter, y(rank))}" '
                         f'style="animation-delay:{delay}ms"/>')
            delay += 35

    parts.append(f'<text class="gut" x="{left_x}" y="{gutter + 4}" text-anchor="end">below 20</text>')
    parts.append(f'<text class="gut" x="{right_x}" y="{gutter + 4}">below 20</text>')
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


def footer(claim, drop_reason):
    return (f'<div class="dt foot"><div class="foot-claim">{esc(claim)}</div>'
            f'<div class="foot-meta">Rows set aside: {esc(drop_reason)}</div></div>')
