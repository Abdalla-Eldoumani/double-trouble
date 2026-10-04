import sys
from pathlib import Path

# streamlit run puts app/ on the path, not the repo root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import pydeck as pdk
import streamlit as st

from app import briefing, export, planning, ui
from app.load import ResultShapeError, consistency_warnings, get_result

st.set_page_config(page_title="Calgary traffic-safety investigations", layout="wide")
# Speech is a later project phase. Environment credentials alone never enable it.
SPEECH_ENABLED = False
TITLE = ("Where should Calgary focus its next ", "traffic-safety", " investigation?")
LEDE = ("Use Calgary’s 2025 reported crash incidents to shortlist locations for investigation. "
        "Choose your area, available investigation capacity, and safety priorities to see where to focus and why.")
EXAMPLES = [
    ("Pedestrians and cyclists", "Focus on pedestrians and cyclists."),
    ("Top 10 citywide", "Top 10 across the whole city."),
    ("City roads only", "City roads only."),
]
PLACEHOLDER = "We can investigate five locations in northwest Calgary. Give recent crashes twice the importance."
ss = st.session_state


def clear_confirmation():
    ss.pop("reply", None)
    ss.pop("tuning_confirmation", None)


def change_control(key):
    """Widget mirrors update only the named field in the authoritative settings."""
    clear_confirmation()
    if key in ("area", "capacity", "recent_weight"):
        field = {"area": "region", "capacity": "budget", "recent_weight": "recent_weight"}[key]
        ss.settings["constraints"][field] = ss[key]
    elif key == "priorities":
        if ss.priorities in planning.PRESETS:
            severity, trend, recent = planning.PRESETS[ss.priorities]
            ss.settings["weights"].update(w_severity=severity, w_trend=trend)
            ss.settings["constraints"]["recent_weight"] = recent
    else:
        ss.settings["weights"][key] = ss[key]


def sync_widgets():
    w, c = ss.settings["weights"], ss.settings["constraints"]
    for key, value in w.items():
        ss[key] = value
    ss.area, ss.capacity, ss.recent_weight = c["region"], c["budget"], c["recent_weight"]
    ss.priorities = planning.preset_name(ss.settings)
    ss.constraints = dict(c)


def request_tuning():
    clear_confirmation()
    ss.tune_requested = True


def submit_typed():
    text = ss.get("planner_text", "").strip()
    if text:
        ss.pending_request = text


def submit_example(text):
    ss.planner_text = text
    ss.pending_request = text


def submit_voice():
    # Preserve the integration hook; direct callbacks also respect the UI-phase gate.
    if not SPEECH_ENABLED:
        return
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


def apply_request(text):
    from engine.planner import compare, parse

    asked = parse(text)
    clear_confirmation()
    recognized = bool(asked["constraints"] or asked["weights"] or asked["reset"] or asked["tune"])
    if asked["reset"]:
        weights, constraints = dict(planning.DEFAULT_WEIGHTS), dict(planning.DEFAULT_CONSTRAINTS)
    else:
        weights = {**ss.settings["weights"], **asked["weights"]}
        constraints = {**ss.settings["constraints"], **asked["constraints"]}
    result = get_result(weights, tune=asked["tune"], constraints=constraints)
    ss.settings = planning.from_result(result)
    if asked["tune"]:
        ss.tuned = result
    previous = ss.get("last_result")
    if previous is not None and "plan" not in previous:
        previous = None
    reply = {"request": text, "text": (
        ("Ranking options tested. Updated: " if asked["tune"] else "Updated: ") + planning.summary(ss.settings) + "." if recognized else
        "Settings unchanged. Try an area, a number of locations, pedestrian/cyclist priorities, "
        "recent crash weighting, or road exclusions."
    )}
    if result.get("plan"):
        reply["comparison"] = compare(previous, result)
    if SPEECH_ENABLED:
        key = briefing.api_key()
        if key:
            try:
                reply["audio"] = briefing.synthesize(reply["text"], key)
                reply["fresh"] = True
            except Exception as exc:
                reply["audio_error"] = f"Audio failed ({type(exc).__name__})."
    ss.reply = reply
    return result


st.html(f"<style>{ui.CSS}</style>")
st.markdown(ui.masthead(), unsafe_allow_html=True)
try:
    if "settings" not in ss:
        result = get_result()
        ss.settings = planning.from_result(result)
    else:
        result = None
    request = ss.pop("pending_request", None)
    if request is not None:
        try:
            result = apply_request(request)
        except ImportError:
            st.warning("The typed planner needs the connected engine. Sample settings were left unchanged.")
    elif ss.pop("tune_requested", False):
        result = get_result(ss.settings["weights"], tune=True, constraints=ss.settings["constraints"])
        ss.tuned = result
        ss.settings = planning.from_result(result)
        ss.tuning_confirmation = "Ranking options tested. Updated: " + planning.summary(ss.settings) + "."
    if result is None:
        result = get_result(ss.settings["weights"], tune=False, constraints=ss.settings["constraints"])
except ResultShapeError as exc:
    st.error(str(exc))
    st.stop()

ss.settings = planning.from_result(result)
sync_widgets()
for problem in consistency_warnings(result):
    st.warning(f"Result check: {problem}")
plan = result.get("plan")
interactive = bool(plan)
rows = ui.recommended_rows(result)
budget = plan["constraints"]["budget"] if plan else len(rows)
region = plan["constraints"]["region"] if plan else None
names = briefing.location_names(result)
st.markdown(ui.hero(TITLE, LEDE, result["dataset"]), unsafe_allow_html=True)
st.markdown(ui.figures(result), unsafe_allow_html=True)

controls_col, ask_col = st.columns([1, 1], gap="large")
with controls_col, st.container(key="controls"):
    st.markdown(ui.card_head("Plan your investigation"), unsafe_allow_html=True)
    st.selectbox("Area", [None, "NW", "NE", "SW", "SE"], key="area",
                 format_func=lambda r: ui.REGIONS[r] if r else "All Calgary",
                 on_change=change_control, args=("area",), disabled=not interactive)
    st.number_input("How many locations can your team investigate?", min_value=1, max_value=20,
                    step=1, key="capacity", on_change=change_control, args=("capacity",), disabled=not interactive)
    st.selectbox("Safety priorities", [*planning.PRESETS, "Custom priorities"], key="priorities",
                 on_change=change_control, args=("priorities",), disabled=not interactive)
    st.caption(planning.PRESET_NOTES[ss.priorities])
    st.checkbox("Exclude Deerfoot and Stoney locations", key="exclude_provincial",
                on_change=change_control, args=("exclude_provincial",), disabled=not interactive,
                help="Excludes grouped location names containing Deerfoot or Stoney; it does not verify road ownership.")
    st.button("Reset settings", on_click=submit_example, args=("Reset.",), disabled=not interactive)
    st.caption("Reset: all Calgary, up to 20 locations, crash totals, Deerfoot and Stoney excluded.")
with ask_col, st.container(key="planner"):
    st.markdown(ui.card_head("Ask the planner", "Tell the planner your investigation capacity, area, or safety priorities."), unsafe_allow_html=True)
    if SPEECH_ENABLED and briefing.api_key():
        st.audio_input("Speak a request", key="planner_audio", on_change=submit_voice)
    with st.form("planner_form", border=False):
        st.text_input("Your planning request", key="planner_text", placeholder=PLACEHOLDER, disabled=not interactive)
        st.form_submit_button("Update recommendations", on_click=submit_typed, type="primary", width="stretch", disabled=not interactive)
    st.caption("Try a supported request:")
    for label, text in EXAMPLES:
        st.button(label, on_click=submit_example, args=(text,), key=f"example_{label}", type="tertiary", width="stretch", disabled=not interactive)
    if ss.get("reply"):
        st.markdown(ui.reply(ss.reply), unsafe_allow_html=True)
        if SPEECH_ENABLED and ss.reply.get("audio"):
            st.audio(ss.reply["audio"], format="audio/mpeg", autoplay=ss.reply.pop("fresh", False))

if not interactive:
    st.caption("Sample output: planning controls are unavailable until the engine is connected. These are illustrative recommendations.")
if ss.get("tuning_confirmation"):
    st.success(ss.tuning_confirmation)
where = f"{ui.REGIONS[region]} Calgary" if region else "Calgary"
st.markdown(ui.section(1, "Recommended locations", f"Up to {budget} locations in {where}."), unsafe_allow_html=True)
st.markdown(ui.recommendation_summary(result), unsafe_allow_html=True)
csv_data, csv_filename = export.shortlist_csv(result)
st.download_button("Export investigation shortlist", data=csv_data, file_name=csv_filename,
                   mime="text/csv", disabled=not rows, on_click="ignore", key="export_shortlist")
if len(rows) < budget:
    st.info(f"{len(rows)} locations qualify for the requested {budget}. Only locations with retained crash records "
            "in the selected area and road scope can be recommended.")
if not rows:
    st.info("No locations qualify. Try another area or include Deerfoot and Stoney locations.")
else:
    shown = pd.DataFrame(rows)
    points = shown.sort_values("rank", ascending=False).assign(
        label=lambda d: d["rank"].astype(str),
        selection_reason=[ui.location_reason(r, result) for r in reversed(rows)],
    )
    deck = pdk.Deck(
        map_style=pdk.map_styles.LIGHT,
        initial_view_state=pdk.ViewState(latitude=float(shown["lat"].mean()), longitude=float(shown["lon"].mean()), zoom=11.2 if region else 10.4),
        layers=[
            pdk.Layer("ScatterplotLayer", data=points, get_position=["lon", "lat"], get_radius=18,
                      radius_units="'pixels'", get_fill_color=[184, 58, 27, 235], stroked=True,
                      get_line_color=[251, 249, 244], line_width_min_pixels=2, pickable=True),
            pdk.Layer("TextLayer", data=points, get_position=["lon", "lat"], get_text="label", get_size=14,
                      get_color=[251, 249, 244], font_family="'Geist Mono, monospace'", font_weight=600,
                      get_text_anchor="'middle'", get_alignment_baseline="'center'"),
        ],
        tooltip={"text": "#{rank} · {name}\n{incidents} reported crashes\n{pedestrian_or_cyclist} pedestrian/cyclist reports\n{selection_reason}",
                 "style": {"backgroundColor": "#1c1a17", "color": "#f4f0e8", "fontSize": "14px", "maxWidth": "340px"}},
    )
    map_col, list_col = st.columns([1.05, 1], gap="large")
    with map_col:
        st.pydeck_chart(deck, height=520)
        st.caption("Numbers match the ranked list. Markers use the median reported coordinates of each grouped location.")
    with list_col:
        st.markdown(ui.shortlist(rows, result), unsafe_allow_html=True)

st.markdown(ui.section(2, "Why these locations are priorities", "Reasons for the leading recommendations, based on reported incidents."), unsafe_allow_html=True)
st.markdown(ui.movers(result, lambda k: briefing.display_name(names, k)), unsafe_allow_html=True)
st.markdown(ui.section(3, "What changed from ranking by crash totals?",
                       "Ranking positions across the two top-20 lists, not measured changes in road safety."), unsafe_allow_html=True)
st.markdown(ui.ranking_changes(result, lambda k: briefing.display_name(names, k)), unsafe_allow_html=True)
with st.expander("Advanced controls", expanded=False):
    st.caption("These controls change ranking priorities; they do not filter out other crash types. Indicators come from reported descriptions, not confirmed injury severity.")
    st.slider("Give more priority to pedestrian/cyclist and other crash indicators", 0.0, 1.0, step=0.05, key="w_severity", on_change=change_control, args=("w_severity",), disabled=not interactive,
              help="Higher values give extra importance to pedestrian/cyclist reports, multi-vehicle crashes, and crashes blocking multiple lanes.")
    st.caption("Higher values give extra importance to pedestrian/cyclist reports, multi-vehicle crashes, and crashes blocking multiple lanes.")
    st.slider("Give more priority to locations with increasing crashes", 0.0, 1.0, step=0.05, key="w_trend", on_change=change_control, args=("w_trend",), disabled=not interactive,
              help="Higher values give extra importance to locations with more crashes in July–December than January–June 2025, using (later crashes + 1) / (earlier crashes + 1).")
    st.caption("Higher values give extra importance to the ratio of July–December to January–June 2025 crashes, using (later crashes + 1) / (earlier crashes + 1).")
    st.slider("Give more priority to recent crashes", 1.0, 5.0, step=0.5, key="recent_weight", on_change=change_control, args=("recent_weight",), disabled=not interactive,
              help="Higher values multiply July–December 2025 reports in both crash counts and incident-indicator points for the full-year ranking; January–June reports keep their usual importance.")
    st.caption("Higher values multiply July–December 2025 reports in both crash counts and incident-indicator points for the full-year ranking. January–June reports keep their usual importance. This is separate from increasing activity.")
    st.caption(f"Current weights: incident indicators {ss.w_severity:.2f}; increasing activity {ss.w_trend:.2f}; recency {ss.recent_weight:g}×.")
    st.button("Test ranking options automatically", on_click=request_tuning, type="primary", disabled=not interactive)
    st.caption("Compares available weight settings using historical validation and selects the strongest result under that test. The search evaluates 20 locations and retains your area, road scope, and recency settings; your displayed capacity stays the same.")
with st.expander("How we tested the ranking", expanded=False):
    st.markdown(ui.validation(result), unsafe_allow_html=True)
    st.markdown(ui.slope(result, lambda k: briefing.display_name(names, k), budget), unsafe_allow_html=True)
    st.caption("Both lists use the same area, road exclusions, capacity, and January–December 2025 records. The crash-total list uses raw counts, without extra recency or incident weighting.")
    st.dataframe(pd.DataFrame(rows).reindex(columns=["rank", "name", "incidents", "score", "baseline_rank"]).rename(columns={"rank": "Current rank", "name": "Location", "incidents": "Reported crashes", "score": "Custom ranking score", "baseline_rank": "Rank by total crashes"}), hide_index=True)
    tuned = ss.get("tuned")
    if tuned:
        st.markdown("**Automatic ranking search**")
        st.caption(f"Tested {len(tuned['agent_iterations'])} settings. Objective: maximize September–December proxy points at 20 locations selected from January–August. Ties keep simpler weights. This evaluation was used to choose weights.")
        st.caption("Search settings: " + planning.summary(planning.from_result(tuned)))
        st.caption(f"Selected weights: incident indicators {tuned['weights']['w_severity']:.2f}; increasing activity {tuned['weights']['w_trend']:.2f}.")
        if planning.from_result(tuned) != ss.settings:
            st.caption("These are results from a previous search. Your current settings have changed.")
        st.markdown(ui.trace(tuned), unsafe_allow_html=True)
    else:
        st.caption("Automatic search has not run in this session. Current weights were supplied directly.")
with st.expander("About the data", expanded=False):
    d = result["dataset"]
    st.markdown(f"{d['rows_loaded']:,} rows loaded, {d['rows_dropped']:,} dropped, {d['rows_used']:,} used. These counts cover the full dataset, before your area and road filters.")
    st.write(d["source"])
    st.write("Rows set aside: " + d["drop_reason"] + ". Records missing location, coordinates, date, or description are also excluded.")
    st.write("Location names are normalized and grouped; a group can represent a corridor or approximate cluster, rather than a verified intersection. Areas use the most frequently reported quadrant in each group.")
    st.markdown("Source: [City of Calgary Traffic Incidents](https://data.calgary.ca/Transportation-Transit/Traffic-Incidents/35ra-9556). Contains information licensed under the Open Government Licence – City of Calgary.")
st.markdown(ui.footer(briefing.FOOTER, ""), unsafe_allow_html=True)
ss.last_result = result
