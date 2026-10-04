# Architecture

```mermaid
flowchart TD
    CSV["Open Calgary Traffic Incidents CSV<br/>data/calgary_traffic_incidents_2025.csv"]
    CLEAN["Clean<br/>set aside stalls, signal faults, closures; normalize text<br/>engine/data.py"]
    KEY["Location key<br/>intersection or interchange name, direction words and typos fixed,<br/>quadrant variants within 300 m merged<br/>engine/data.py"]
    SIG["Signals per location<br/>count, severity points, trend, provincial flag<br/>engine/score.py"]

    subgraph LOOP["Agent loop, engine/agent.py"]
        PLAN["Plan<br/>15 weight candidates"]
        SCORE["Backtest score<br/>rank on Jan-Aug,<br/>Sep-Dec severity points caught,<br/>ties at the cut share credit"]
        REVISE["Revise<br/>keep strictly better, ties go to simpler weights,<br/>log every candidate kept or rejected"]
        PLAN --> SCORE --> REVISE
        REVISE -->|next candidate| SCORE
    end

    RANK["Ranking<br/>full-year top 20, count-only baseline,<br/>overlap, movers with reasons, second-cut check"]
    JSON["result dict / out/result.json<br/>shape fixed by contract/sample_output.json"]
    MAP["Streamlit map and shortlist<br/>app/"]
    VOICE["Voice briefing<br/>app/"]

    subgraph PLANNER["Voice planner"]
        SPEAK["Planner speaks or types a request<br/>ElevenLabs speech to text, app/briefing.py"]
        PARSE["Parse to constraints<br/>recent weight, quadrant, budget, weights<br/>engine/planner.py"]
        COMPARE["Compare old and new shortlist<br/>engine/planner.py"]
        EXPLAIN["Explain from the computed numbers<br/>ElevenLabs text to speech"]
    end

    CSV --> CLEAN --> KEY --> SIG --> LOOP --> RANK --> JSON
    JSON --> MAP
    JSON --> VOICE
    SPEAK --> PARSE -->|constraints| SIG
    JSON --> COMPARE --> EXPLAIN
    COMPARE --> MAP
```

## Why this design

The whole pipeline is pandas over one table of a few thousand rows, so there is no database, no service and nothing to deploy beyond the app.

There is no model training: the score is a weighted mix of incident counts and keyword tags taken from the City's own incident text, so every rank can be traced back to the rows behind it.

The agent tests its own weights by ranking on the earlier months and counting how many later severity points its top 20 caught, and it keeps count-only when nothing beats it. The second cut overlaps the first test window, so it is reported as a check, not a held-out test.

The data is loaded and scored once per file version, so after the first call a full run, including the 15-candidate search, takes well under a second and the app can re-run the engine live while someone moves a slider.

A newer export of the Open Calgary Traffic Incidents feed with the same columns should load unchanged, as long as the City keeps its description wording; only the date windows at the top of engine/agent.py move to the new year.

The planner parses requests with fixed rules rather than a language model, so the same words always give the same constraints, it works offline, and a request it cannot read changes nothing instead of guessing.
