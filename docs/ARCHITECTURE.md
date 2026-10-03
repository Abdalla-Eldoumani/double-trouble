# Architecture

```mermaid
flowchart TD
    CSV["Open Calgary Traffic Incidents CSV<br/>data/calgary_traffic_incidents_2025.csv"]
    CLEAN["Clean<br/>drop non-crash rows, normalize text<br/>engine/data.py"]
    KEY["Location key<br/>intersection name, direction words stripped<br/>engine/data.py"]
    SIG["Signals per location<br/>count, severity points, trend, provincial flag<br/>engine/score.py"]

    subgraph LOOP["Agent loop, engine/agent.py"]
        PLAN["Plan<br/>15 weight candidates"]
        SCORE["Backtest score<br/>rank on Jan-Aug,<br/>share of Sep-Dec severity caught"]
        REVISE["Revise<br/>keep strictly better, ties go to simpler weights,<br/>log every candidate kept or rejected"]
        PLAN --> SCORE --> REVISE
        REVISE -->|next candidate| SCORE
    end

    RANK["Ranking<br/>full-year top 20, count-only baseline,<br/>overlap, movers with reasons, second-split check"]
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

There is no model training: the score is a weighted mix of counts the City already publishes, so every rank can be traced back to the incidents behind it.

The agent tests its own weights by ranking on the earlier months and checking how much of the later harm its top 20 caught, and it keeps count-only when nothing beats it.

A full run, including the 15-candidate search, finishes in under 2 seconds on a laptop, so the app can re-run the engine live while someone moves a slider.

The engine reads the same columns as the Open Calgary Traffic Incidents feed, so a newer export loads with no change to cleaning or scoring; only the date windows at the top of engine/agent.py move to the new year.

The voice planner parses requests with fixed rules rather than a language model, so the same words always give the same constraints, it works offline, and a request it cannot read changes nothing instead of guessing.
