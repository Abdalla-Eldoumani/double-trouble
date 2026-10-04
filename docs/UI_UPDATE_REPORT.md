# Focused UI correction and actual verification

Updated 2026-10-04 against checkout `f87b638` in `/Users/ibrahimahmed/double-trouble`. The code and existing report were inspected before editing. Python 3.13.2; Streamlit 1.65.0. This report supersedes the earlier report's server-status statements; older screenshots in `ui-checks/correction/` are historical.

## Summary investigation: confirmed findings and uncertainty

The restarted, user-facing process is PID **2129**, running this checkout's `.venv/bin/streamlit run app/main.py`, with working directory `/Users/ibrahimahmed/double-trouble`, listening on **8501**. Its health endpoint returned HTTP 200 and `ok`. It was not stopped or reconfigured.

A separate Chrome session inspected `http://localhost:8501` **before changes**. It rendered exactly one Recommendation summary, with the current area/count, road exclusions, applied priorities, and three leading locations with factual counts. At 1440 × 1050, the panel began at approximately **1309 pixels** below the document top, outside the initial viewport. After scrolling, its heading and contents were visibly readable directly above export and the map.

The panel was 291 pixels high, with `display: block`, `position: static`, automatic height, visible overflow, visibility `visible`, opacity 1, dark text on white, and no hiding ancestor. Screenshot inspection showed no covering element. Evidence: [before-change measurements](ui-checks/current/before.json), [opening page](ui-checks/current/before-8501-header.png), and [summary after scrolling](ui-checks/current/before-8501-summary.png).

**Confirmed:** the current summary was below the opening viewport, making it easy to miss. **Not established:** the cause of the user's earlier missing-summary experience. No hidden-summary CSS fault or wrong-checkout condition was reproduced in the restarted 8501 process. The previous report's unresponsive servers and stale-module observations are historical findings, not proven explanations for this current experience.

## Focused changes and preserved behavior

- Added a small **View current recommendations ↓** link immediately after the three figures. It targets the existing summary heading, brings it near the top of the viewport, and does not duplicate the summary or its contents. The target has a modest scroll margin and the link has a keyboard-focus outline.
- Kept exactly one **Recommendation summary** in its normal-flow, opaque themed panel above export, map, and shortlist. The existing result-derived contents and explicit empty state remain intact. No expander, fixed positioning, forced scrolling on reruns, or competing summary was added.
- Enlarged the desktop equipment photograph from **218 × 218 to 240 × 240**. Its separate header grid column keeps it clear of the title, description, and theme toggle. The existing crop prominently shows the vest and helmet, at full opacity; its subtle border and dark-theme brightness adjustment remain. Tablet size stays 160 × 160 and it is hidden at 640 pixels and below.
- Preserved the title, description, layout, colors, controls, typed planner, dark-mode state, map, CSV export, ranking engine, scoring, exclusions, tuning, and reset behavior. ElevenLabs remains deferred and gated. No planning, engine, export, speech, or application dependency files changed.
- Updated browser utilities to inspect an explicitly selected server and store new evidence separately. Removed a hardcoded comparison with the obsolete 8502 server so future checks cannot silently attribute old observations to the current app.

## Real photographs and background

Both existing local JPEGs were opened and visually inspected. Their bytes are unchanged. No replacement imagery was sourced, generated, or hotlinked.

| Asset | Current treatment |
| --- | --- |
| `safety-vest-hardhat-life-of-pix.jpg` — Life Of Pix / Pexels, Pexels License | Existing proportional crop reused at 240 pixels on desktop, 160 on tablets, hidden on phones. Full opacity, separate grid column, subtle border, brightness 0.88 in dark mode. |
| `road-intersection-frak-lopez.jpg` — Frak Lopez / Unsplash, Unsplash License | The existing intersection photograph is suitable and its existing page-edge background treatment is retained: one local image with cover cropping, opacity 0.12 light / 0.10 dark, theme-colored overlays, and intersecting horizontal/vertical masks. Absolute positioning inside the scrolling document, no repetition, stretching, animation, fixed-position effect, or pointer interception. Reduced on tablets and disabled at 640 pixels and below. |

Desktop screenshots show faint road markings in open edge space. Opaque figures and planning panels cover the image; the summary and map remain clear of it. Dark mode has no bright background patches. [Attribution](../app/assets/ATTRIBUTION.md) records each creator, source, license, and adjustments, including the new equipment display size. Existing in-app attribution remains.

## Actual browser verification

The in-app browser skill was attempted first; initialization failed with a missing `sandboxPolicy` field. A temporary Playwright utility in `/tmp/double-trouble-browser-tools` then drove an isolated headless instance of installed Google Chrome. These results include actual browser interactions and opened screenshot inspections, not only AppTests. No existing user browser session was changed.

| Server inspected | Checkout / process | Result |
| --- | --- | --- |
| `http://localhost:8501` | Existing user-facing PID 2129; this checkout | Full browser audit passed after changes. The long-lived server picked up the current summary anchor and 240-pixel photograph. |
| `http://localhost:8504` | Fresh verification PID 3653, started with `.venv/bin/python -m streamlit run /Users/ibrahimahmed/double-trouble/app/main.py --server.port 8504 --server.address 127.0.0.1 --server.headless true`; same checkout | Same full browser audit passed. No visible summary, photo-size, theme, or workflow difference found. |

Both servers were checked at **1440 × 1050** and **390 × 844**:

- One summary heading and its actual contents, before export/map/shortlist. The new link scrolls the heading into the first 150 pixels of the viewport. Hit-testing confirms the heading, overview, and first factual reason are uncovered. All three reasons were visibly inspected in light/dark desktop and phone screenshots.
- Panel height approximately 291 pixels on desktop and 640 on the phone viewport; static positioning, visible overflow, full opacity, and no hiding ancestor. Light text: `rgb(32,40,48)` on white. Dark text: `rgb(240,244,248)` on `rgb(32,42,52)`.
- Summary updates after area selection, capacity changes, priority selection, advanced weights, tuning, Northwest typed requests, whole-city typed requests, and reset. All Calgary remains selected through the checked reruns.
- Both theme directions retain applied recommendations, planner reply, area, and capacity. Actual downloaded CSVs match byte-for-byte across themes for the checked ten-location request: 6703 bytes.
- Equipment photograph loaded at 240 × 240, opacity 1, with horizontal bounds separate from the title/description and vertical bounds below the theme toggle. The road treatment remains faint in both themes. Both photographs are hidden on the phone viewport; no horizontal page overflow.
- Dropdowns, advanced sliders/help tooltip, rendered basemap, marker hover tooltip, zoom-in/out controls, shortlist, and actual CSV downloads work. No browser page errors were captured.

Evidence: [running-server results](ui-checks/current/running/results.json), [fresh-server results](ui-checks/current/fresh/results.json), and [browser audit](ui-checks/check_ui.py).

Current running-server screenshots:

- [Light desktop](ui-checks/current/running/light-desktop.png), [dark desktop](ui-checks/current/running/dark-desktop.png), [summary-link destination](ui-checks/current/running/summary-jump.png).
- [Light summary above map](ui-checks/current/running/light-summary-map.png), [dark summary above map](ui-checks/current/running/dark-summary-map.png).
- [Light phone summary](ui-checks/current/running/light-mobile-summary.png), [dark phone summary](ui-checks/current/running/dark-mobile-summary.png).
- [Light map tooltip](ui-checks/current/running/light-map-tooltip.png), [dark map tooltip](ui-checks/current/running/dark-map-tooltip.png).

Corresponding fresh-server screenshots are in `ui-checks/current/fresh/`.

## Tests and limits

- `.venv/bin/python -m pytest tests -q`: **116 passed in 102.97 seconds**. Existing tests cover current-result summary content and order, empty/sparse results, controls, typed requests, tuning/reset, All Calgary persistence, theme persistence, export, and deferred speech.
- `.venv/bin/python -m compileall -q app engine`: passed.
- `git diff --check`: passed.

The supplied dataset did not produce an empty area during browser checks; the empty state is verified by existing synthetic-data AppTests, not claimed as a browser observation. Browser checks use desktop Chrome with resized viewports, not physical phones or other browser engines. Theme persistence is within a Streamlit session. Map tiles still require network access.

No unrelated process was terminated. The existing 8501 app and this session's fresh 8504 verification server remain running. No commit, push, merge, deployment, or ElevenLabs configuration was performed.
