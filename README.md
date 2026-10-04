# Calgary collision-hotspot shortlist

Shortlists Calgary locations for traffic-safety investigation using reported 2025 crashes. Choose an area, capacity, and priorities, or use the deterministic typed planner. A visible summary, map, location reasons, and CSV export support the investigation workflow. The session's Dark mode toggle preserves planning settings. Advanced controls start collapsed; technical evaluation stays in the engine and tests.

Built for the IEEE YP Industry Hackathon 2026, Energy and Infrastructure Systems, Case 5.

## Run

Needs Python 3.12 or newer (the pinned numpy does not install on 3.11).

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q
.venv/bin/python -m engine.agent --out out/result.json
.venv/bin/streamlit run app/main.py
```

Open `http://localhost:8501`. The opening preset and Reset settings use crash totals, all Calgary, up to 20 locations, and name-based Deerfoot/Stoney exclusion. The CLI command above runs the automatic weight search; the app starts with the count-only preset.

## Optional ElevenLabs speech

Create **`.streamlit/secrets.toml`** in the repository and paste your key there:

```toml
ELEVENLABS_API_KEY = "paste-your-key-here"
```

Use `.streamlit/secrets.toml.example` as a reference; preserve any existing entries in your secrets file. The real file and local `.env` files are ignored by Git. Alternatively, set `ELEVENLABS_API_KEY` in the environment that launches Streamlit; it takes precedence over the secrets file. `.env` files are not loaded automatically. Never paste your key into chat or commit it.

Launch from the repository root:

```bash
.venv/bin/streamlit run app/main.py
```

In **Ask the planner**, turn on **Speak your request**, record a short request, and click **Transcribe recording**. Review and edit **Review transcription**, then click **Apply request**. The same offline planner handles both speech transcripts and typed requests, retaining settings you do not mention. Supported requests include “Show the top 20 locations in northeast Calgary,” “Give pedestrian and cyclist crashes more importance,” “Exclude Deerfoot and Stoney Trail,” “Now show all Calgary,” and “Find the best ranking automatically.” Unsupported requests leave settings unchanged; this is a rule-based planner, not a general conversational assistant.

Beside the visible recommendation summary, click **Read summary aloud**, then press play in the audio player. Audio describes the current investigation recommendations; changing recommendations removes old audio. Theme changes preserve the transcript and current audio. No recording, transcription, synthesis, or playback happens automatically. Transcription and speech generation send audio or briefing text to ElevenLabs only when requested and may use your account's credits.

Optional environment variables or secrets entries: `ELEVENLABS_VOICE_ID` (default George, `JBFqnCBsd6RMkjVDRZzb`), `ELEVENLABS_STT_MODEL_ID` (default `scribe_v2`), and `ELEVENLABS_TTS_MODEL_ID` (default `eleven_multilingual_v2`). Use models and a voice available to your account; no separate settings screen is needed.

If speech is disabled, check the key's spelling and restart Streamlit after adding secrets or changing its environment. If the microphone is unavailable, allow microphone access in your browser and use localhost or HTTPS; typed planning remains available. Keep recordings under 90 seconds. For empty transcripts, record clear speech and retry. For authorization, quota, connection, or voice/model errors, check your ElevenLabs account/configuration and retry deliberately. Requests have 30-second network timeouts and no automatic retries. See [the integration report](docs/ELEVENLABS_INTEGRATION_REPORT.md) for mocked verification and a first-live-test checklist.

## Data and ranking

The bundled City of Calgary Traffic Incidents feed is an incident-report dataset, not a complete police collision database. Cleaning removes non-crash descriptions and records lacking required fields. Normalized location names remove travel-direction words and group reports; groups may represent corridors or approximate clusters, rather than verified intersections. Median coordinates place markers, and the most frequent quadrant determines each group's area. See [data/README.md](data/README.md).

The baseline ranks by raw full-year crash counts with the same area, road exclusions, and capacity as the applied recommendations. Ties are deterministic. Additional scoring signals use description-based indicator points (one per crash, plus three for pedestrian/cyclist involvement, one for multi-vehicle reports, and one for multiple blocked lanes; indicators can overlap), the smoothed ratio of later-half to earlier-half crash counts, and an optional recency multiplier applied to later-half counts and points. These are proxy signals, not confirmed injury severity or injury counts.

Presets map to `(incident-indicator weight, increasing-activity weight, recency multiplier)`: Crash totals `(0, 0, 1)`, Balanced priorities `(0.5, 0.5, 1)`, Pedestrians and cyclists `(1, 0, 1)`, Recent activity `(0, 0, 2)`. The pedestrian/cyclist preset also weights multi-vehicle and blocked-lane descriptions.

## Historical evaluation and limitations

Automatic search compares 15 weight pairs at 20 locations, retaining the chosen area, road exclusions, and recency. It selects the greatest later-period proxy-point capture; ties retain simpler weights. Display capacity affects the shortlist and its evaluation, not the search objective. Rejected candidates and negative outcomes remain in the result contract.

The primary window selects locations from January–August and evaluates September–December 2025. The secondary window selects from January–June and evaluates July–December. Recency weights the later half of each training window; evaluation points are unweighted. The primary evaluation is used to choose weights. The windows overlap, so the secondary evaluation is not an independent holdout. Neither demonstrates crash reduction or future performance.

Reproduced on the bundled dataset on 2026-10-04 with `engine.agent.run(tune=False)` and `run(tune=True)`, using all Calgary, 20 locations, Deerfoot/Stoney excluded, recency 1×:

- Cleaning retained 6,572 of 6,984 rows (412 removed).
- Automatic search chose indicator weight 1 and increasing-activity weight 0. Primary captured points: baseline 262 versus selected weights 288, out of 3,143 eligible points. Result-contract shares, rounded by the engine: 8.34% versus 9.16%.
- Secondary shares: 8.07% baseline versus 8.20% selected weights. These overlapping-window results are tuning diagnostics.
- Increasing both indicator and activity weights to 1 performs worse: primary capture 242/3,143 (7.70%), secondary share 6.06%. Negative results are preserved.

Header photos are locally stored real photographs of illustrative scenes outside Calgary. See [app/assets/ATTRIBUTION.md](app/assets/ATTRIBUTION.md) for creators, source pages, licenses, and adjustments. See [docs/UI_UPDATE_REPORT.md](docs/UI_UPDATE_REPORT.md) for implementation and verification details.
