# Initial Local Test and Demo Readiness

## Verdict

**B) Ready after setup only.**

The current `main` branch is internally coherent: the Streamlit app, planner, engine, dataset, styling, fonts, configuration, and tests are present. No source-level blocker was found. It is not ready to run in the current shell because there is no project virtual environment and the required packages are not installed.

## 1. Project readiness

- Current branch: `main`, clean and aligned with `origin/main` at `9c30861`.
- The app is present at `app/main.py`; its local modules `app/briefing.py`, `app/load.py`, and `app/ui.py` exist.
- Engine modules `engine/agent.py`, `engine/data.py`, `engine/score.py`, and `engine/planner.py` exist and use consistent imports.
- Referenced CSS and bundled Fraunces/Geist font files exist.
- The required CSV exists at `data/calgary_traffic_incidents_2025.csv`.
- No unresolved merge entries, conflict markers, `TODO`, `FIXME`, or `HACK` markers were found.
- All app, engine, and test Python files parse successfully.

The Streamlit app appears runnable after dependency installation. One demo-level mismatch is visible: the page copy describes ranking by harm, but first load uses the engine defaults `w_severity=0`, `w_trend=0`, and `exclude_provincial=True`. Thus, the first result is count-only until a slider, planner request, or tuning run changes the weights. This is not a startup error, but the opening state does not demonstrate severity ranking.

## 2. Dependencies and environment

The tracked `README.md` requires **Python 3.12 or newer**, specifically noting that pinned NumPy does not install on Python 3.11. This machine has Python 3.13.2 and 3.14.0; Python 3.13 is the recommended available interpreter for the initial test.

`requirements.txt` pins:

```text
pandas==3.0.6
numpy==2.5.3
streamlit==1.65.0
pydeck==0.9.3
elevenlabs==2.70.0
pytest==9.1.1
```

The declared versions are consistent with the README's Python 3.12+ requirement. No dependency conflict is evident from repository files, but installation has not yet been executed in a clean environment on this machine. The existing global Python 3.13 environment has older pandas/NumPy and lacks Streamlit, pydeck, ElevenLabs, and pytest.

ElevenLabs is optional for app startup. `app/briefing.py` imports the ElevenLabs client lazily inside speech functions, so the ranking app and typed planner do not need a configured key. The sole expected secret is:

```text
ELEVENLABS_API_KEY
```

It is read first from the environment and then from Streamlit secrets. `.streamlit/secrets.toml` is explicitly ignored by `.gitignore` and was confirmed with `git check-ignore`.

## 3. App startup

Running:

```bash
streamlit run app/main.py
```

follows this path:

1. `app/main.py` calculates the repository root and inserts it into `sys.path`.
2. It imports pandas, pydeck, Streamlit, `app.briefing`, `app.ui`, and `app.load`.
3. `app.load.get_result()` imports `engine.agent` and calls `run()`.
4. `engine.agent` imports the loader and scoring functions.
5. `engine.data` resolves the CSV relative to its own file as `../data/calgary_traffic_incidents_2025.csv`, which exists and has the expected seven-column header plus 6,984 records.
6. On first load, `get_result()` defaults to `tune=False`; the engine uses count-only weights and excludes Deerfoot/Stoney locations.
7. The returned result is shape-validated before rendering.

If the engine import fails, the app can display `contract/sample_output.json` with a visible fallback warning. With the present files and installed dependencies, that fallback should not be needed. Data-loading or computation exceptions are not converted to the fixture fallback.

Without an ElevenLabs key, startup remains valid: microphone input and audio playback controls are suppressed, typed planning stays enabled, and the briefing is displayed as text.

Expected first-load UI:

- branded masthead, problem statement, and dataset figures;
- typed planner input and four example buttons;
- a notice that voice input is off if no key is configured;
- severity and trend sliders at zero;
- provincial-road exclusion enabled;
- top-20 Calgary map and shortlist ledger;
- movers section;
- count-only comparison/slope chart;
- an empty agent-search state prompting the user to tune;
- morning safety briefing text and data caveat footer.

## 4. Core functionality

| Function | Readiness |
|---|---|
| Initial hotspot ranking | Should work from the bundled CSV |
| Map rendering | Should work; the pydeck Light basemap may need internet access |
| Top-20 shortlist | Should work |
| Count-only comparison | Should work |
| Severity/trend sliders | Should rerun the engine with explicit weights |
| Provincial-road toggle | Should include/exclude name-matched Deerfoot and Stoney locations |
| Agent tuning | Should test the fixed 15-candidate weight grid |
| Movers/explanations | Should work when the chosen ranking differs from count-only |
| Typed planner requests | Should work offline after dependencies are installed |
| Voice planner requests | Require key, network access, and browser microphone permission |
| ElevenLabs spoken replies | Require valid key, endpoint access, quota, and network |
| Morning safety briefing | Text always; audio only with ElevenLabs |

The engine and parser do not use an LLM. Planner behavior is deterministic regular-expression parsing.

## 5. Voice-planner flow

The implemented flow is:

```text
Streamlit st.audio_input
  -> recorded WAV tuple
  -> app.briefing.transcribe()
  -> ElevenLabs speech_to_text.convert(model_id="scribe_v2")
  -> engine.planner.parse()
  -> engine.agent.run(weights, constraints)
  -> engine.planner.compare() and explain()
  -> app.briefing.synthesize()
  -> ElevenLabs text_to_speech.convert()
  -> Streamlit MP3 playback
```

Text-to-speech uses voice `JBFqnCBsd6RMkjVDRZzb`, model `eleven_multilingual_v2`, and output format `mp3_44100_128`.

Failure and fallback behavior:

- Missing key: microphone and audio controls are hidden; typed requests and briefing text remain.
- STT exception: no voice-driven rerank occurs; the app displays the exception class and tells the user to type instead.
- Empty transcript: no rerank; the app asks the user to retry or type.
- Unrecognized request: settings remain unchanged and the explanation says no changeable setting was detected.
- Planner-reply TTS failure: reranking and text explanation remain; an audio error is displayed.
- Morning-briefing TTS failure: an error is displayed and the generated script remains visible.

Requests definitely supported by `engine/planner.py` include:

```text
Prioritize recent crashes twice as much, only show northwest Calgary, and assume we can only investigate five intersections.
```

```text
Focus on pedestrians and cyclists.
```

```text
Now show me the northeast instead.
```

```text
Include Deerfoot and Stoney.
```

```text
Let the agent tune it.
```

Also supported are `Reset.`, `Just count crashes.`, `City roads only.`, and `Top 10 across the whole city.`

## 6. Tests

Test files:

- `tests/test_engine.py` — engine contract, ranking, cleaning, weights, explanations, and runtime.
- `tests/test_engine_planner.py` — parsing, constraints, comparisons, explanations, and constrained runtime.
- `tests/test_app.py` — fixture fallback, result validation, controls, real-engine rendering, visual builders, and briefing audio caching.
- `tests/test_app_voice.py` — typed planning, follow-ups, provincial tuning, mocked TTS, and mocked STT.

Exact full-suite command:

```bash
.venv/bin/python -m pytest tests -q
```

The suite could not be run during this review because `.venv` does not exist and the available global interpreters do not have pytest or all runtime dependencies installed. This is an environment limitation, not an observed test failure.

No test looks certain to fail from static inspection. The most potentially fragile checks are the two assertions requiring full engine runs in under two seconds and Streamlit tests tied to exact widget labels/page markup. ElevenLabs tests use mocked clients and should not call the live service.

## 7. Initial demo readiness

**Classification: B) Ready after setup only.**

Reasons:

- No obvious code, import, merge, asset, or data-path blocker was found.
- The app is now merged into `main` and its local dependencies are present.
- Missing ElevenLabs credentials do not block launch or typed operation.
- A Python environment and pinned packages still need to be installed.
- The test suite and live Streamlit startup have not yet been executed in that clean environment.
- Live ElevenLabs and map-tile network access should be verified before presenting.

README and implementation are now mostly aligned. The main remaining messaging mismatch is the harm-ranking description versus the initial count-only weights.

## 8. Exact commands

From the repository root, use the installed Python 3.13:

```bash
cd /Users/ibrahimahmed/double-trouble

python3.13 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python -m pytest tests -q
python -m engine.agent --out out/result.json
```

For a temporary key that is not written to disk:

```bash
read -s "ELEVENLABS_API_KEY?ElevenLabs API key: "
export ELEVENLABS_API_KEY
echo
```

Alternatively, create the gitignored `.streamlit/secrets.toml` locally with:

```toml
ELEVENLABS_API_KEY = "your-key"
```

Start Streamlit:

```bash
streamlit run app/main.py
```

Then open `http://localhost:8501`.

## 9. First-test checklist

- Confirm the page loads with no engine-fallback or result-consistency warning.
- Confirm the map and 20 shortlist rows appear.
- Set severity to `1.0` and verify ranks/movers change.
- Toggle provincial roads and verify Deerfoot/Stoney behavior changes.
- Click **Let the agent tune it** and verify the 15-step trace appears.
- Submit the northwest/top-five example and verify five NW results.
- If configured, test microphone input, spoken reply, and morning briefing audio.
- Check the terminal for exceptions throughout.
