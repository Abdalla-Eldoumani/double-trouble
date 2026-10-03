# Calgary collision-hotspot shortlist

Ranks Calgary crash locations for City of Calgary Roads by reported harm, not raw count, and tests its own weights against what happened later in the year.

Built for the IEEE YP Industry Hackathon 2026, Energy and Infrastructure Systems, Case 5.

## Run

```bash
pip install -r requirements.txt
python -m engine.agent --out out/result.json
streamlit run app/main.py
```

Data: see `data/README.md`.
