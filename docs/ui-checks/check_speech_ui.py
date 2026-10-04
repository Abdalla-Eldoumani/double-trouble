"""Inspect optional speech UI without recording or clicking any paid API action.

Requires the optional Playwright utility and installed Chrome.
Usage: python docs/ui-checks/check_speech_ui.py http://localhost:8502 running
"""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import json
import sys

root = Path(__file__).resolve().parents[2]
url = sys.argv[1] if len(sys.argv)>1 else 'http://localhost:8501'
out = root / 'docs/ui-checks/speech' / (sys.argv[2] if len(sys.argv)>2 else 'running')
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width':1440, 'height':1050})
    page.goto(url, wait_until='domcontentloaded', timeout=15000)
    page.get_by_role('heading', name='Recommendation summary', exact=True).wait_for()
    page.locator('.stApp[data-test-script-state="notRunning"]').wait_for()
    page.get_by_text('Speak your request', exact=True).click()
    page.get_by_label('Review transcription', exact=True).wait_for()
    page.get_by_text('Speak your request', exact=True).scroll_into_view_if_needed()
    page.screenshot(path=str(out/'light-planner.png'))
    transcribe_enabled=page.get_by_role('button',name='Transcribe recording',exact=True).is_enabled()
    read_enabled=page.get_by_role('button',name='Read summary aloud',exact=True).is_enabled()
    page.get_by_label('Review transcription',exact=True).fill('Now show all Calgary.')
    page.get_by_role('button',name='Apply request',exact=True).click()
    expect(page.locator('.reply-text')).to_contain_text('All Calgary')
    page.get_by_text('Dark mode',exact=True).click()
    expect(page.get_by_label('Review transcription',exact=True)).to_have_value('Now show all Calgary.')
    page.get_by_label('Review transcription',exact=True).scroll_into_view_if_needed()
    expect(page.get_by_label('Review transcription',exact=True)).to_have_css('background-color','rgb(32, 42, 52)')
    page.screenshot(path=str(out/'dark-planner.png'))
    page.get_by_role('heading',name='Recommendation summary',exact=True).scroll_into_view_if_needed()
    page.screenshot(path=str(out/'dark-summary.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_text('Speak your request',exact=True).scroll_into_view_if_needed()
    page.get_by_label('Review transcription',exact=True).scroll_into_view_if_needed()
    page.screenshot(path=str(out/'phone-planner.png'))
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    assert page.locator('.recommendation-summary').count()==1
    assert page.get_by_test_id('stAudio').count()==0
    results={'server':url,'transcribe_enabled':transcribe_enabled,'read_summary_enabled':read_enabled,
        'review_apply_and_theme_preservation':True,'dark_transcript_readable':True,
        'phone_no_horizontal_overflow':True,'summary_count':1,'summary_audio_players':0,
        'microphone_capture_tested':False,'live_api_calls':0}
    (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))
    browser.close()
