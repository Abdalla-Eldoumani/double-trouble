"""Explicit-action speech helpers. Credentials and audio never enter shared caches."""
import hashlib
import io
import json
import os
import re
import time
import wave

import streamlit as st

FOOTER = "A shortlist for investigation, based on reported crashes in 2025. It does not predict or prevent crashes."
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
MODEL_ID = "eleven_multilingual_v2"
STT_MODEL_ID = "scribe_v2"
QUADRANTS = {"nw", "ne", "sw", "se"}
REQUEST_TIMEOUT = 30
REQUEST_OPTIONS = {"timeout_in_seconds": REQUEST_TIMEOUT, "max_retries": 0}
MAX_RECORDING_SECONDS = 90


class SpeechError(Exception):
    """Only safe, user-facing messages; never propagate an SDK response body."""


def location_names(result):
    names = {r["location_key"]: r["name"]
             for r in result["baseline"]["top20"] + result["movers"] if r.get("name")}
    names.update({r["location_key"]: r["name"] for r in result["top20"]})
    return names


def display_name(names, key):
    if key in names:
        return names[key]
    return " ".join(w.upper() if w in QUADRANTS else w.capitalize() for w in key.split())


def spoken_name(name):
    quadrants = {"NW": "northwest", "NE": "northeast", "SW": "southwest", "SE": "southeast"}
    name = name.replace("&", "and")
    return re.sub(r"\b(NW|NE|SW|SE)\b", lambda m: quadrants[m[0]], name)


def build_script(result):
    """About 20–40 seconds: applied scope and up to three factual leading reasons."""
    from app import ui

    details = ui.summary_details(result)
    rows = details["rows"]
    w, c = details["settings"]["weights"], details["settings"]["constraints"]
    priorities = ["crash totals"]
    if w["w_severity"]:
        priorities.append("pedestrian, cyclist, multi-vehicle and blocked-lane reports")
    if w["w_trend"]:
        priorities.append("increasing crash activity")
    if c["recent_weight"] != 1:
        priorities.append(f"July to December reports weighted {c['recent_weight']:g} times")
    lines = [f"For {details['area']}, {len(rows)} locations are recommended for investigation, based on reported 2025 crashes.",
             "Priorities: " + ", ".join(priorities) + ".",
             details["road_scope"] + "."]
    if not rows:
        lines.append("No locations qualify. Try another area or change the road exclusions.")
    for row in rows[:3]:
        reason = f"{row['incidents']} reported crashes"
        if w["w_severity"]:
            reason += f", including {row['pedestrian_or_cyclist']} involving pedestrians or cyclists"
        elif (w["w_trend"] or c["recent_weight"] != 1) and "late" in row:
            reason += f", with {row['late']} in July to December"
        line = f"{spoken_name(row['name'])}: {reason}."
        # Long corridor names and custom priorities can otherwise exceed 40s.
        if len((" ".join(lines) + " " + line).split()) > 105 and len(lines) > 3:
            break
        lines.append(line)
    return " ".join(lines)


def setting(name, default=None):
    value = os.environ.get(name)
    if value and value.strip():
        return value.strip()
    try:
        value = st.secrets.get(name)
    except Exception:
        # Missing or invalid local secrets must never break offline planning.
        return default
    return value.strip() if isinstance(value, str) and value.strip() else default


def api_key():
    key = setting("ELEVENLABS_API_KEY")
    return None if key == "paste-your-key-here" else key


def speech_config():
    return {"voice_id": setting("ELEVENLABS_VOICE_ID", VOICE_ID),
            "tts_model": setting("ELEVENLABS_TTS_MODEL_ID", MODEL_ID),
            "stt_model": setting("ELEVENLABS_STT_MODEL_ID", STT_MODEL_ID)}


def _client(key):
    if not key:
        raise SpeechError("Add ELEVENLABS_API_KEY to .streamlit/secrets.toml or the environment to enable speech.")
    from elevenlabs.client import ElevenLabs
    return ElevenLabs(api_key=key, timeout=REQUEST_TIMEOUT)


def _failure(exc, action):
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return f"{action} was not authorized. Check your local API key and speech permissions."
    if status == 429:
        return f"{action} is unavailable due to quota or rate limits. Check your ElevenLabs account, then retry."
    return f"{action} failed or timed out. Check your connection and voice/model configuration, then retry."


def recording_id(data, model):
    return hashlib.sha256(model.encode() + b"\0" + data).hexdigest()


# A 16-bit recording whose loudest sample never passes 64 (0.2% of full scale) is a muted microphone.
QUIET_PEAK = 64
QUIET_MESSAGE = ("The recording is almost silent. Check that the browser is using the right microphone "
                 "and that it is not muted, then record again.")
UNCLEAR_MESSAGE = ("That did not come through as an English request. Speak closer to the microphone "
                   "and record again, or type the request.")


def _peak(frames):
    import numpy as np
    samples = np.frombuffer(frames[: len(frames) - len(frames) % 2], dtype="<i2")
    return int(np.abs(samples.astype("int32")).max()) if samples.size else 0


def validate_recording(data):
    if not isinstance(data, bytes) or not data or len(data) > 10_000_000:
        raise SpeechError("The recording is empty or too large. Record a short request and try again.")
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            seconds = audio.getnframes() / audio.getframerate()
            frames = audio.readframes(audio.getnframes())
            if not frames or seconds < 0.1:
                raise SpeechError("The recording is too short or empty. Record a spoken request and try again.")
            if seconds > MAX_RECORDING_SECONDS:
                raise SpeechError("Keep recordings under 90 seconds, then try again.")
            if audio.getsampwidth() == 2 and _peak(frames) < QUIET_PEAK:
                raise SpeechError(QUIET_MESSAGE)
    except (wave.Error, EOFError, ValueError, ZeroDivisionError):
        raise SpeechError("The recording could not be read. Record it again using the microphone control.") from None


def transcribe(audio, key, model_id=None):
    """One bounded batch request; Streamlit's recorder supplies in-memory WAV."""
    data = audio[1] if isinstance(audio, tuple) else audio
    validate_recording(data)
    try:
        response = _client(key).speech_to_text.convert(
            file=("request.wav", data, "audio/wav"),
            model_id=model_id or STT_MODEL_ID, language_code="eng",
            tag_audio_events=False, diarize=False, request_options=dict(REQUEST_OPTIONS),
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise SpeechError("No speech was transcribed. Record a clear spoken request and try again.")
        # Near-silent clips come back as a filler word in another script (for example "うん。").
        if len(re.findall(r"[A-Za-z]", text)) < 3:
            raise SpeechError(UNCLEAR_MESSAGE)
        return text.strip()
    except SpeechError:
        raise
    except Exception as exc:
        raise SpeechError(_failure(exc, "Transcription")) from None


def synthesize(script, key, voice_id=None, model_id=None):
    """Collect the SDK's MP3 byte iterator. No global audio cache or auto playback."""
    started = time.monotonic()
    try:
        chunks = _client(key).text_to_speech.convert(
            voice_id=voice_id or VOICE_ID, text=script, model_id=model_id or MODEL_ID,
            output_format="mp3_44100_128", request_options=dict(REQUEST_OPTIONS),
        )
        audio = bytearray()
        for chunk in chunks:
            if time.monotonic() - started > REQUEST_TIMEOUT or len(audio) > 5_000_000:
                raise SpeechError("Reading the summary timed out. Please retry.")
            audio.extend(chunk)
        if not audio:
            raise SpeechError("No summary audio was returned. Please retry.")
        return bytes(audio)
    except SpeechError:
        raise
    except Exception as exc:
        raise SpeechError(_failure(exc, "Reading the summary")) from None


def briefing_id(result, config):
    """Invalidate even when a changed recommendation falls outside the spoken top three."""
    from app import ui
    payload = {"settings": ui.summary_details(result)["settings"],
               "rows": ui.recommended_rows(result), "config": config}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
