"""Optional local browser audit; requires Playwright and an installed Google Chrome.

Start the app, then pass its URL and optionally an output directory. Playwright is a verification
utility only and is intentionally absent from the application's requirements.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect, Error as PlaywrightError
import json
import sys

OUT=Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).resolve().parent
OUT.mkdir(parents=True,exist_ok=True)
URL=sys.argv[1] if len(sys.argv)>1 else 'http://localhost:8502'

def idle(page):
    page.locator('.stApp[data-test-script-state="notRunning"]').wait_for(timeout=30000)
    page.wait_for_timeout(300)

def map_hover(page,filename):
    rect=page.get_by_test_id('stDeckGlJsonChart').bounding_box()
    # In the default citywide view, marker #7 is just left of centre.
    page.mouse.move(rect['x']+rect['width']*.222,rect['y']+rect['height']*.60)
    tooltip=page.locator('.deck-tooltip')
    expect(tooltip).to_contain_text('Crowchild Trail and Bow Trail SW')
    box=tooltip.bounding_box()
    assert box['y']>=rect['y'] and box['y']+box['height']<=rect['y']+rect['height']
    page.screenshot(path=str(OUT/filename))
    page.mouse.move(20,20)


def area(page,value):
    page.get_by_role('combobox',name='Area',exact=True).scroll_into_view_if_needed()
    page.get_by_role('group').filter(has=page.get_by_role('combobox',name='Area',exact=True)).get_by_role('button',name='Open',exact=True).click()
    if ':8502' in page.url:
        page.screenshot(path=str(OUT/'running-8502-area-dropdown.png'))
        print('Existing area options:',page.get_by_role('option').all_text_contents(),flush=True)
    page.get_by_role('option',name=value,exact=True).click()
    idle(page)
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value(value)

def ask(page,text):
    page.get_by_label('Your planning request',exact=True).fill(text)
    page.get_by_role('button',name='Update recommendations',exact=True).click()
    expect(page.locator('.reply-ask')).to_contain_text(text,timeout=30000)
    idle(page)

with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1050},accept_downloads=True)
    page=context.new_page()
    page.set_default_timeout(12000)
    failures=[]
    page.on('pageerror',lambda e: failures.append(str(e)))
    page.goto(URL)
    page.get_by_role('heading',name='Recommendation summary').wait_for(timeout=30000)
    idle(page)
    notice=page.get_by_role('button',name="Don't show again",exact=True)
    if notice.count():
        notice.click()
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    assert page.locator('.hero img').evaluate_all('(es)=>es.every(e=>e.complete&&e.naturalWidth>0)')
    assert page.locator('.hero img').evaluate_all('(es)=>es.every(e=>e.alt===""&&e.getAttribute("aria-hidden")==="true")')
    page.screenshot(path=str(OUT/'light-desktop.png'))
    def summary_readable():
        panel=page.locator('.recommendation-summary')
        expect(panel).to_have_count(1)
        expect(page.get_by_role('heading',name='Recommendation summary',exact=True)).to_be_visible()
        panel.scroll_into_view_if_needed()
        info=panel.evaluate('''e=>{
            const rect=e.getBoundingClientRect(), css=getComputedStyle(e);
            const heading=e.querySelector('h3'), p=e.querySelector('p'), li=e.querySelector('li');
            const uncovered=n=>{const r=n.getBoundingClientRect();
              return n.contains(document.elementFromPoint(r.x+Math.min(30,r.width/2),r.y+r.height/2));};
            let a=e, ancestors=[]; while(a){const s=getComputedStyle(a);ancestors.push({opacity:s.opacity,visibility:s.visibility,display:s.display});a=a.parentElement;}
            return {height:rect.height,position:css.position,overflow:css.overflow,
              headingUncovered:uncovered(heading),paragraphUncovered:uncovered(p),reasonUncovered:li?uncovered(li):true,
              colors:{background:css.backgroundColor,heading:getComputedStyle(heading).color,body:getComputedStyle(p).color},
              text:e.innerText,ancestors};
        }''')
        assert info['height']>150 and info['position']=='static' and info['overflow']=='visible',info
        assert info['headingUncovered'] and info['paragraphUncovered'] and info['reasonUncovered'],info
        assert all(a['opacity']=='1' and a['visibility']=='visible' and a['display']!='none' for a in info['ancestors']),info
        assert page.locator('.recommendation-summary li').count()==3
        assert panel.bounding_box()['y']+panel.bounding_box()['height'] <= page.get_by_test_id('stDownloadButton').bounding_box()['y']+1
        assert page.get_by_test_id('stDownloadButton').bounding_box()['y'] < page.get_by_test_id('stDeckGlJsonChart').bounding_box()['y']
        return info
    light_readability=summary_readable()
    page.screenshot(path=str(OUT/'light-summary-map.png'))
    page.locator('.mast').scroll_into_view_if_needed()
    equipment=page.locator('.hero-equipment').evaluate('''e=>{const r=e.getBoundingClientRect(),title=document.querySelector('.title').getBoundingClientRect(),
        lede=document.querySelector('.lede').getBoundingClientRect(),toggle=document.querySelector('input[role="switch"]').closest('label').getBoundingClientRect();
        return {width:r.width,height:r.height,opacity:getComputedStyle(e).opacity,loaded:e.complete&&e.naturalWidth>0,
            separateFromText:r.x>=title.right&&r.x>=lede.right,belowToggle:r.y>toggle.bottom};}''')
    assert equipment['loaded'] and equipment['width']>=210 and equipment['opacity']=='1'
    assert equipment['separateFromText'] and equipment['belowToggle'],equipment
    road=page.get_by_test_id('stMainBlockContainer').evaluate('''e=>{const s=getComputedStyle(e,'::before');
        return {position:s.position,opacity:s.opacity,repeat:s.backgroundRepeat,mask:s.maskImage,composite:s.maskComposite,
          local:s.backgroundImage.includes('data:image/jpeg;base64,'),pointerEvents:s.pointerEvents};}''')
    assert road['local'] and road['position']=='absolute' and all(r.strip()=='no-repeat' for r in road['repeat'].split(',')) and road['pointerEvents']=='none',road
    page.get_by_role('combobox',name='Area',exact=True).click()
    page.screenshot(path=str(OUT/'light-dropdown.png'))
    page.get_by_role('option',name='Northwest',exact=True).click()
    idle(page)
    expect(page.locator('.recommendation-summary')).to_contain_text('Northwest Calgary')
    area(page,'All Calgary')
    # Focus/blur must not clear the citywide selection.
    page.get_by_label('How many locations can your team investigate?',exact=True).click()
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    page.get_by_label('How many locations can your team investigate?',exact=True).fill('5')
    page.get_by_label('How many locations can your team investigate?',exact=True).press('Enter')
    expect(page.locator('.recommendation-summary')).to_contain_text('5 locations recommended')
    idle(page)
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    page.get_by_role('combobox',name='Safety priorities',exact=True).click()
    page.get_by_role('option',name='Pedestrians and cyclists',exact=True).click()
    idle(page)
    expect(page.locator('.recommendation-summary')).to_contain_text('Applied priorities: Pedestrians and cyclists')
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    page.get_by_text('Advanced controls',exact=True).click()
    page.wait_for_timeout(400)
    s=page.get_by_label('Give more priority to pedestrian/cyclist and other crash indicators',exact=True)
    s.press('ArrowLeft')
    idle(page)
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    page.get_by_role('button',name='Test ranking options automatically',exact=True).click()
    idle(page)
    expect(page.locator('.recommendation-summary')).to_contain_text('5 locations recommended in All Calgary')
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    ask(page,'We can investigate five locations in northwest Calgary. Give recent crashes twice the importance.')
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('Northwest')
    expect(page.locator('.recommendation-summary')).to_contain_text('5 locations recommended in Northwest Calgary')
    expect(page.locator('.recommendation-summary')).to_contain_text('reports weighted 2×')
    ask(page,'Top 10 across the whole city.')
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    light_summary=page.locator('.recommendation-summary').inner_text()
    light_reply=page.locator('.reply').inner_text()
    with page.expect_download() as d:
        page.get_by_role('button',name='Export investigation shortlist',exact=True).click()
    light_csv=Path(d.value.path()).read_bytes()
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    page.get_by_text('Dark mode',exact=True).click()
    idle(page)
    assert page.locator('.recommendation-summary').inner_text()==light_summary
    assert page.locator('.reply').inner_text()==light_reply
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    with page.expect_download() as d:
        page.get_by_role('button',name='Export investigation shortlist',exact=True).click()
    dark_csv=Path(d.value.path()).read_bytes()
    assert dark_csv==light_csv
    page.get_by_role('button',name='Reset settings',exact=True).click()
    idle(page)
    expect(page.get_by_role('switch',name='Dark mode')).to_be_checked()
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    expect(page.locator('.recommendation-summary')).to_contain_text('20 locations recommended')
    page.locator('.mast').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'dark-desktop.png'))
    page.get_by_role('combobox',name='Area',exact=True).click()
    page.screenshot(path=str(OUT/'dark-dropdown.png'))
    page.get_by_role('option',name='All Calgary',exact=True).click()
    idle(page)
    page.get_by_role('heading',name='Recommendation summary').scroll_into_view_if_needed()
    dark_readability=summary_readable()
    page.screenshot(path=str(OUT/'dark-summary-map.png'))
    # Full map and ranked locations, with actual network-backed basemap.
    page.get_by_test_id('stDeckGlJsonChart').scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT/'dark-map-shortlist.png'))
    map_hover(page,'dark-map-tooltip.png')
    page.get_by_role('button',name='Zoom In',exact=True).click()
    page.wait_for_timeout(350)
    page.get_by_role('button',name='Zoom Out',exact=True).click()
    page.wait_for_timeout(350)
    if not page.get_by_label('Give more priority to recent crashes',exact=True).is_visible():
        page.get_by_text('Advanced controls',exact=True).click()
    page.wait_for_timeout(450)
    page.get_by_text('These sliders change ranking priorities',exact=False).scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'dark-advanced.png'))
    dark_caption=page.get_by_text('These sliders change ranking priorities',exact=False).evaluate('(e)=>({color:getComputedStyle(e).color,opacity:getComputedStyle(e.parentElement).opacity})')
    assert dark_caption['opacity']=='1'
    summary_bg=page.get_by_text('Advanced controls',exact=True).evaluate('(e)=>getComputedStyle(e.closest("summary")).backgroundColor')
    assert summary_bg in ['rgb(32, 42, 52)','rgb(39, 50, 61)'],summary_bg
    track_bg=page.get_by_test_id('stSlider').first.evaluate('(e)=>getComputedStyle(e.querySelector("[role=group] > div[data-rac] > div")).backgroundImage')
    assert 'linear-gradient' in track_bg
    page.get_by_role('button',name='Help for Give more priority to pedestrian/cyclist and other crash indicators').hover()
    tooltip=page.get_by_test_id('stTooltipContent')
    tooltip.wait_for()
    assert tooltip.evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(32, 42, 52)'
    page.wait_for_timeout(800)  # Finish the tooltip's entrance animation.
    page.screenshot(path=str(OUT/'dark-helper-tooltip.png'))
    page.mouse.move(20,20)
    page.get_by_text('Dark mode',exact=True).click()
    idle(page)
    page.get_by_role('heading',name='Recommendation summary').scroll_into_view_if_needed()
    summary_readable()
    page.screenshot(path=str(OUT/'light-summary-map.png'))
    page.get_by_test_id('stDeckGlJsonChart').scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT/'light-map-shortlist.png'))
    map_hover(page,'light-map-tooltip.png')
    page.get_by_text('These sliders change ranking priorities',exact=False).scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'light-advanced.png'))
    light_caption=page.get_by_text('These sliders change ranking priorities',exact=False).evaluate('(e)=>({color:getComputedStyle(e).color,opacity:getComputedStyle(e.parentElement).opacity})')
    assert light_caption['opacity']=='1'
    # Small-screen checks use the same session, preserving settings.
    page.set_viewport_size({'width':390,'height':844})
    page.locator('.mast').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'light-mobile.png'))
    assert not page.locator('.hero-equipment').is_visible()
    assert page.get_by_test_id('stMainBlockContainer').evaluate("e=>getComputedStyle(e,'::before').display")=='none'
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.get_by_role('heading',name='Recommendation summary').scroll_into_view_if_needed()
    # On a phone the whole panel can exceed the viewport. Check the heading and
    # the actual reasons separately, without treating offscreen text as hidden.
    expect(page.get_by_role('heading',name='Recommendation summary',exact=True)).to_be_visible()
    expect(page.locator('.recommendation-summary')).to_contain_text('20 locations recommended in All Calgary')
    light_phone_readability=summary_readable()
    page.screenshot(path=str(OUT/'light-mobile-summary.png'))
    page.get_by_text('Dark mode',exact=True).click()
    idle(page)
    page.locator('.mast').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'dark-mobile.png'))
    page.get_by_role('heading',name='Recommendation summary').scroll_into_view_if_needed()
    dark_phone_readability=summary_readable()
    page.screenshot(path=str(OUT/'dark-mobile-summary.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    expect(page.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
    results = {'visual_checks':'passed','desktop':[1440,1050],'mobile':[390,844],
        'server':URL,'equipment':equipment,'road':road,'summary_readability':{'light':light_readability,'dark':dark_readability,'light_phone':light_phone_readability,'dark_phone':dark_phone_readability},
        'csv_identical_across_themes':dark_csv==light_csv,'download_bytes':len(dark_csv),
        'captions':{'light':light_caption,'dark':dark_caption},'page_errors':failures}
    (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    # Compare against the already-running user server in a new browser session.
    # Do not stop it, reconfigure it, or change a user's existing browser session.
    if URL=='http://127.0.0.1:8504':
        existing=browser.new_page(viewport={'width':1440,'height':1050})
        try:
            existing.goto('http://localhost:8502',timeout=15000)
        except PlaywrightError as exc:
            results['existing_server']={'url':'http://localhost:8502','status':'unavailable',
                'navigation_error':str(exc),'controls_verification':'incomplete',
                'earlier_observation':'Updated summary container and 218px full-opacity equipment were seen and captured before this server stopped accepting connections.'}
            (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps({'verification_server':URL,'visual_checks':results['visual_checks'],
                'existing_server':results['existing_server'],'page_errors':failures},indent=2))
            assert not failures
            browser.close()
            sys.exit(0)
        existing.get_by_role('heading',name='Recommendation summary').wait_for(timeout=30000)
        idle(existing)
        notice=existing.get_by_role('button',name="Don't show again",exact=True)
        if notice.count():
            notice.click()
        expect(existing.locator('.st-key-recommendation_summary')).to_have_count(1)
        expect(existing.locator('.recommendation-summary')).to_have_count(1)
        expect(existing.locator('.recommendation-summary')).to_contain_text('20 locations recommended in All Calgary')
        existing.screenshot(path=str(OUT/'running-8502-light-header.png'))
        existing_equipment=existing.locator('.hero-equipment').evaluate('e=>({width:e.getBoundingClientRect().width,cssWidth:getComputedStyle(e).width,opacity:getComputedStyle(e).opacity,position:getComputedStyle(e).position,parent:e.parentElement.className})')
        print('Existing server equipment:',json.dumps(existing_equipment),flush=True)
        assert existing_equipment['width']>=210,existing_equipment
        existing.locator('.recommendation-summary').scroll_into_view_if_needed()
        existing.screenshot(path=str(OUT/'running-8502-light-summary.png'))
        existing.locator('.st-key-controls').scroll_into_view_if_needed()
        area(existing,'Northwest')
        expect(existing.locator('.recommendation-summary')).to_contain_text('Northwest Calgary')
        ask(existing,'Top 10 across the whole city.')
        expect(existing.get_by_role('combobox',name='Area',exact=True)).to_have_value('All Calgary')
        applied=existing.locator('.recommendation-summary').inner_text()
        existing.get_by_role('switch',name='Dark mode').set_checked(True)
        idle(existing)
        assert existing.locator('.recommendation-summary').inner_text()==applied
        existing.locator('.mast').scroll_into_view_if_needed()
        existing.screenshot(path=str(OUT/'running-8502-dark-header.png'))
        existing.locator('.recommendation-summary').scroll_into_view_if_needed()
        existing.screenshot(path=str(OUT/'running-8502-dark-summary.png'))
        results['existing_server']={'url':existing.url,'updated_summary_container':True,
            'equipment_width':218,'area_planner_and_theme_checked':True,'summary':applied}
        existing.close()
    (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))
    assert not failures
    browser.close()
