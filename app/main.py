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

# A long-lived Streamlit process can rerun this script while retaining an older
# imported presentation/speech modules. Refresh those when their source changes;
# session settings, cached results, and the ranking engine stay intact.
for presentation_module in (ui, briefing, planning):
    source_mtime = Path(presentation_module.__file__).resolve().stat().st_mtime_ns
    if getattr(presentation_module, "_source_mtime_ns", None) != source_mtime:
        from importlib import reload
        reload(presentation_module)
        presentation_module._source_mtime_ns = source_mtime

st.set_page_config(page_title="Calgary traffic-safety investigations", layout="wide")
TITLE = ("Where should Calgary focus its next ", "traffic-safety", " investigation?")
LEDE = ("A shortlist of locations to investigate, built from Calgary’s 2025 reported crash incidents. "
        "Set your area, capacity and priorities, then see where to focus and why.")
EXAMPLES = [
    ("Pedestrians and cyclists", "Focus on pedestrians and cyclists."),
    ("Top 10 citywide", "Top 10 across the whole city."),
    ("City roads only", "City roads only."),
]
PLACEHOLDER = "We can investigate five locations in northwest Calgary. Give recent crashes twice the importance."
ss = st.session_state
# Retain reviewed text even when the compact voice option is closed and its
# widget is temporarily absent. Theme reruns must never erase that draft.
ss.voice_transcript = ss.get("voice_transcript", "")


def clear_confirmation():
    ss.pop("reply", None)
    ss.pop("tuning_confirmation", None)


def change_control(key):
    """Widget mirrors update only the named field in the authoritative settings."""
    clear_confirmation()
    if key == "area":
        ss.settings["constraints"]["region"] = planning.engine_region(ss.area)
    elif key in ("capacity", "recent_weight"):
        field = {"capacity": "budget", "recent_weight": "recent_weight"}[key]
        ss.settings["constraints"][field] = ss[key]
    elif key == "priorities":
        if ss.priorities in planning.PRESETS:
            severity, trend, recent = planning.PRESETS[ss.priorities]
            ss.settings["weights"].update(w_severity=severity, w_trend=trend)
            ss.settings["constraints"]["recent_weight"] = recent
    else:
        ss.settings["weights"][key] = ss[key]


def sync_widgets():
    for key, value in planning.widget_values(ss.settings).items():
        if ss.get(key) != value:
            ss[key] = value


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


def submit_reviewed_voice():
    text = ss.get("voice_transcript", "").strip()
    if text:
        ss.pop("transcription_error", None)
        ss.pending_request = text
    else:
        ss.transcription_error = "Enter or transcribe a request before applying it."


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
        planning.confirmation(asked, ss.settings) if recognized else
        "Settings unchanged. Try an area, a number of locations, pedestrian/cyclist priorities, "
        "recent crash weighting, or road exclusions."
    )}
    if result.get("plan"):
        reply["comparison"] = compare(previous, result)
    ss.reply = reply
    # Apply and build the text reply before the optional speech request. Audio
    # belongs to this reply only; ordinary reruns never synthesize it again.
    key = briefing.api_key() if recognized and result.get("plan") else None
    if key:
        config = briefing.speech_config()
        with st.spinner("Preparing spoken confirmation…"):
            try:
                reply["audio"] = briefing.synthesize(
                    reply["text"], key, voice_id=config["voice_id"],
                    model_id=config["tts_model"], action="Reading the confirmation",
                )
            except briefing.SpeechError as exc:
                reply["audio_error"] = "Request applied. " + str(exc)
            else:
                reply["audio_fresh"] = True
    return result


ss.setdefault("dark_mode", False)
mast_col, theme_col = st.columns([5, 1])
with mast_col:
    st.markdown(ui.masthead(), unsafe_allow_html=True)
with theme_col:
    st.toggle("Dark mode", key="dark_mode")
st.html(f"<style>{ui.theme_css(ss.dark_mode)}</style>")
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
        ss.tuning_confirmation = "The agent picked the weights. Updated: " + planning.summary(ss.settings) + "."
    if result is None:
        previous = ss.get("last_result")
        # Theme, focus and export reruns retain the exact applied result (including
        # its tuning trace). Settings changes still rerank through the engine.
        result = (previous if previous and planning.from_result(previous) == ss.settings else
                  get_result(ss.settings["weights"], tune=False, constraints=ss.settings["constraints"]))
except ResultShapeError as exc:
    st.error(str(exc))
    st.stop()

ss.settings = planning.from_result(result)
sync_widgets()
for problem in consistency_warnings(result):
    st.warning(f"Result check: {problem}")
plan = result.get("plan")
interactive = bool(plan)
speech_key = briefing.api_key() if interactive else None
speech_config = briefing.speech_config() if interactive else None
rows = ui.recommended_rows(result)
budget = plan["constraints"]["budget"] if plan else len(rows)
region = plan["constraints"]["region"] if plan else None
names = briefing.location_names(result)
st.markdown(ui.hero(TITLE, LEDE, result["dataset"]), unsafe_allow_html=True)
st.markdown(ui.figures(result), unsafe_allow_html=True)
st.html(ui.recommendation_link())
st.markdown(ui.step(1, "Choose what you can investigate"), unsafe_allow_html=True)

controls_col, ask_col = st.columns([1, 1], gap="large")
with controls_col, st.container(key="controls"):
    st.markdown(ui.card_head("Your settings"), unsafe_allow_html=True)
    st.selectbox("Area", list(planning.AREA_OPTIONS), key="area",
                 format_func=planning.AREA_OPTIONS.__getitem__,
                 on_change=change_control, args=("area",), disabled=not interactive)
    st.number_input("How many locations can your team investigate?", min_value=1, max_value=20,
                    step=1, key="capacity", on_change=change_control, args=("capacity",), disabled=not interactive)
    st.selectbox("Safety priorities", [*planning.PRESETS, "Custom priorities"], key="priorities",
                 on_change=change_control, args=("priorities",), disabled=not interactive)
    st.caption(planning.PRESET_NOTES[ss.priorities])
    st.checkbox("Exclude Deerfoot and Stoney locations", key="exclude_provincial",
                on_change=change_control, args=("exclude_provincial",), disabled=not interactive,
                help="Excludes grouped location names containing Deerfoot or Stoney; it does not verify road ownership.")
    st.button("Let the agent pick the weights", key="agent_pick", on_click=request_tuning, type="primary",
              width="stretch", disabled=not interactive)
    st.caption("Tries weight options on earlier 2025 reports for your capacity and keeps the plain crash count unless one does better.")
    st.button("Reset settings", on_click=submit_example, args=("Reset.",), type="tertiary", disabled=not interactive,
              help="All Calgary, up to 20 locations, crash totals, Deerfoot and Stoney excluded.")
with ask_col, st.container(key="planner"):
    st.markdown(ui.card_head("Or just ask", "Type a capacity, an area or a priority in plain words."), unsafe_allow_html=True)
    with st.form("planner_form", border=False):
        st.text_input("Your planning request", key="planner_text", placeholder=PLACEHOLDER, disabled=not interactive)
        st.form_submit_button("Update recommendations", on_click=submit_typed, type="primary", width="stretch", disabled=not interactive)
    st.caption("Examples")
    for label, text in EXAMPLES:
        st.button(label, on_click=submit_example, args=(text,), key=f"example_{label}", type="tertiary", disabled=not interactive)
    if interactive:
        st.toggle("Speak your request", key="voice_open")
        if not speech_key:
            st.caption("Speech is optional and needs an ELEVENLABS_API_KEY. Typed planning works without a key.")
        if ss.get("voice_open"):
            st.caption("Record up to 90 seconds. No microphone? Allow access in your browser, or type instead.")
            recording = st.audio_input("Record a planning request", key="planner_audio", disabled=not speech_key,
                                       help="Audio is sent to ElevenLabs only when you click Transcribe recording.")
            data = recording.getvalue() if recording is not None else None
            recording_key = briefing.recording_id(data, speech_config["stt_model"]) if data is not None else None
            completed = ss.get("completed_transcription", {})
            if recording_key != ss.get("recording_seen"):
                ss.recording_seen = recording_key
                ss.pop("transcription_error", None)
                if recording_key is not None:
                    ss.voice_transcript = completed.get("text", "") if completed.get("recording_id") == recording_key else ""
            already_transcribed = recording_key is not None and completed.get("recording_id") == recording_key
            if st.button("Transcribe recording", key="transcribe_recording", disabled=not speech_key or data is None or already_transcribed) and not already_transcribed:
                ss.pop("transcription_error", None)
                with st.spinner("Transcribing recording…"):
                    try:
                        transcript = briefing.transcribe(data, speech_key, model_id=speech_config["stt_model"])
                    except briefing.SpeechError as exc:
                        ss.transcription_error = str(exc)
                    else:
                        ss.voice_transcript = transcript
                        ss.completed_transcription = {"recording_id": recording_key, "text": transcript}
            if ss.get("transcription_error"):
                st.warning(ss.transcription_error)
            if already_transcribed:
                st.caption("This recording is transcribed. Review or edit the text, then apply it.")
            # Outside a form so edited text is retained on focus/theme reruns.
            # Applying is still a separate, explicit planner action.
            st.text_area("Review transcription", key="voice_transcript", height=100,
                         help="Edit road names or settings before applying. Nothing is applied automatically.")
            st.button("Apply request", on_click=submit_reviewed_voice, width="stretch")
            st.caption('Try: “Top 20 in northeast Calgary.” “Find the best ranking automatically.”')
    if ss.get("reply"):
        st.markdown(ui.reply(ss.reply), unsafe_allow_html=True)
        if ss.reply.get("audio"):
            st.audio(ss.reply["audio"], format="audio/mpeg",
                     autoplay=ss.reply.pop("audio_fresh", False))
        if ss.reply.get("audio_error"):
            st.warning(ss.reply["audio_error"])

if not interactive:
    st.caption("Sample output: planning controls are unavailable until the engine is connected. These are illustrative recommendations.")
where = f"{ui.REGIONS[region]} Calgary" if region else "Calgary"
st.markdown(ui.step(2, "Where to investigate", f"Up to {budget} locations in {where}."), unsafe_allow_html=True)
if ss.get("tuning_confirmation") and result.get("agent_iterations"):
    st.html(ui.agent_result(result))
with st.container(key="recommendation_summary"):
    # Dedicated HTML rendering keeps the panel in normal flow and avoids
    # Markdown rewriting its heading/list. Always use the current applied result.
    st.html(ui.recommendation_summary(result))
    if interactive:
        current_briefing = briefing.briefing_id(result, speech_config)
        if ss.get("summary_audio", {}).get("briefing_id") != current_briefing:
            ss.pop("summary_audio", None)
        if ss.get("speech_error_id") != current_briefing:
            ss.pop("speech_error", None)
        if st.button("Read summary aloud", key="read_summary", disabled=not speech_key, type="tertiary", icon=":material/volume_up:",
                     help="Optional spoken summary. Needs an ElevenLabs key." if not speech_key else "Generate a spoken summary, then press play."):
            ss.pop("speech_error", None)
            if not ss.get("summary_audio"):
                with st.spinner("Preparing spoken summary…"):
                    try:
                        audio = briefing.synthesize(briefing.build_script(result), speech_key,
                                                   voice_id=speech_config["voice_id"], model_id=speech_config["tts_model"])
                    except briefing.SpeechError as exc:
                        ss.speech_error = str(exc)
                        ss.speech_error_id = current_briefing
                    else:
                        ss.summary_audio = {"briefing_id": current_briefing, "bytes": audio}
        if not speech_key:
            st.caption("Spoken summary is available with an ElevenLabs key.")
        if ss.get("speech_error"):
            st.warning(ss.speech_error)
        if ss.get("summary_audio"):
            st.caption("Spoken summary of the current recommendations. Press play to listen.")
            st.audio(ss.summary_audio["bytes"], format="audio/mpeg", autoplay=False)
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
        map_style=pdk.map_styles.DARK if ss.dark_mode else pdk.map_styles.LIGHT,
        initial_view_state=pdk.ViewState(latitude=float(shown["lat"].mean()), longitude=float(shown["lon"].mean()), zoom=11.2 if region else 10.4),
        layers=[
            pdk.Layer("ScatterplotLayer", data=points, get_position=["lon", "lat"], get_radius=18,
                      radius_units="'pixels'", get_fill_color=[184, 58, 27, 235], stroked=True,
                      get_line_color=[251, 249, 244], line_width_min_pixels=2, pickable=True),
            pdk.Layer("TextLayer", data=points, get_position=["lon", "lat"], get_text="label", get_size=14,
                      get_color=[255, 255, 255], font_family="'system-ui, sans-serif'", font_weight=600,
                      get_text_anchor="'middle'", get_alignment_baseline="'center'"),
        ],
        tooltip={"text": "#{rank} · {name}\n{incidents} reported crashes\n{pedestrian_or_cyclist} pedestrian/cyclist reports\n{selection_reason}",
                 "style": {"backgroundColor": "#1c1a17", "color": "#f4f0e8", "fontSize": "14px", "maxWidth": "340px"}},
    )
    map_col, list_col = st.columns([1.05, 1], gap="large")
    with map_col:
        st.pydeck_chart(deck, height=520)
        st.caption("Numbers match the list. Each marker sits at the median reported position of its location.")
    with list_col:
        st.markdown(ui.shortlist(rows, result), unsafe_allow_html=True)

st.markdown(ui.step(3, "Why these locations are priorities", "The top three, explained from reported incidents."), unsafe_allow_html=True)
st.markdown(ui.movers(result, lambda k: briefing.display_name(names, k)), unsafe_allow_html=True)
st.markdown(ui.section(3, "How your priorities affect the recommendations"), unsafe_allow_html=True)
st.markdown(ui.ranking_changes(result, lambda k: briefing.display_name(names, k)), unsafe_allow_html=True)
with st.expander("Advanced controls", expanded=False):
    st.caption("Sliders change weight; they do not exclude other crash types. Report types come from incident descriptions, not confirmed injury severity.")
    st.slider("Give more priority to pedestrian/cyclist and other crash indicators", 0.0, 1.0, step=0.05, key="w_severity", on_change=change_control, args=("w_severity",), disabled=not interactive,
              help="Higher values give extra importance to pedestrian/cyclist reports, multi-vehicle crashes, and crashes blocking multiple lanes.")
    st.slider("Give more priority to locations with increasing crashes", 0.0, 1.0, step=0.05, key="w_trend", on_change=change_control, args=("w_trend",), disabled=not interactive,
              help="Higher values prioritize the smoothed ratio of July–December to January–June 2025 crash reports.")
    st.slider("Give more priority to recent crashes", 1.0, 5.0, step=0.5, key="recent_weight", on_change=change_control, args=("recent_weight",), disabled=not interactive,
              help="Higher values multiply July–December 2025 reports in both crash counts and incident-indicator points for the full-year ranking; January–June reports keep their usual importance.")
    st.caption(f"Current weights: pedestrian, cyclist and incident {ss.w_severity:.2f}; rising crashes {ss.w_trend:.2f}; recency {ss.recent_weight:g}×.")
    st.button("Test ranking options automatically", on_click=request_tuning, disabled=not interactive)
    st.caption("Same search as the agent button above. Keeps your area, road scope and recency; it does not show crash reduction.")
with st.expander("About the data and attribution", expanded=False):
    d = result["dataset"]
    st.markdown(f"{d['rows_loaded']:,} rows loaded, {d['rows_dropped']:,} dropped, {d['rows_used']:,} used. These counts cover the full dataset, before your area and road filters.")
    st.write(d["source"])
    st.write("Rows set aside: " + d["drop_reason"] + ". Records missing location, coordinates, date, or description are also excluded.")
    st.write("Location names are normalized and grouped; a group can represent a corridor or approximate cluster, rather than a verified intersection. Areas use the most frequently reported quadrant in each group.")
    st.markdown("Source: [City of Calgary Traffic Incidents](https://data.calgary.ca/Transportation-Transit/Traffic-Incidents/35ra-9556). Contains information licensed under the Open Government Licence – City of Calgary.")
    st.markdown(ui.PHOTO_CREDITS)
st.markdown(ui.footer(briefing.FOOTER, ""), unsafe_allow_html=True)
ss.last_result = result
