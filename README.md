# Calgary collision-hotspot shortlist

Shortlists Calgary locations for traffic-safety investigation using reported 2025 crashes. Choose an area, capacity, and priorities, or use the deterministic typed planner. Historical validation and technical weights are available in collapsed sections.

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

Open `http://localhost:8501`. The opening preset and Reset settings use crash totals, all Calgary, up to 20 locations, and name-based Deerfoot/Stoney exclusion.

Speech configuration and live testing are deferred. Existing ElevenLabs functions remain available for the later phase, but `SPEECH_ENABLED = False` in `app/main.py` hides speech controls and prevents speech calls even when credentials exist. Typed planning requires no key.

Presets map to `(incident-indicator weight, increasing-activity weight, recency multiplier)`: Crash totals `(0, 0, 1)`, Balanced priorities `(0.5, 0.5, 1)`, Pedestrians and cyclists `(1, 0, 1)`, Recent activity `(0, 0, 2)`. The pedestrian/cyclist preset also weights multi-vehicle and blocked-lane descriptions. The automatic search evaluates 20 locations under the selected area, road scope, and recency; capacity affects the displayed shortlist and its validation, not the search objective. The secondary validation uses overlapping months and is not an independent holdout.

Data: see `data/README.md`.
