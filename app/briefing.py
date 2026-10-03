import os

import streamlit as st

FOOTER = "This ranks where harm was reported in 2025. It does not predict or prevent crashes."
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
MODEL_ID = "eleven_multilingual_v2"


def location_names(result):
    names = {r["location_key"]: r["name"] for r in result["baseline"]["top20"] if r.get("name")}
    names.update({r["location_key"]: r["name"] for r in result["top20"]})
    return names


def build_script(result):
    names = location_names(result)
    data = result["dataset"]
    lines = [
        "Morning safety briefing.",
        f"{data['rows_used']:,} reported crashes, ranked by harm rather than by count.",
        "The top five:",
    ]
    for r in sorted(result["top20"], key=lambda r: r["rank"])[:5]:
        line = f"Number {r['rank']}, {r['name']}, with {r['incidents']} incidents"
        if r["pedestrian_or_cyclist"]:
            line += f", {r['pedestrian_or_cyclist']} involving a pedestrian or cyclist"
        lines.append(line + ".")
    if result["movers"]:
        lines.append("What changed against a count-only list:")
    for m in result["movers"]:
        name = names.get(m["location_key"], m["location_key"])
        reason = m["reason"].strip()
        if reason and reason[-1] not in ".!?":
            reason += "."
        lines.append(f"{name} moved {m['direction']} from {m['from_rank']} to {m['to_rank']}. {reason}")
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
