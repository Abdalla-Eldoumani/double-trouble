# Calgary collision-hotspot shortlist

Ranks Calgary crash locations for City of Calgary Roads by reported harm, not raw count, and tests its own weights against what happened later in the year.

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

Open `http://localhost:8501`. Browsers only allow the microphone on `localhost` or HTTPS.

Voice input and the spoken briefing use ElevenLabs. Set `ELEVENLABS_API_KEY` in the environment or in `.streamlit/secrets.toml` (gitignored). Without a key, typed planner requests and everything else still work.

Data: see `data/README.md`.
