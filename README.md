# Calgary traffic-safety shortlist

Ranks Calgary traffic-incident locations by a harm score instead of a raw count, for The City of Calgary's Mobility business unit (Traffic Safety team) to review. It then tests its own weights against what happened later in the year and keeps a change only when the test supports it. Not affiliated with or endorsed by The City of Calgary.

Built for the IEEE YP Industry Hackathon 2026, Energy and Infrastructure Systems, Case 5: "Which Calgary intersections keep hurting people?" It ranks locations. It does not reduce crashes or forecast them.

## How it works

1. **Clean.** Load the 2025 Open Calgary Traffic Incidents file and set aside rows whose first sentence is not a collision (stalled vehicles, signal faults, closures, police operations and similar).
2. **Group.** Turn each free-text location into one key: direction words removed, abbreviations and feed typos fixed, street order sorted. Keys with the same streets but a different quadrant tag are merged when their centres are within 300 m, because the feed tags crossings of Macleod Trail or Memorial Drive either way.
3. **Score.** Every incident is 1 point, plus 3 when the text names a pedestrian or cyclist, plus 1 for multi-vehicle, plus 1 when more than one lane is blocked. The feed has no injury field, so this is a keyword score, stated in `engine/score.py` so it can be argued with.
4. **Agent loop.** Plan 15 weight settings (severity 0 to 1, trend 0 to 1), simplest first. Rank on January to August, then count the September to December severity points each top 20 would have caught. Keep a setting only when it catches strictly more; ties stay with the simpler weights. Locations tied at the cut share credit, so alphabetical order never decides a test.
5. **Report.** Re-rank the full year with the chosen weights, compare with a plain count, and explain the three biggest rank changes from each location's own numbers. The shortlist on screen downloads as a CSV with each location's counts, reason and the settings that produced it.
6. **Plan.** A rules-based planner turns a typed or spoken request ("top 5 in the northwest, recent incidents twice") into constraints, re-runs the engine and says what changed. ElevenLabs handles speech when a key is set.

## Results on the 2025 file

From `python -m engine.agent --out out/result.json` with the default settings (Deerfoot and Stoney Trail left out):

- 6,984 rows loaded, 419 set aside, 6,565 used.
- The agent keeps severity weight 0.75, trend 0.
- September to December test: 320 of 3,199 severity points caught, against 292.8 for a plain count (+0.85 percentage points).
- Second cut, ranked on January to June and scored on July to December: 8.98% against 9.20% for a plain count, so behind by 0.22. That window overlaps the first test, so it is a check, not a held-out test.
- 17 of the top 20 are the same as a plain count. 17 Avenue and 36 Street SE, where 5 of 11 incidents involved a pedestrian or cyclist, moves from 53rd to 17th.

The honest reading: on one year of sparse data, weighting by harm changes which places make the list more than it changes how much later harm the list catches.

## Known limits

- The feed is logged from traffic camera views. The City calls it unverified, and places without cameras are under-counted. It is not a police collision record.
- The 2025 file has no rows from 28 May to 2 July, so "January to June" is really January to May.
- The provincial filter matches the names Deerfoot and Stoney, so it also drops the City-road leg of each interchange.
- No traffic volumes, so the score measures total harm, not risk per vehicle.

## Run

Needs Python 3.12 or newer (the pinned numpy does not install on 3.11).

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q
.venv/bin/python -m engine.agent --out out/result.json
.venv/bin/streamlit run app/main.py
```

Open `http://localhost:8501`. Browsers only allow the microphone on `localhost` or HTTPS. The map's basemap tiles load from the internet; the pins, lists and everything else work offline.

Voice input and the spoken briefing use ElevenLabs. Set `ELEVENLABS_API_KEY` in the environment or in `.streamlit/secrets.toml` (gitignored). Without a key, typed planner requests and everything else still work. Requests to ElevenLabs time out after 15 seconds; start the app with `DT_NO_VOICE=1` to switch voice off without removing the key.

## Data

The City of Calgary, Open Calgary, Traffic Incidents: https://data.calgary.ca/Transportation-Transit/Traffic-Incidents/35ra-9556. Contains information licensed under the Open Government Licence - City of Calgary (https://data.calgary.ca/stories/s/Open-Calgary-Terms-of-Use/u45n-7awa/). Sources for every claim about the world are in `docs/FACTS.md`; the design is in `docs/ARCHITECTURE.md`.
