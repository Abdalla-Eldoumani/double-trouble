import math
import sys
from pathlib import Path

# streamlit run puts app/ on the path, not the repo root, and the engine lives at the root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import pydeck as pdk
import streamlit as st

from app import briefing, ui
from app.load import ResultShapeError, consistency_warnings, get_result

st.set_page_config(page_title="Calgary safety shortlist", layout="wide")

TITLE = ("Which Calgary locations keep ", "hurting", " people?")
LEDE = ("A plain count treats a fender bender like a call where EMS met a pedestrian. This one ranks 2025 "
        "traffic incidents by a harm score read from the City's own incident text, then tests its weights "
        "against what happened later in the year.")
EXAMPLES = [
    ("Northwest, top 5, recent \u00d72",
     "Prioritize recent incidents twice as much, only show northwest Calgary, "
     "and assume we can only investigate five locations."),
    ("Now the northeast", "Now show me the northeast instead."),
    ("Plain count only", "Just count incidents, ignore severity."),
    ("Reset", "Reset."),
]
# One accent for harm; "moved down" is a hollow ink ring so colour is never the only cue.
FILL = {"up": [184, 58, 27, 235], "down": [251, 249, 244, 245], "same": [163, 156, 142, 235]}
LINE = {"up": [251, 249, 244], "down": [28, 26, 23], "same": [251, 249, 244]}
LABEL = {"up": [251, 249, 244], "down": [28, 26, 23], "same": [251, 249, 244]}
ALL_AREAS = "All of Calgary"
ss = st.session_state


def set_weights(weights):
    ss.w_severity = float(weights["w_severity"])
    ss.w_trend = float(weights["w_trend"])
    ss.exclude_provincial = bool(weights["exclude_provincial"])


def current_weights():
    return {"w_severity": ss.w_severity, "w_trend": ss.w_trend,
            "exclude_provincial": ss.exclude_provincial}


def request_tuning():
    clear_reply()
    ss.tune_requested = True


def clear_reply():
    # A reply describes the request that made it; once the controls move it is out of date.
    ss.pop("reply", None)


def set_scope():
    """Area and budget are planner constraints, so the controls and typed requests stay in step."""
    clear_reply()
    ss.constraints = {**(ss.get("constraints") or {}),
                      "region": None if ss.area == ALL_AREAS else ss.area, "budget": int(ss.budget)}


def submit_typed():
    text = ss.get("planner_text", "").strip()
    if text:
        ss.pending_request = text


def submit_example(text):
    ss.planner_text = text
    ss.pending_request = text


def submit_voice():
    audio = ss.get("planner_audio")
    if audio is None:
        return
    try:
        text = briefing.transcribe(("request.wav", audio.getvalue(), "audio/wav"), briefing.api_key())
    except Exception as exc:
        ss.planner_error = f"Speech to text failed ({type(exc).__name__}). Type the request instead."
        return
    if text:
        ss.planner_text = text
        ss.pending_request = text
    else:
        ss.planner_error = "No speech was picked up. Try again or type the request."


def apply_request(text):
    """Parse the request, re-rank with it, and keep a spoken reply that compares old and new."""
    from engine.agent import DEFAULT_WEIGHTS
    from engine.planner import compare, explain, parse

    asked = parse(text)
    if asked["reset"]:
        constraints, weights = dict(asked["constraints"]), dict(ss.get("default_weights") or DEFAULT_WEIGHTS)
    else:
        constraints = {**(ss.get("constraints") or {}), **asked["constraints"]}
        weights = {**current_weights(), **asked["weights"]}
    ss.constraints = constraints
    result = get_result(weights, tune=asked["tune"], constraints=constraints)
    if asked["tune"]:
        ss.tuned = result
    set_weights(result["weights"])
    previous = ss.get("last_result")
    if previous is not None and "plan" not in previous:
        previous = None
    reply = {"request": text, "text": explain(result, compare(previous, result), asked["heard"])}
    key = briefing.api_key()
    if key:
        try:
            reply["audio"], reply["fresh"] = briefing.synthesize(reply["text"], key), True
        except Exception as exc:
            reply["audio_error"] = f"Audio failed ({type(exc).__name__}). The reply is above."
    ss.reply = reply
    return result


def fit_view(points, height, width=560):
    """Centre and zoom so every pin fits, with a margin; a fixed zoom dropped pins off the edge."""
    lat_lo, lat_hi = points["lat"].min(), points["lat"].max()
    lon_lo, lon_hi = points["lon"].min(), points["lon"].max()
    lat_span = max((lat_hi - lat_lo) / math.cos(math.radians((lat_lo + lat_hi) / 2)), 1e-3)
    zoom = min(math.log2(0.75 * height * 360 / (512 * lat_span)),
               math.log2(0.75 * width * 360 / (512 * max(lon_hi - lon_lo, 1e-3))), 13.0)
    return pdk.ViewState(latitude=float((lat_lo + lat_hi) / 2), longitude=float((lon_lo + lon_hi) / 2), zoom=zoom)


def movement(row):
    if row["rank"] < row["baseline_rank"]:
        return "up"
    if row["rank"] > row["baseline_rank"]:
        return "down"
    return "same"


def weight_state():
    weights = current_weights()
    if "tuned" in ss and ss.tuned["weights"] == weights:
        return "Chosen by the agent", True
    if weights["w_severity"] == 0 and weights["w_trend"] == 0:
        return "Count only", False
    return "Set by hand", False


st.html(f"<style>{ui.CSS}</style>")
st.markdown(ui.masthead(), unsafe_allow_html=True)

request = ss.pop("pending_request", None)
try:
    first_load = "w_severity" not in ss
    if first_load:
        # Open on the agent's own choice, so the first screen shows what it changed and why.
        result = get_result(tune=True)
        ss.tuned = result
        set_weights(result["weights"])
        ss.default_weights = current_weights()
    if request is not None:
        try:
            result = apply_request(request)
        except ImportError:
            st.warning("The planner needs the engine, which is not connected.")
            result = get_result(current_weights(), tune=False)
    elif ss.pop("tune_requested", False):
        # Tune within the user's provincial choice and planner constraints, not the defaults.
        result = get_result({"exclude_provincial": ss.exclude_provincial}, tune=True,
                            constraints=ss.get("constraints"))
        ss.tuned = result
        set_weights(result["weights"])
    elif not first_load:
        result = get_result(current_weights(), tune=False, constraints=ss.get("constraints"))
except ResultShapeError as exc:
    st.error(str(exc))
    st.stop()

for problem in consistency_warnings(result):
    st.warning(f"Result check: {problem}")

names = briefing.location_names(result)
if result.get("plan"):
    # Mirror whatever the planner or a reset decided before the widgets are drawn.
    ss.area = result["plan"]["constraints"]["region"] or ALL_AREAS
    ss.budget = result["plan"]["constraints"]["budget"]
else:
    ss.setdefault("area", ALL_AREAS)
    ss.setdefault("budget", len(result["top20"]))


def name_of(key):
    return briefing.display_name(names, key)


plan = result.get("plan")
budget = plan["constraints"]["budget"] if plan else len(result["top20"])
region = plan["constraints"]["region"] if plan else None

st.markdown(ui.hero(TITLE, LEDE, result["dataset"]), unsafe_allow_html=True)
st.markdown(ui.figures(result), unsafe_allow_html=True)

ask_col, weights_col = st.columns([1.3, 1], gap="large")
with ask_col, st.container(key="planner"):
    st.markdown(ui.card_head("Ask the planner", "Say or type what the traffic safety team can afford to "
                             "look at. The engine reranks and says what changed."),
                unsafe_allow_html=True)
    voice_key = briefing.api_key()
    if voice_key:
        st.audio_input("Speak a request", key="planner_audio", on_change=submit_voice)
    with st.form("planner_form", border=False):
        typed, go = st.columns([3, 1.1], vertical_alignment="bottom")
        typed.text_input("Type a request", key="planner_text", placeholder=EXAMPLES[0][1])
        go.form_submit_button("Run request", on_click=submit_typed, type="primary", width="stretch")
    for pair in (EXAMPLES[:2], EXAMPLES[2:]):
        for col, (label, text) in zip(st.columns(2, gap="small"), pair):
            col.button(label, on_click=submit_example, args=(text,), key=f"example_{label}",
                       type="tertiary", width="stretch")
    st.markdown('<div class="dt card-note quiet">It understands an area (northeast, NW...), how many '
                'locations, recent incidents counted twice or more, pedestrians and cyclists, count only, '
                'Deerfoot and Stoney in or out, "tune it" and "reset".</div>', unsafe_allow_html=True)
    if "planner_error" in ss:
        st.error(ss.pop("planner_error"))

with weights_col, st.container(key="controls"):
    state, agent_set = weight_state()
    st.markdown(ui.card_head("How much should harm count?", state=state, agent_set=agent_set),
                unsafe_allow_html=True)
    scoped = bool(result.get("plan"))
    area_col, budget_col = st.columns([1, 1.25], gap="medium")
    area_col.selectbox("Area", [ALL_AREAS, *ui.REGIONS], key="area", on_change=set_scope,
                       format_func=lambda a: ui.REGIONS.get(a, a), disabled=not scoped)
    budget_col.slider("Locations the team can visit", 1, 20, key="budget", on_change=set_scope,
                      disabled=not scoped)
    st.slider("Severity weight", 0.0, 1.0, step=0.05, key="w_severity", on_change=clear_reply,
              help="Harm score per incident: 1, plus 3 when the text names a pedestrian or cyclist, plus 1 for "
                   "multi-vehicle, plus 1 for more than one lane blocked. Keyword-based: the feed has no injury field.")
    st.slider("Trend weight", 0.0, 1.0, step=0.05, key="w_trend", on_change=clear_reply,
              help="How much a rise from the first half of 2025 to the second lifts a location. "
                   "To count recent incidents more, ask the planner.")
    st.checkbox("Leave out Deerfoot and Stoney Trail", key="exclude_provincial", on_change=clear_reply,
                help="The Government of Alberta maintains both roads. Matched by name, so the City-road "
                     "legs of those interchanges drop out too.")
    st.button("Let the agent tune it", on_click=request_tuning, type="primary", width="stretch")

# The reply sits full width under both cards, so the cards stay level and the map stays in view.
if ss.get("reply"):
    reply = ss.reply
    with st.container(key="answer"):
        st.markdown(ui.reply(reply, ui.plan_tags(plan)), unsafe_allow_html=True)
        if reply.get("audio"):
            st.audio(reply["audio"], format="audio/mpeg", autoplay=reply.pop("fresh", False))
        if reply.get("audio_error"):
            st.error(reply["audio_error"])

# 01: the shortlist
where = f"{ui.REGIONS[region]} Calgary" if region else "Calgary"
st.markdown(ui.section(1, f"Top {budget} on the map",
                       f"The shortlist for {where} at the current settings. The bar under each row "
                       "is its harm score."),
            unsafe_allow_html=True)
top = pd.DataFrame(result["top20"]).sort_values("rank")
top["move"] = top.apply(movement, axis=1)
shown = top.head(budget)
# Drawn last means drawn on top, so rank 1 stays visible where circles overlap.
points = shown.sort_values("rank", ascending=False).assign(
    fill=lambda d: d["move"].map(FILL),
    line=lambda d: d["move"].map(LINE),
    text_colour=lambda d: d["move"].map(LABEL),
    radius=lambda d: 11 + 11 * d["score"] / d["score"].max(),
    label=lambda d: d["rank"].astype(str),
)
map_height = max(420, 44 * len(shown) + 64)
deck = pdk.Deck(
    map_style=pdk.map_styles.LIGHT,
    initial_view_state=fit_view(shown, map_height),
    layers=[
        pdk.Layer("ScatterplotLayer", data=points, get_position=["lon", "lat"],
                  get_radius="radius", radius_units="'pixels'", get_fill_color="fill",
                  stroked=True, get_line_color="line", line_width_min_pixels=2, pickable=True),
        pdk.Layer("TextLayer", data=points, get_position=["lon", "lat"], get_text="label",
                  get_size=14, get_color="text_colour", font_family="'Geist Mono, monospace'",
                  font_weight=600, get_text_anchor="'middle'", get_alignment_baseline="'center'"),
    ],
    tooltip={
        "html": "<b>{name}</b><br/>Rank {rank}, count-only rank {baseline_rank}<br/>"
                "{incidents} incidents, {pedestrian_or_cyclist} pedestrian or cyclist<br/>"
                "<span style='opacity:.75'>{reason}</span>",
        "style": {"backgroundColor": "#1c1a17", "color": "#f4f0e8", "fontFamily": "Geist, sans-serif",
                  "fontSize": "14px", "lineHeight": "1.45", "padding": "12px 14px",
                  "borderRadius": "8px", "maxWidth": "340px"},
    },
)
map_col, list_col = st.columns([1.05, 1], gap="large")
with map_col:
    st.pydeck_chart(deck, height=map_height)
    st.markdown(ui.legend(), unsafe_allow_html=True)
with list_col:
    st.markdown(ui.shortlist(shown.to_dict("records")), unsafe_allow_html=True)

# 02: movers
st.markdown(ui.section(2, "Why it moved", "The three biggest rank changes against a plain incident count, "
                       "explained from the incident descriptions."),
            unsafe_allow_html=True)
st.markdown(ui.movers(result, name_of), unsafe_allow_html=True)

# 03: count-only against harm
overlap = plan["overlap"] if plan else result["metrics"]["overlap_with_baseline"]
st.markdown(ui.section(3, f"{overlap} of {len(shown)} the same as count-only",
                       f"Left, the {budget} locations with the most incidents. Right, the {budget} with "
                       "the highest harm score. Lines join the same place; red lines climbed."),
            unsafe_allow_html=True)
st.markdown(ui.slope(result, name_of, budget), unsafe_allow_html=True)

# 04: the agent's search
if "tuned" in ss:
    tuned = ss.tuned
    its = tuned["agent_iterations"]
    kept = sum(it["note"].startswith("kept") for it in its)
    w = tuned["weights"]
    n = tuned["plan"]["constraints"]["budget"] if tuned.get("plan") else len(tuned["top20"])
    note = (f"Plan: {len(its)} weight settings, simplest first. Test: rank on Jan-Aug, then count the Sep-Dec "
            f"severity points its top {n} would have caught. Revise: keep a setting only when it catches "
            f"strictly more, so ties stay with the simpler one. {kept} of {len(its) - 1} changes were kept. "
            f"Chosen: severity {w['w_severity']:.2f}, trend {w['w_trend']:.2f}.")
    if w != current_weights():
        note += " The sliders have changed since that run."
    st.markdown(ui.section(4, "How the agent chose", note), unsafe_allow_html=True)
    st.markdown(ui.trace(tuned), unsafe_allow_html=True)
else:
    st.markdown(ui.section(4, "How the agent chose"), unsafe_allow_html=True)
    st.markdown('<div class="dt empty"><b>The agent has not run yet.</b> '
                'Press "Let the agent tune it" and it will rank on January to August, score each '
                'weight setting on September to December, and keep only the settings that catch '
                'more later severity points.</div>', unsafe_allow_html=True)

# 05: briefing
st.markdown(ui.section(5, "Morning safety briefing"), unsafe_allow_html=True)
script = briefing.build_script(result)
key = briefing.api_key()
if key:
    if st.button("Play the morning safety briefing", type="secondary"):
        try:
            st.audio(briefing.synthesize(script, key), format="audio/mpeg")
        except Exception as exc:
            st.error(f"Audio failed ({type(exc).__name__}). The script is below.")
    note = "Read by an ElevenLabs voice. Every name and number comes from the ranking above."
else:
    note = "Script for the spoken briefing. Every name and number comes from the ranking above."
st.markdown(ui.briefing(script, note), unsafe_allow_html=True)

st.markdown(ui.footer(briefing.FOOTER, result["dataset"]["drop_reason"]), unsafe_allow_html=True)
ss.last_result = result
