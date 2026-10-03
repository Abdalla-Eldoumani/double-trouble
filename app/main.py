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


st.title("Which Calgary locations keep hurting people?")
st.markdown("#### A count-only list treats a fender bender like a pedestrian hit. "
            "This list ranks 2025 crash locations by reported harm and checks its weights "
            "against what happened later in the year.")

request = ss.pop("pending_request", None)
try:
    first_load = "w_severity" not in ss
    if first_load:
        result = get_result()
        set_weights(result["weights"])
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

data = result["dataset"]
source = data["source"].rstrip(". ") + "."
if "not a complete police collision database" not in source:
    source += " This is the City's incident feed, not a complete police collision database."
st.markdown(f"**Data:** {source}")
st.markdown(f"**{data['rows_loaded']:,} rows loaded, {data['rows_dropped']:,} dropped, "
            f"{data['rows_used']:,} used.**")
st.caption(f"Dropped: {data['drop_reason']}")

# Voice planner
EXAMPLES = [
    "Prioritize recent crashes twice as much, only show northwest Calgary, "
    "and assume we can only investigate five intersections.",
    "Focus on pedestrians and cyclists.",
    "Now show me the northeast instead.",
    "Reset.",
]
st.subheader("Ask the planner")
voice_key = briefing.api_key()
if voice_key:
    st.audio_input("Speak a request", key="planner_audio", on_change=submit_voice)
else:
    st.caption("Voice input is off because no ElevenLabs key is set. Type a request instead.")
with st.form("planner"):
    st.text_input("Type a request", key="planner_text", placeholder=EXAMPLES[0])
    st.form_submit_button("Run request", on_click=submit_typed, type="primary")
for col, example in zip(st.columns(len(EXAMPLES)), EXAMPLES):
    col.button(example if len(example) < 40 else "Recent x2, northwest, budget 5",
               on_click=submit_example, args=(example,), key=f"example_{example[:12]}")
if "planner_error" in ss:
    st.error(ss.pop("planner_error"))
if ss.get("reply"):
    reply = ss.reply
    st.info(f'You asked: "{reply["request"]}"\n\n{reply["text"]}')
    if reply.get("audio"):
        st.audio(reply["audio"], format="audio/mpeg", autoplay=reply.pop("fresh", False))
    if reply.get("audio_error"):
        st.error(reply["audio_error"])

plan = result.get("plan")
budget = plan["constraints"]["budget"] if plan else len(result["top20"])

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
splits = [("backtest_metric_name", "backtest_baseline", "backtest_agent")]
# The second split is optional in the contract; older results do not have it.
if {"check_metric_name", "check_baseline", "check_agent"} <= m.keys():
    splits.append(("check_metric_name", "check_baseline", "check_agent"))
lines = []
for label, base_key, agent_key in splits:
    diff = 100 * (m[agent_key] - m[base_key])
    lines.append(f"- {m[label][:1].upper()}{m[label][1:]}: count-only {m[base_key]:.2%}, "
                 f"these weights {m[agent_key]:.2%} ({diff:+.2f} points)")
st.markdown("**Backtest**\n" + "\n".join(lines) +
            "\n\nOne year of data, so small differences may be noise.")

if plan and plan["constraints"] != {"recent_weight": 1.0, "region": None, "budget": 20}:
    c = plan["constraints"]
    st.markdown(
        f"**Planner settings:** top {c['budget']}"
        f"{', ' + c['region'] + ' only' if c['region'] else ', all of Calgary'}"
        f"{', July to December crashes count ' + format(c['recent_weight'], 'g') + ' times' if c['recent_weight'] != 1 else ''}. "
        f"**Backtest** ({plan['metric_name']}): count-only {plan['backtest_baseline']:.3f}, "
        f"these settings {plan['backtest_agent']:.3f}."
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
            "Backtest": f"{it['backtest_metric']:.2%}",
            "Result": it["note"],
        }
        for it in tuned["agent_iterations"]
    ]), hide_index=True)

# Map
st.subheader(f"Top {budget} on the map")
st.markdown(
    "Circle size is the harm score. "
    "<span style='color:rgb(0,114,178)'><b>Blue</b></span>: moved up against count-only. "
    "<span style='color:rgb(213,94,0)'><b>Orange</b></span>: moved down. "
    "<span style='color:rgb(150,150,150)'><b>Grey</b></span>: unchanged.",
    unsafe_allow_html=True,
)
# Drawn last means drawn on top, so rank 1 stays visible where circles overlap.
shown = top.head(budget)
points = shown.sort_values("rank", ascending=False).assign(
    colour=shown["move"].map(COLOURS),
    radius=12 + 14 * shown["score"] / shown["score"].max(),
    label=shown["rank"].astype(str),
)
deck = pdk.Deck(
    map_style=pdk.map_styles.LIGHT,
    initial_view_state=pdk.ViewState(latitude=float(shown["lat"].mean()),
                                     longitude=float(shown["lon"].mean()),
                                     zoom=11.2 if plan and plan["constraints"]["region"] else 10.3),
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
agent_rank = dict(zip(shown["location_key"], shown["rank"]))
overlap = plan["overlap"] if plan else m["overlap_with_baseline"]
st.subheader(f"{overlap} of {len(shown)} the same as count-only")
left, right = st.columns(2)
with left:
    st.markdown("**Count only**")
    st.table(pd.DataFrame([
        {
            "Rank": i,
            "Location": briefing.display_name(names, r["location_key"]),
            "Incidents": r["incidents"],
            "Agent rank": str(agent_rank.get(r["location_key"], "out")),
        }
        for i, r in enumerate(result["baseline"]["top20"][:budget], start=1)
    ]), hide_index=True)
with right:
    st.markdown("**Ranked by harm**")
    st.table(pd.DataFrame({
        "Rank": shown["rank"],
        "Location": shown["name"],
        "Incidents": shown["incidents"],
        "Ped or cyclist": shown["pedestrian_or_cyclist"],
        "Count rank": shown["baseline_rank"],
    }), hide_index=True)

# Movers
st.subheader("Why it moved")
if not result["movers"]:
    st.markdown("No location changed rank against count-only at these weights.")
for col, mv in zip(st.columns(max(len(result["movers"]), 1)), result["movers"]):
    with col:
        st.markdown(f"**{briefing.display_name(names, mv['location_key'])}**")
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
ss.last_result = result
