"""Capture the existing user servers before the focused UI correction."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "correction"
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    results = {}
    for port in (8501, 8502):
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        print(f"Inspecting {port}", flush=True)
        try:
            page.goto(f"http://localhost:{port}", wait_until="domcontentloaded", timeout=15000)
        except Exception as exc:
            results[str(port)] = {"navigation_error": str(exc)}
            page.close()
            continue
        page.get_by_role("button", name="Export investigation shortlist", exact=True).wait_for(timeout=30000)
        page.locator('.stApp[data-test-script-state="notRunning"]').wait_for()
        page.screenshot(path=str(OUT / f"before-{port}-header.png"))
        panel = page.locator(".recommendation-summary")
        info = {"url": page.url, "summary_count": panel.count()}
        if panel.count():
            info["summary"] = panel.evaluate("""e => {
              const props = n => { const s=getComputedStyle(n), r=n.getBoundingClientRect();
                return {tag:n.tagName, class:n.className, display:s.display, visibility:s.visibility,
                  opacity:s.opacity, height:r.height, width:r.width, y:r.y, overflow:s.overflow,
                  position:s.position, color:s.color, background:s.backgroundColor}; };
              const ancestors=[]; let a=e; while(a) {ancestors.push(props(a));a=a.parentElement;}
              return {text:e.innerText, html:e.outerHTML, ancestors};
            }""")
            panel.scroll_into_view_if_needed()
        else:
            page.get_by_role("button", name="Export investigation shortlist", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / f"before-{port}-summary.png"))
        info["headings"] = page.get_by_role("heading").all_text_contents()
        info["equipment"] = page.locator(".hero-equipment").evaluate("e=>({loaded:e.complete&&e.naturalWidth>0,box:e.getBoundingClientRect().toJSON(),opacity:getComputedStyle(e).opacity})")
        results[str(port)] = info
    (OUT / "before.json").write_text(json.dumps(results, indent=2)+"\n")
    print(json.dumps(results, indent=2))
    browser.close()
