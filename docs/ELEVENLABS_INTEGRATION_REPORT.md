# ElevenLabs integration

Implemented 2026-10-04 in `/Users/ibrahimahmed/double-trouble`. The repository, existing speech hooks, planner, tests, and ancestor/repository AGENTS.md locations were inspected first; no applicable AGENTS.md was found. Existing UI changes were preserved. No real credential was created, displayed, or added to Git. No live ElevenLabs request, paid API call, commit, push, merge, or deployment was performed.

## Implementation and files changed

| File | Change |
| --- | --- |
| `app/main.py` | Optional compact voice toggle inside Ask the planner; microphone recorder; explicit transcription action; editable review field; Apply request through the same pending-request/apply_request path as typed planning; explicit summary speech action and manual audio player; session deduplication/invalidation. Refreshes changed speech/presentation modules in long-lived servers. |
| `app/briefing.py` | Lazy SDK initialization; safe environment/secrets lookup; optional model/voice configuration; WAV validation; bounded API requests; safe errors; short factual briefing; recording/result fingerprints. Removed the shared synthesis cache and old long morning briefing. |
| `app/ui.py` | Shared applied summary details for visible and spoken output; existing visible summary appearance/content preserved. |
| `app/style.css` | New transcript field and recorder use the existing light/dark palette, including readable text, borders, focus, and timecode. Road/equipment imagery and overall layout unchanged. |
| `engine/planner.py` | Narrow additions for “all Calgary” and “best ranking automatically”; ranking calculations and search logic unchanged. |
| `.gitignore`, `.streamlit/secrets.toml.example` | Ignore actual Streamlit secrets and local environment files; safe placeholder example with optional voice/model settings. Existing configuration and secret files are untouched. |
| `tests/test_speech.py` | Mocked SDK contracts, state transitions, configuration, errors/retry, result freshness, supported phrases, and Git exclusions. |
| `tests/test_app.py`, `tests/test_app_voice.py` | Update former deferred-speech/long-briefing assertions to the explicit-action integration and supported SDK arguments. |
| `README.md` | Key location, launch command, both speech workflows, optional configuration, and troubleshooting. |
| `docs/ui-checks/check_speech_ui.py`, `docs/ui-checks/speech/` | Reproducible browser UI checks and screenshots. API actions are deliberately never clicked by this audit. |

The engine's scores, validation, top-20 limit, follow-up merging, All Calgary boundary mapping, exclusions, controls, CSV export, priority explanations, and collapsed Advanced controls remain intact. The visible summary stays above export/map/shortlist. No realtime agent, continuous listening, wake word, new LLM, or separate chat/settings application was added. The already-pinned `elevenlabs==2.70.0` SDK and `streamlit==1.65.0` recorder are reused; no dependency changes were required.

## Current documentation checked

Official ElevenLabs documentation and the installed SDK's signatures were checked before implementation:

- Batch speech-to-text uses `speech_to_text.convert(file=..., model_id="scribe_v2")`. The single-channel synchronous response exposes transcript text in `.text`. The app uploads the recorder's WAV bytes with an English language hint, without diarization or audio-event tags. [Create transcript](https://elevenlabs.io/docs/api-reference/speech-to-text/convert).
- Speech synthesis uses `text_to_speech.convert(voice_id=..., text=..., model_id="eleven_multilingual_v2", output_format="mp3_44100_128")`. The SDK yields audio-byte chunks, collected for Streamlit's MP3 player. [Create speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [official Python SDK](https://github.com/elevenlabs/elevenlabs-python).
- Supported model families and defaults were cross-checked with the [official model documentation](https://elevenlabs.io/docs/overview/models). The application does not query model/voice lists or validate account access automatically, avoiding background API calls.

## Behavior and state

**Input:** turn on Speak your request, record, click Transcribe recording, review/edit the transcript, then click Apply request. Recording and transcription never apply settings automatically. The review field is outside a Streamlit form so edits persist on focus/theme reruns; closing the voice option also retains the draft. Typed planning remains equally available. No-key, unavailable-microphone guidance, unusable WAV, empty transcription, authorization/quota/service failure, and unsupported request states are handled without breaking planning.

**Output:** Read summary aloud builds a brief description of the current area, actual count, priorities, road exclusions, and up to three leading locations with observed counts. It uses the same applied settings and rows as the visible summary. Quadrant abbreviations are expanded for speech. Most scripts contain roughly 60–105 words, aiming at 20–40 seconds; very long names/custom priorities reduce the number of spoken locations. Empty results explicitly say none qualify. No internal points, validation metrics, predicted crash reduction, injury-severity claims, or lengthy disclaimer is spoken.

**API discipline:** only transcription/speech button clicks call the SDK. There is no shared speech cache. The latest successful transcript is associated with a SHA-256 fingerprint of recording/model; duplicate transcription is disabled and guarded. Failed attempts can be deliberately retried. Synthesized bytes are kept only in that session; clicking Read summary aloud again for the same result reuses them. Every recommended row, applied setting, and speech configuration participates in the briefing fingerprint, so a changed unspoken location also removes stale audio. Theme reruns preserve drafts/audio and never generate API calls. Audio never autoplays.

SDK initialization is lazy. Network timeouts are 30 seconds and SDK retries are explicitly zero. Synthesis also checks elapsed time and a small output-size limit while collecting chunks. A stalled chunk read is still subject to the network timeout; this is not a separate hard wall-clock cancellation mechanism. Recordings are validated as WAV, 0.1–90 seconds and at most 10 MB. User recordings are never written to repository or temporary files. Only safe error messages reach the UI; raw SDK exceptions, response bodies, credentials, and request details are not logged or displayed by this integration.

## Configuration

Exact local key file: **`/Users/ibrahimahmed/double-trouble/.streamlit/secrets.toml`**. Create it if absent and add this entry, preserving any other entries:

```toml
ELEVENLABS_API_KEY = "paste-your-key-here"
```

Replace the placeholder locally with your key; do not paste it in chat. The real file is ignored by Git. The example file is safe to track. An `ELEVENLABS_API_KEY` environment variable takes precedence; missing/malformed secrets safely leave speech unavailable. `.env` files are ignored but are not automatically loaded.

Optional entries or environment variables:

| Name | Default |
| --- | --- |
| `ELEVENLABS_STT_MODEL_ID` | `scribe_v2` |
| `ELEVENLABS_TTS_MODEL_ID` | `eleven_multilingual_v2` |
| `ELEVENLABS_VOICE_ID` | `JBFqnCBsd6RMkjVDRZzb` |

Launch from the repository root: `.venv/bin/streamlit run app/main.py`. Restart after adding secrets or changing launch environment. Use a supported model and voice available to your account.

## Automated verification

All API endpoints were mocked; no automated test requires a real key or spends credits.

- Focused speech/app/parser tests: **69 passed in 36.37 seconds** after fixing the transcript-form issue.
- Existing suite plus integration tests: **141 passed in 108.33 seconds**.
- Final speech checks after transcript recovery/error clearing and environment-ignore refinements: **25 passed in 15.11 seconds**.
- `compileall` and `git diff --check`: passed.

Coverage includes environment-over-secrets precedence, missing secrets, optional configuration, invalid/empty/oversize-duration audio without API calls, `.text` and chunked-byte response contracts, explicit timeout/no-retry settings, sanitized API errors, no-key startup/typed planning, recording-without-auto-apply, transcript editing, All Calgary follow-ups/control reruns, completed-recording deduplication, deliberate retry, current spoken facts, manual playback, full-result audio invalidation, theme/draft persistence, offline failures, supported example phrases, and ignored secrets with a trackable example.

## Browser verification and remaining limits

The in-app browser plugin was attempted but failed at initialization with a missing `sandboxPolicy` field. Actual UI inspection used isolated headless Google Chrome via the temporary Playwright utility, with 1440 × 1050 desktop and 390 × 844 phone viewports. No microphone permission was requested and no speech API button was clicked.

- Existing server: **`http://localhost:8502`**, PID **4202**, `.venv/bin/streamlit run app/main.py`, working directory this checkout.
- Fresh verification: **`http://localhost:8506`**, PID **5142**, `.venv/bin/python -m streamlit run /Users/ibrahimahmed/double-trouble/app/main.py --server.port 8506 --server.address 127.0.0.1 --server.headless true`, same checkout.
- Port 8501 accepted connections but health/navigation timed out during this task. It was left untouched. The 8502 and fresh 8506 pages were inspected instead; no unrelated process was stopped or reconfigured.

The speech UI audit passed on both responsive servers: disabled speech actions without a key, optional recorder/review controls, reviewed text applied through the planner, All Calgary confirmation, theme-preserved text, dark transcript contrast, one visible summary, no synthesized player before action, and no phone horizontal overflow. Initial screenshot inspection caught the new widgets' white backgrounds in dark mode; their colors were corrected and fresh screenshots inspected. [Audit script](ui-checks/check_speech_ui.py), [running UI evidence](ui-checks/speech/running/), [fresh UI evidence](ui-checks/speech/fresh/).

The existing complete browser regression audit also passed on 8506: summary navigation/visibility in both themes, area/capacity/priorities/planner/tuning/reset updates, All Calgary persistence, map markers and tooltip, zoom controls, actual CSV downloads identical across themes, opaque panels, the 240-pixel equipment photo, subtle road background, and narrow layout. No browser page errors were captured. [Regression results](ui-checks/speech/regression/results.json).

**Not verified live:** actual microphone capture/permission behavior, ElevenLabs account permissions, transcription quality, pronunciation, synthesized-audio quality, or measured speech duration. STT/TTS responses and audio-player creation were verified with mocks in AppTest. Physical mobile devices and other browsers were not tested. Session results are lost on a new session; there is no persistent recording archive. ElevenLabs receives recordings/briefing text when you explicitly invoke it and applies its account retention/billing rules. The application does not claim enterprise zero retention.

## First real test checklist

1. Add your key to the exact local secrets file above; restart with `.venv/bin/streamlit run app/main.py` from this repository. Open the URL Streamlit prints. If port 8501 is occupied, use `--server.port 8507` rather than stopping an unrelated process.
2. Turn on Speak your request, allow microphone access, record “Show the top 20 locations in northeast Calgary,” stop, and click Transcribe recording. Confirm editable text appears and recommendations have not changed yet.
3. Correct any road/area wording, then click Apply request. Confirm Northeast, the capacity, visible summary, map, shortlist, and exported CSV agree.
4. Record/apply “Now show all Calgary.” Change another control and the theme. Confirm All Calgary and the reviewed text persist.
5. Click Read summary aloud, wait for the player, then press play. Check the spoken area/count, priorities, exclusions, and factual leading reasons against the visible summary.
6. Change area or priorities. Confirm the old player disappears; click Read summary aloud again for the new result. For a failed API request, check account permissions/quota and retry deliberately. Typed planning should remain usable throughout.
