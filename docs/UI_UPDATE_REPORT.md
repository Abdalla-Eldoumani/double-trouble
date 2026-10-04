# Focused UI correction and actual verification

Updated 2026-10-04 in `/Users/ibrahimahmed/double-trouble`, based on checkout `b2f83c4` plus the existing uncommitted UI changes. Python 3.13.2; Streamlit 1.65.0. The code and previous report were inspected before editing. Existing changes were retained. No commit, push, merge, deployment, or ElevenLabs configuration was performed.

## Summary investigation: confirmed findings and limits

The previous report verified a separate server on 8502 and left the then-existing server on 8501 untouched. This correction inspected the currently running processes and the actual pages instead of inferring visibility from AppTest.

| Server | Process and checkout | Actual observation |
| --- | --- | --- |
| `http://localhost:8501` | Existing PID 25090, `python -m streamlit run app/main.py`, working directory `/Users/ibrahimahmed/double-trouble` | TCP connections accepted, but the health endpoint returned zero bytes and timed out after 8 seconds. Chrome navigation also timed out (both load and DOM-content waits). No usable page was delivered; its summary visibility could not be inspected. |
| `http://localhost:8502` | Existing PID 33245, this checkout's `.venv/bin/streamlit run app/main.py`, same working directory | The pre-change page rendered one readable summary above export and the map. Subsequently, it picked up the modified main script but retained old imported UI code and CSS. This mismatch was reproduced in Chrome, and the freshness fix produced the updated summary and photo. Before its remaining control comparison could finish, the server stopped accepting connections (`ERR_CONNECTION_REFUSED`). |
| `http://127.0.0.1:8504` | Verification PID 34663, started for this correction using `.venv/bin/python -m streamlit run /Users/ibrahimahmed/double-trouble/app/main.py --server.port 8504 --server.address 127.0.0.1 --server.headless true` | Fresh process from the same checkout rendered the corrected presentation and was exercised in Chrome. Left running for review. |

The pre-change summary on 8502 contained the current area, actual count, applied priorities, road scope, and all three leading location names/reasons. Its initial top was about 1309 pixels below the page top at 1440 × 1050, below the initial viewport. After scrolling, it was visibly readable. It measured about 298 pixels high, with `display: block`, `position: static`, `visibility: visible`, opacity 1, visible overflow, white background, and dark text. Its ancestors did not hide it. Screenshots show its location immediately above export/map/shortlist and no covering element after scrolling. See [pre-change observations](ui-checks/correction/before.json) and [pre-change summary screenshot](ui-checks/correction/before-8502-summary.png).

**Confirmed version mismatch:** after the edits, 8502 rendered the new keyed summary container from `main.py`, yet the equipment photo still measured 120 pixels with opacity 0.78 and absolute positioning. The fresh 8504 page showed 218 pixels, opacity 1, and static positioning. Thus changing the main script did not ensure that the long-lived process refreshed the imported presentation module. A timestamp check now reloads only `app.ui` when its source changes. CSS is read from the local stylesheet on every theme/render rerun instead of being captured at import time. The existing 8502 process then rendered the current photograph at 218 pixels, full opacity, and static positioning without restarting it.

**Not established:** the precise cause of the user's earlier missing-summary experience. The responsive server's original summary was visible during this inspection. The unresponsive 8501 server and the reproduced stale-module behavior establish real differences between running and verification servers, but neither proves that a particular CSS rule hid that earlier summary. Below-the-fold placement is also a confirmed observation, not a proven cause of disappearance.

## Focused implementation

- Exactly one **Recommendation summary** uses a dedicated keyed Streamlit container with `st.html`, avoiding Markdown transformations of its heading/list. It remains in normal document flow immediately above export, map, and shortlist, with automatic height, visible overflow, full opacity, an opaque themed panel, and strong text contrast. It is not an expander.
- Contents continue to come from the current applied result: area, actual recommendation count, road exclusions/inclusions, applied priorities, and up to three leading locations with factual counts. Planner requests, controls, automatic tuning, and reset feed the same result. Empty results explicitly say no locations qualify; export remains disabled and the map absent in that case.
- The previous All Calgary fix remains intact: the widget stores the explicit string `ALL`, translated to engine `region=None` only at the boundary. Theme changes retain the applied plan, typed request, reply, and exact result.
- The title, description, palette, panel layout, controls, planner, scoring, ranking engine, capacity, road filters, map, export, and speech gate are preserved. No engine, export, planning, dependency, or speech files were changed for this correction.
- Presentation refresh is narrowly scoped to the UI module. It does not clear session settings, planner replies, tuning state, or engine caches. A new regression simulates a stale summary/hero implementation and verifies restoration of the current UI while retaining an active Northwest plan and dark mode.

## Real photographs

Both existing local JPEGs were visually inspected and reused without changing their bytes, sourcing new photographs, or generating imagery. Attribution remains in the app and is updated in [app/assets/ATTRIBUTION.md](../app/assets/ATTRIBUTION.md).

| Asset | Treatment in this correction |
| --- | --- |
| `safety-vest-hardhat-life-of-pix.jpg` — Life Of Pix / Pexels, Pexels License | Increased from 120 × 120 to 218 × 218 in its own header grid column, beside the title and description and below the theme toggle. Full opacity and no fading mask make the vest and hardhat noticeable. Proportional cover crop, subtle border, and dark-theme brightness 0.88 retain a restrained appearance. Reduced to 160 × 160 at tablet widths; hidden at 640 pixels and below. |
| `road-intersection-frak-lopez.jpg` — Frak Lopez / Unsplash, Unsplash License | Removed from the title's full-width image layer and reused as a single page-edge background accent. Proportional cover cropping, opacity 0.12 light / 0.10 dark, theme-aware colored overlays, and intersecting horizontal/vertical fading masks soften every boundary. Most visible in the left margin and open gaps; panels and map remain opaque. Absolute positioning inside the scrolling document, no fixed positioning, repetition, stretching, or animation, and no pointer interception. Reduced below 1000 pixels and disabled at 640 pixels and below. |

The pre-change screenshot also showed Streamlit's optional developer notice covering the old equipment-photo corner. This notice was dismissed in the isolated verification browser context for visual assessment; no global user preference or unrelated browser session was modified.

## Tests and browser evidence

The in-app browser plugin was attempted first and failed before initialization with a missing `sandboxPolicy` field. Verification therefore used a separate headless instance of installed Google Chrome via the previously installed Playwright utility in `/tmp/double-trouble-browser-tools`. These are actual browser interactions and screenshot inspections, not claims based only on AppTest. No unrelated process was terminated or reconfigured.

| Check | Actual result |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_app_ui.py -q` after panel/image changes | 34 passed in 34.68 seconds. |
| `.venv/bin/python -m pytest tests -q` after panel/image changes | 115 passed in 70.61 seconds. |
| `.venv/bin/python -m pytest tests -q` after the module-freshness fix | 115 passed in 90.26 seconds. |
| `.venv/bin/python -m pytest tests/test_app_ui.py::test_stale_presentation_refresh_preserves_applied_plan -q` (new regression added after suite collection) | 1 passed in 3.65 seconds. Together with the final suite, 116 distinct tests passed. |
| `.venv/bin/python -m compileall -q app engine` | Passed. |
| `git diff --check` | Passed. |

Browser checks on 8504 covered desktop 1440 × 1050 and narrow 390 × 844 viewports:

- Exactly one summary heading and actual contents, before export/map/shortlist. The panel measured about 291 pixels on desktop and 640 pixels on the phone viewport. Hit-testing confirmed that the heading, overview paragraph, and first factual reason were uncovered; ancestor visibility/opacity were checked, and screenshots of all three reasons were opened and inspected.
- Light summary text `rgb(32,40,48)` on white; dark text `rgb(240,244,248)` on `rgb(32,42,52)`. Heading and body share full-contrast text, with no translucent panel or photo over them.
- Summary changes after area selection, capacity changes, priority selection, advanced weights, tuning, Northwest typed requests, whole-city typed requests, and reset. All Calgary remains selected through the relevant reruns.
- Both theme directions retain summary, applied area and capacity, and planner reply. Theme changes produce byte-identical downloaded CSVs (6703 bytes for the checked ten-location request).
- Loaded 218-pixel equipment photograph, opacity 1, separate horizontal bounds from title/description, and bounds below the theme toggle. Both photographs are hidden on the phone viewport, with no horizontal page overflow.
- Native dropdowns, advanced sliders/helper tooltip, functioning map markers and hover tooltip, zoom-in/out controls, current shortlist, and actual CSV downloads. Light/dark CARTO basemaps were visibly rendered. No photograph overlays the map.
- Road layer is a local JPEG, absolute in the document, non-repeating, smoothly masked, with `pointer-events: none`. Visual inspection confirms faint edge detail in light mode and no bright dark-mode patches; content panels remain readable.

[Browser audit](ui-checks/check_ui.py) and [machine-readable results](ui-checks/correction/results.json). Browser-audit development exposed selector/timing problems and the real 8502 stale-module mismatch. Passing AppTests were not substituted for browser inspection.

The fresh-server workflow checks completed. The existing 8502 server's updated light header and summary were separately captured and inspected after the module-freshness fix. Its remaining dropdown/planner/theme comparison did not complete before the server became unavailable; no completed dark-theme or full control-workflow verification is claimed for that existing process. The final audit records this external-server limitation separately from the passing 8504 checks.

Screenshots from this correction (the earlier screenshots outside `correction/` are historical):

- [Light desktop](ui-checks/correction/light-desktop.png), [dark desktop](ui-checks/correction/dark-desktop.png).
- [Light summary above map](ui-checks/correction/light-summary-map.png), [dark summary above map](ui-checks/correction/dark-summary-map.png).
- [Light phone summary](ui-checks/correction/light-mobile-summary.png), [dark phone summary](ui-checks/correction/dark-mobile-summary.png).
- [Light phone header](ui-checks/correction/light-mobile.png), [dark phone header](ui-checks/correction/dark-mobile.png).
- [Updated running 8502 header](ui-checks/correction/running-8502-light-header.png), [updated running 8502 summary](ui-checks/correction/running-8502-light-summary.png).

## Limitations and server handling

Port 8501 did not serve a usable page during this session and was left untouched. Its earlier summary state cannot be confirmed. By the final port inspection, neither 8501 nor 8502 had a listener; this agent did not stop either process. The verified app remains available on 8504. Browser verification uses desktop Chrome with resized viewports, not physical phones, Safari/Firefox, or a screen-reader audit. The empty state is verified using existing synthetic-data AppTests; the supplied full dataset did not produce an empty quadrant during browser checks. Theme persistence is within a Streamlit session; new sessions start light. Basemap tiles still require network access. ElevenLabs remains deferred and gated, including when credentials exist.
