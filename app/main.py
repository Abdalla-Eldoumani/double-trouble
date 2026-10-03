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

TITLE = "Which Calgary locations keep hurting people?"
LEDE = ("A count-only list treats a fender bender like a pedestrian hit. This one ranks 2025 crash "
        "locations by reported harm, then tests its own weights against what happened later in the year.")
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

try:
    if "w_severity" not in ss:
        result = get_result()
        set_weights(result["weights"])
        ss.default_weights = current_weights()
    elif ss.pop("tune_requested", False):
        result = get_result(tune=True)
        ss.tuned = result
        set_weights(result["weights"])
    else:
        result = get_result(current_weights(), tune=False)
except ResultShapeError as exc:
    st.error(str(exc))
    st.stop()

for problem in consistency_warnings(result):
    st.warning(f"Result check: {problem}")

names = briefing.location_names(result)


def name_of(key):
    return briefing.display_name(names, key)


st.markdown(ui.hero(TITLE, LEDE, result["dataset"]), unsafe_allow_html=True)
st.markdown(ui.figures(result), unsafe_allow_html=True)

with st.container(key="controls"):
    state, agent_set = weight_state()
    st.markdown(ui.controls_head(state, agent_set), unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([3, 3, 2.6, 2.2], vertical_alignment="bottom", gap="medium")
    c1.slider("Severity weight", 0.0, 1.0, step=0.05, key="w_severity",
              help="How much pedestrian, cyclist, multi-vehicle and lane-blocking crashes count.")
    c2.slider("Trend weight", 0.0, 1.0, step=0.05, key="w_trend",
              help="How much crashes late in the year count.")
    c3.checkbox("Exclude provincial roads", key="exclude_provincial")
    c4.button("Let the agent tune it", on_click=request_tuning, type="primary", width="stretch")

# 01: map and movers
st.markdown(ui.section(1, "The shortlist on the map",
                       "Each circle is one of the top 20 locations at the current weights."),
            unsafe_allow_html=True)
top = pd.DataFrame(result["top20"]).sort_values("rank")
top["move"] = top.apply(movement, axis=1)
# Drawn last means drawn on top, so rank 1 stays visible where circles overlap.
points = top.sort_values("rank", ascending=False).assign(
    fill=lambda d: d["move"].map(FILL),
    line=lambda d: d["move"].map(LINE),
    text_colour=lambda d: d["move"].map(LABEL),
    radius=lambda d: 12 + 14 * d["score"] / d["score"].max(),
    label=lambda d: d["rank"].astype(str),
)
deck = pdk.Deck(
    map_style=pdk.map_styles.LIGHT,
    initial_view_state=pdk.ViewState(latitude=float(top["lat"].mean()),
                                     longitude=float(top["lon"].mean()), zoom=10.4),
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
map_col, movers_col = st.columns([1.65, 1], gap="large")
with map_col:
    st.pydeck_chart(deck, height=620)
    st.markdown(ui.legend(), unsafe_allow_html=True)
with movers_col:
    st.markdown('<div class="dt ctl-title">Why it moved</div>', unsafe_allow_html=True)
    st.markdown(ui.movers(result, name_of), unsafe_allow_html=True)

# 02: count-only against harm
overlap = result["metrics"]["overlap_with_baseline"]
st.markdown(ui.section(2, f"{overlap} of {len(result['top20'])} the same as count-only",
                       "Left, the 20 locations with the most incidents. Right, the 20 with the most "
                       "reported harm. Lines join the same place; red lines climbed."),
            unsafe_allow_html=True)
st.markdown(ui.slope(result, name_of), unsafe_allow_html=True)

# 03: the agent's search
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
    st.markdown(ui.section(3, "How the agent chose", note), unsafe_allow_html=True)
    st.markdown(ui.trace(tuned), unsafe_allow_html=True)
else:
    st.markdown(ui.section(3, "How the agent chose"), unsafe_allow_html=True)
    st.markdown('<div class="dt empty" style="margin-top:1.2rem"><b>The agent has not run yet.</b> '
                'Press "Let the agent tune it" and it will rank on January to August, score each '
                'weight setting on September to December, and keep only the settings that catch '
                'more later harm.</div>', unsafe_allow_html=True)

# 04: briefing
st.markdown(ui.section(4, "Morning safety briefing"), unsafe_allow_html=True)
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
