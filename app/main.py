import sys
from pathlib import Path

# streamlit run puts app/ on the path, not the repo root, and the engine lives at the root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import pydeck as pdk
import streamlit as st

from app import briefing
from app.load import ResultShapeError, consistency_warnings, get_result

st.set_page_config(page_title="Calgary crash shortlist", layout="wide")

# Blue and vermillion stay distinguishable for colour-blind viewers.
COLOURS = {"up": [0, 114, 178], "down": [213, 94, 0], "same": [150, 150, 150]}
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


st.title("Which Calgary locations keep hurting people?")
st.markdown("#### A count-only list treats a fender bender like a pedestrian hit. "
            "This list ranks 2025 crash locations by reported harm and checks its weights "
            "against what happened later in the year.")

try:
    if "w_severity" not in ss:
        result = get_result()
        set_weights(result["weights"])
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

data = result["dataset"]
st.markdown(
    f"**Data:** {data['source']}. {data['rows_loaded']:,} rows loaded, "
    f"{data['rows_dropped']:,} dropped as {data['drop_reason']}. {data['rows_used']:,} used. "
    "This is the City's incident feed, not a complete police collision database."
)

top = pd.DataFrame(result["top20"]).sort_values("rank")
top["move"] = top.apply(movement, axis=1)
names = briefing.location_names(result)

# Controls
st.subheader("Weights")
c1, c2, c3, c4 = st.columns([3, 3, 2, 2], vertical_alignment="bottom")
c1.slider("Severity weight", 0.0, 1.0, step=0.05, key="w_severity",
          help="How much pedestrian, cyclist, multi-vehicle and lane-blocking crashes count.")
c2.slider("Trend weight", 0.0, 1.0, step=0.05, key="w_trend",
          help="How much crashes late in the year count.")
c3.checkbox("Exclude provincial roads", key="exclude_provincial")
c4.button("Let the agent tune it", on_click=request_tuning, type="primary")

m = result["metrics"]
diff = m["backtest_agent"] - m["backtest_baseline"]
st.markdown(
    f"**Backtest** ({m['backtest_metric_name']}): count-only {m['backtest_baseline']:.3f}, "
    f"these weights {m['backtest_agent']:.3f}, difference {diff:+.3f}. "
    "One year of data, so small differences may be noise."
)

if "tuned" in ss:
    tuned = ss.tuned
    st.markdown("**What the agent tried** (last tuning run)")
    if tuned["weights"] != current_weights():
        st.caption("The sliders have changed since that run.")
    st.table(pd.DataFrame([
        {
            "Step": it["iteration"],
            "Severity": f"{it['weights']['w_severity']:.2f}",
            "Trend": f"{it['weights']['w_trend']:.2f}",
            "Exclude provincial": "yes" if it["weights"]["exclude_provincial"] else "no",
            "Backtest": f"{it['backtest_metric']:.3f}",
            "Result": it["note"],
        }
        for it in tuned["agent_iterations"]
    ]), hide_index=True)

# Map
st.subheader("Top 20 on the map")
st.markdown(
    "Circle size is the harm score. "
    "<span style='color:rgb(0,114,178)'><b>Blue</b></span>: moved up against count-only. "
    "<span style='color:rgb(213,94,0)'><b>Orange</b></span>: moved down. "
    "<span style='color:rgb(150,150,150)'><b>Grey</b></span>: unchanged.",
    unsafe_allow_html=True,
)
# Drawn last means drawn on top, so rank 1 stays visible where circles overlap.
points = top.sort_values("rank", ascending=False).assign(
    colour=top["move"].map(COLOURS),
    radius=12 + 14 * top["score"] / top["score"].max(),
    label=top["rank"].astype(str),
)
deck = pdk.Deck(
    map_style=pdk.map_styles.LIGHT,
    initial_view_state=pdk.ViewState(latitude=float(top["lat"].mean()),
                                     longitude=float(top["lon"].mean()), zoom=10.3),
    layers=[
        pdk.Layer("ScatterplotLayer", data=points, get_position=["lon", "lat"],
                  get_radius="radius", radius_units="'pixels'", get_fill_color="colour",
                  opacity=0.8, stroked=True, get_line_color=[255, 255, 255],
                  line_width_min_pixels=1, pickable=True),
        pdk.Layer("TextLayer", data=points, get_position=["lon", "lat"], get_text="label",
                  get_size=14, get_color=[255, 255, 255], get_text_anchor="'middle'",
                  get_alignment_baseline="'center'"),
    ],
    tooltip={"html": "<b>{name}</b><br/>Rank {rank} (count-only rank {baseline_rank})<br/>"
                     "{incidents} incidents, {pedestrian_or_cyclist} pedestrian or cyclist<br/>"
                     "{reason}"},
)
st.pydeck_chart(deck, height=560)

# Side by side
agent_rank = dict(zip(top["location_key"], top["rank"]))
overlap = m["overlap_with_baseline"]
st.subheader(f"{overlap} of {len(top)} the same as count-only")
left, right = st.columns(2)
with left:
    st.markdown("**Count only**")
    st.table(pd.DataFrame([
        {
            "Rank": i,
            "Location": names.get(r["location_key"], r["location_key"]),
            "Incidents": r["incidents"],
            "Agent rank": str(agent_rank.get(r["location_key"], "out")),
        }
        for i, r in enumerate(result["baseline"]["top20"], start=1)
    ]), hide_index=True)
with right:
    st.markdown("**Ranked by harm**")
    st.table(pd.DataFrame({
        "Rank": top["rank"],
        "Location": top["name"],
        "Incidents": top["incidents"],
        "Ped or cyclist": top["pedestrian_or_cyclist"],
        "Count rank": top["baseline_rank"],
    }), hide_index=True)

# Movers
st.subheader("Why it moved")
for col, mv in zip(st.columns(max(len(result["movers"]), 1)), result["movers"]):
    with col:
        st.markdown(f"**{names.get(mv['location_key'], mv['location_key'])}**")
        st.markdown(f"Moved {mv['direction']}: rank {mv['from_rank']} to {mv['to_rank']}")
        st.write(mv["reason"])

# Briefing
st.subheader("Morning safety briefing")
script = briefing.build_script(result)
key = briefing.api_key()
if key:
    if st.button("Play the morning safety briefing"):
        try:
            st.audio(briefing.synthesize(script, key), format="audio/mpeg")
        except Exception as exc:
            st.error(f"Audio failed ({type(exc).__name__}). The script is below.")
    with st.expander("Script"):
        st.write(script)
else:
    st.caption("Audio is off because no ElevenLabs key is set. The script:")
    st.write(script)

st.divider()
st.markdown(f"**{briefing.FOOTER}**")
