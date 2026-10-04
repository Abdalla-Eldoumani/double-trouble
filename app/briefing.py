import os

import streamlit as st

FOOTER = "A shortlist for investigation, based on reported crashes in 2025. It does not predict or prevent crashes."
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
MODEL_ID = "eleven_multilingual_v2"
QUADRANTS = {"nw", "ne", "sw", "se"}


def location_names(result):
    names = {r["location_key"]: r["name"]
             for r in result["baseline"]["top20"] + result["movers"] if r.get("name")}
    names.update({r["location_key"]: r["name"] for r in result["top20"]})
    return names


def display_name(names, key):
    # Locations outside the harm top 20 carry only their key, which is the lowercased name.
    if key in names:
        return names[key]
    return " ".join(w.upper() if w in QUADRANTS else w.capitalize() for w in key.split())


def build_script(result):
    names = location_names(result)
    data = result["dataset"]
    lines = [
        "Morning safety briefing.",
        f"{data['rows_used']:,} reported crashes, " + (
            "ranked by harm." if any(result["weights"][k] for k in ("w_severity", "w_trend"))
            else "ranked by crash count."),
        "The top five:",
    ]
    for r in sorted(result["top20"], key=lambda r: r["rank"])[:5]:
        line = f"Number {r['rank']}, {r['name']}, {r['incidents']} incidents"
        if r["pedestrian_or_cyclist"]:
            line += f", {r['pedestrian_or_cyclist']} involving a pedestrian or cyclist"
        lines.append(line + ".")
    if result["movers"]:
        lines.append("Biggest changes against a count-only list:")
    # Reasons stay on screen; read aloud they push the briefing well past 40 seconds.
    for m in result["movers"]:
        name = display_name(names, m["location_key"])
        lines.append(f"{name}, {m['direction']} from {m['from_rank']} to {m['to_rank']}.")
    lines.append(FOOTER)
    return " ".join(lines)


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        return key
    try:
        return st.secrets.get("ELEVENLABS_API_KEY")
    except Exception:
        # No secrets file is a normal state locally; the caller hides the button.
        return None


STT_MODEL_ID = "scribe_v2"


def transcribe(audio, key):
    """Speech to text for a recorded planner request."""
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=key)
    return client.speech_to_text.convert(file=audio, model_id=STT_MODEL_ID).text.strip()


@st.cache_data(show_spinner="Generating audio...")
def synthesize(script, _key):
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=_key)
    audio = client.text_to_speech.convert(
        voice_id=VOICE_ID,
        text=script,
        model_id=MODEL_ID,
        output_format="mp3_44100_128",
    )
    return b"".join(audio)
