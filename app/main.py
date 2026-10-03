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

st.set_page_config(page_title="Calgary crash shortlist", layout="wide")

TITLE = ("Which Calgary locations keep ", "hurting", " people?")
LEDE = ("A count-only list treats a fender bender like a pedestrian hit. This one ranks 2025 crash "
        "locations by reported harm, then tests its own weights against what happened later in the year.")
EXAMPLES = [
    ("Recent x2, northwest, top 5",
     "Prioritize recent crashes twice as much, only show northwest Calgary, "
     "and assume we can only investigate five intersections."),
    ("Pedestrians and cyclists", "Focus on pedestrians and cyclists."),
    ("Now the northeast", "Now show me the northeast instead."),
    ("Reset", "Reset."),
]
# One accent for harm; "moved down" is a hollow ink ring so colour is never the only cue.
FILL = {"up": [184, 58, 27, 235], "down": [251, 249, 244, 245], "same": [163, 156, 142, 235]}
LINE = {"up": [251, 249, 244], "down": [28, 26, 23], "same": [251, 249, 244]}
LABEL = {"up": [251, 249, 244], "down": [28, 26, 23], "same": [251, 249, 244]}
ss = st.session_state


def set_weights(weights):
    ss.w_severity = float(weights["w_severity"])
    ss.w_trend = float(weights["w_trend"])
    ss.exclude_provincial = bool(weights["exclude_provincial"])


def current_weights():
    return {"w_severity": ss.w_severity, "w_trend": ss.w_trend,
            "exclude_provincial": ss.exclude_provincial}


def request_tuning():
    ss.tune_requested = True


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
        constraints, weights = dict(asked["constraints"]), dict(DEFAULT_WEIGHTS)
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
    if weights == ss.get("default_weights"):
        if weights["w_severity"] == 0 and weights["w_trend"] == 0:
            return "Engine default: count only", False
        return "Engine default", False
    return "Set by hand", False


st.html(f"<style>{ui.CSS}</style>")
st.markdown(ui.masthead(), unsafe_allow_html=True)

request = ss.pop("pending_request", None)
try:
    first_load = "w_severity" not in ss
    if first_load:
        result = get_result()
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


def name_of(key):
    return briefing.display_name(names, key)


plan = result.get("plan")
budget = plan["constraints"]["budget"] if plan else len(result["top20"])
region = plan["constraints"]["region"] if plan else None

st.markdown(ui.hero(TITLE, LEDE, result["dataset"]), unsafe_allow_html=True)
st.markdown(ui.figures(result), unsafe_allow_html=True)

ask_col, weights_col = st.columns([1.3, 1], gap="large")
with ask_col, st.container(key="planner"):
    st.markdown(ui.card_head("Ask the planner", "Say or type what the roads team can afford to "
                             "look at. The engine reranks and says what changed."),
                unsafe_allow_html=True)
    voice_key = briefing.api_key()
    if voice_key:
        st.audio_input("Speak a request", key="planner_audio", on_change=submit_voice)
    with st.form("planner_form", border=False):
        typed, go = st.columns([4, 1.2], vertical_alignment="bottom")
        typed.text_input("Type a request", key="planner_text", placeholder=EXAMPLES[0][1])
        go.form_submit_button("Run request", on_click=submit_typed, type="primary", width="stretch")
    for pair in (EXAMPLES[:2], EXAMPLES[2:]):
        for col, (label, text) in zip(st.columns(2, gap="small"), pair):
            col.button(label, on_click=submit_example, args=(text,), key=f"example_{label}",
                       type="tertiary", width="stretch")
    if not voice_key:
        st.markdown('<div class="dt card-note quiet">Voice input is off because no ElevenLabs key is set. '
                    'Typing works the same way.</div>', unsafe_allow_html=True)
    if "planner_error" in ss:
        st.error(ss.pop("planner_error"))
    if ss.get("reply"):
        reply = ss.reply
        st.markdown(ui.plan_tags(plan) + ui.reply(reply), unsafe_allow_html=True)
        if reply.get("audio"):
            st.audio(reply["audio"], format="audio/mpeg", autoplay=reply.pop("fresh", False))
        if reply.get("audio_error"):
            st.error(reply["audio_error"])

with weights_col, st.container(key="controls"):
    state, agent_set = weight_state()
    st.markdown(ui.card_head("How much should harm count?", state=state, agent_set=agent_set),
                unsafe_allow_html=True)
    st.slider("Severity weight", 0.0, 1.0, step=0.05, key="w_severity",
              help="How much pedestrian, cyclist, multi-vehicle and lane-blocking crashes count.")
    st.slider("Trend weight", 0.0, 1.0, step=0.05, key="w_trend",
              help="How much crashes late in the year count.")
    st.checkbox("Exclude provincial roads", key="exclude_provincial")
    st.button("Let the agent tune it", on_click=request_tuning, type="primary", width="stretch")

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
    radius=lambda d: 12 + 14 * d["score"] / d["score"].max(),
    label=lambda d: d["rank"].astype(str),
)
deck = pdk.Deck(
    map_style=pdk.map_styles.LIGHT,
    initial_view_state=pdk.ViewState(latitude=float(shown["lat"].mean()),
                                     longitude=float(shown["lon"].mean()),
                                     zoom=11.2 if region else 10.4),
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
    st.pydeck_chart(deck, height=max(420, 44 * len(shown) + 64))
    st.markdown(ui.legend(), unsafe_allow_html=True)
with list_col:
    st.markdown(ui.shortlist(shown.to_dict("records")), unsafe_allow_html=True)

# 02: movers
st.markdown(ui.section(2, "Why it moved", "The three biggest rank changes against a plain crash count, "
                       "explained from the incident descriptions."),
            unsafe_allow_html=True)
st.markdown(ui.movers(result, name_of), unsafe_allow_html=True)

# 03: count-only against harm
overlap = plan["overlap"] if plan else result["metrics"]["overlap_with_baseline"]
st.markdown(ui.section(3, f"{overlap} of {len(shown)} the same as count-only",
                       f"Left, the {budget} locations with the most incidents. Right, the {budget} with "
                       "the most reported harm. Lines join the same place; red lines climbed."),
            unsafe_allow_html=True)
st.markdown(ui.slope(result, name_of, budget), unsafe_allow_html=True)

# 04: the agent's search
if "tuned" in ss:
    tuned = ss.tuned
    its = tuned["agent_iterations"]
    kept = sum(it["note"].startswith("kept") for it in its)
    w = tuned["weights"]
    note = (f"It tried {len(its)} weight settings on Jan-Aug, scored each on Sep-Dec, and kept a change "
            f"only when it caught more later harm. {kept} changes were kept. Chosen: severity "
            f"{w['w_severity']:.2f}, trend {w['w_trend']:.2f}.")
    if w != current_weights():
        note += " The sliders have changed since that run."
    st.markdown(ui.section(4, "How the agent chose", note), unsafe_allow_html=True)
    st.markdown(ui.trace(tuned), unsafe_allow_html=True)
else:
    st.markdown(ui.section(4, "How the agent chose"), unsafe_allow_html=True)
    st.markdown('<div class="dt empty"><b>The agent has not run yet.</b> '
                'Press "Let the agent tune it" and it will rank on January to August, score each '
                'weight setting on September to December, and keep only the settings that catch '
                'more later harm.</div>', unsafe_allow_html=True)

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
    note = "Audio is off because no ElevenLabs key is set. Every name and number comes from the ranking above."
st.markdown(ui.briefing(script, note), unsafe_allow_html=True)

st.markdown(ui.footer(briefing.FOOTER, result["dataset"]["drop_reason"]), unsafe_allow_html=True)
ss.last_result = result
