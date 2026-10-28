"""Opt-in real IE mode end-to-end test against local disposable fixtures."""
from functools import partial
import faulthandler
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import UnexpectedAlertPresentException

from ie_mode_mcp.browser import Browser


def ref(snapshot, element_id):
    return next(c["ref"] for c in snapshot["controls"] if c["id"] == element_id)


def check_interactions(browser):
    print('STEP: testing new interactions', flush=True)
    assert browser.status()['state'] == 'ready'
    page = browser.snapshot()
    for action, target, expected in [('double', 'doubleTarget', 'Double received'),
                                     ('right', 'rightTarget', 'Right received')]:
        browser.act(action, ref(page, target))
        page = browser.wait_text(expected)
    browser.hover(ref(page, 'hoverTarget'))
    page = browser.wait_text('Hover received')
    browser.press_key(ref(page, 'keyTarget'), 'ENTER')
    page = browser.wait_text('Enter received')
    browser.act('click', ref(page, 'asyncTarget'))
    ready = browser.wait_ready(seconds=10, stable_seconds=1)
    assert ready['ready'] and ready['skipped_frames'] == 0
    page = browser.snapshot()
    assert 'Async ready' in page['text']
    assert 'Loading' not in browser.wait_text('Loading', gone=True)['text']
    assert browser.scroll('bottom')['position']['y'] > 0
    assert browser.scroll('top')['position']['y'] == 0
    page = browser.snapshot()
    assert browser.scroll('into_view', ref=ref(page, 'bottomTarget'))['position']['y'] > 0
    browser.scroll('top')
    print('PASS: double/right click, hover, key, AJAX readiness and scrolling', flush=True)


def check_exploration(browser):
    page = browser.snapshot()
    assert page['total_controls'] > 200 and page['next_offset'] == 200
    assert page['next_text_offset'] == 12000
    more = browser.snapshot(offset=200, text_offset=12000)
    assert more['controls'] and more['text'] and more['next_offset'] is None
    assert set(c['id'] for c in more['controls']).isdisjoint(c['id'] for c in page['controls'])
    region = browser.find('exploreRegion', by='id')['matches'][0]['ref']
    page = browser.snapshot(root_ref=region, limit=5, text_limit=100)
    assert page['total_controls'] == 221 and page['next_offset'] == 5 and page['next_text_offset'] == 100
    assert page['text'] == ('Page text. ' * 20)[:100]
    assert [c['id'] for c in page['controls']] == ['exploreButton' + str(i) for i in range(5)]
    more = browser.snapshot(root_ref=page['scope_ref'], offset=5, limit=5, text_offset=100, text_limit=100)
    assert more['text'] == ('Page text. ' * 20)[100:200]
    assert [c['id'] for c in more['controls']] == ['exploreButton' + str(i) for i in range(5, 10)]
    found = browser.find('Explore item 219')
    assert len(found['matches']) == 1 and found['matches'][0]['id'] == 'exploreButton219'
    png = browser.screenshot(found['matches'][0]['ref'])
    assert png.startswith(b'\x89PNG')
    target = browser.find('exploreField', by='id')['matches'][0]['ref']
    browser.act('fill', target, 'Found via search', fill_mode='dom')
    target = browser.find('exploreField', by='id')['matches'][0]['ref']
    assert browser.snapshot(include_values=True, root_ref=target)['controls'][0]['value'] == 'Found via search'
    assert browser.find('Found via search')['total'] == 0  # no input values searched
    browser.scroll('top')
    print('PASS: paged controls/text, region scope renewal, search refs and element screenshot', flush=True)


def main():
    faulthandler.dump_traceback_later(60, repeat=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).parent / "fixtures"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    browser = Browser()
    try:
        snapshot = browser.start(f"http://127.0.0.1:{server.server_port}/index.html")
        print("STEP: browser started", flush=True)
        assert snapshot["document_mode"], "Page is not in IE mode"
        assert "DO_NOT_EXPOSE_PASSWORD" not in str(snapshot)
        assert "HIDDEN_SENTINEL" not in str(snapshot)
        assert "SCRIPT_SENTINEL" not in str(snapshot)
        chosen = browser.choose_file(ref(snapshot, 'attachment'), str(Path(__file__).resolve().parent / 'fixtures' / 'child.html'))
        assert chosen['selected'] and chosen['filename'] == 'child.html'
        snapshot = browser.snapshot(include_values=True)
        assert 'DO_NOT_EXPOSE_PASSWORD' not in str(snapshot)
        browser.act('click', ref(snapshot, 'legacyRow'), click_mode='dom')
        snapshot = browser.wait_text('undefined:undefined')
        browser.prepare_legacy_row(ref(snapshot, 'legacyRow'), ['_id','_status'])
        snapshot = browser.snapshot()
        browser.act('click', ref(snapshot, 'legacyRow'), click_mode='dom')
        snapshot = browser.wait_text('fixture-42:ready')
        snapshot = browser.snapshot(include_values=True)
        assert next(c for c in snapshot['controls'] if c['id']=='customer')['value'] == ''
        batch = browser.fill_many([{'ref':ref(snapshot,'customer'),'value':'中文客户'}, {'ref':ref(snapshot,'note'),'value':'Fixture note'}])
        assert batch['verified'] is True
        snapshot = browser.snapshot(include_values=True)
        assert next(c for c in snapshot['controls'] if c['id']=='customer')['value'] == '中文客户'
        browser.act("fill", ref(snapshot, "customer"), "Fixture customer")
        print("STEP: filled", flush=True)
        snapshot = browser.snapshot()
        browser.act("select", ref(snapshot, "region"), "Export")
        print("STEP: selected", flush=True)
        snapshot = browser.snapshot()
        browser.act("click", ref(snapshot, "search"))
        snapshot = browser.wait_text("Fixture customer")
        print("STEP: query complete", flush=True)
        assert browser.table(ref(snapshot, "results"))["rows"][1] == ["Fixture customer"]
        snapshot = browser.frame(ref(snapshot, "child"))
        assert "Frame content ready" in snapshot["text"]
        snapshot = browser.frame(parent=True)
        print("STEP: frame complete", flush=True)
        browser.act("click", ref(snapshot, "dialog"))
        try:
            browser.snapshot()
        except UnexpectedAlertPresentException:
            pass
        assert browser.alert()["text"] == "Fixture alert"
        browser.alert("accept")
        print("STEP: alert complete", flush=True)
        snapshot = browser.snapshot()
        before = browser.windows()
        browser.act("click", ref(snapshot, "popup"))
        WebDriverWait(browser.driver, 10).until(lambda d: len(d.window_handles) > len(before["handles"]))
        new = next(h for h in browser.windows()["handles"] if h not in before["handles"])
        assert "Frame content ready" in browser.window(new)["text"]
        browser.window(before["current"])
        snapshot = browser.open_page(f"http://127.0.0.1:{server.server_port}/child.html")
        assert 'Frame content ready' in snapshot['text']
        assert 'ie_mode_mcp_fixture=opener' in browser.driver.execute_script('return document.cookie')
        browser.close_window()
        page = browser.navigate(f"http://127.0.0.1:{server.server_port}/interactions.html")
        assert page['document_mode'] == 11
        resized = browser.resize(1100, 850)
        assert resized['window']['width'] > 0
        assert browser.wait_ready()['documents'] == 2
        check_interactions(browser)
        check_exploration(browser)
        browser.navigate(f"http://127.0.0.1:{server.server_port}/child.html")
        assert 'Interaction fixture' in browser.history('back')['text']
        assert 'Frame content ready' in browser.history('forward')['text']
        snapshot = browser.navigate(f"http://127.0.0.1:{server.server_port}/legacy.html")
        assert snapshot['document_mode'] == 7
        try:
            browser.choose_file(ref(snapshot, 'attachment'), str(Path(__file__).resolve().parent / 'fixtures' / 'child.html'))
        except ValueError as exc:
            assert 'IE11 document mode' in str(exc)
        else:
            raise AssertionError('Legacy file selection must fail before native input')
        snapshot = browser.snapshot()
        assert 'LEGACY_SECRET' not in str(snapshot)
        assert 'LEGACY_HIDDEN' not in str(snapshot)
        assert next(c for c in snapshot['controls'] if c['id']=='legacyCustomer')['label'].strip() == 'Legacy customer'
        browser.act('fill', ref(snapshot, 'legacyCustomer'), 'Legacy customer')
        snapshot = browser.snapshot(True)
        assert next(c for c in snapshot['controls'] if c['id']=='legacyCustomer')['value'] == 'Legacy customer'
        browser.act('click', ref(snapshot, 'legacyAction'))
        assert 'Legacy saved' in browser.wait_text('Legacy saved')['text']
        snapshot = browser.snapshot()
        assert not any(c['id'] == 'plainCell' for c in snapshot['controls'])
        browser.act('click', ref(snapshot, 'legacyTab'), click_mode='dom')
        snapshot = browser.wait_text('Legacy tab selected')
        browser.act('click', ref(snapshot, 'ariaTab'), click_mode='dom')
        assert 'ARIA tab selected' in browser.wait_text('ARIA tab selected')['text']
        snapshot = browser.snapshot()
        ids = {c['id'] for c in snapshot['controls']}
        assert {'legacySuggestion', 'ariaSuggestion'} <= ids
        assert not {'hiddenSuggestion', 'plainSuggestion'} & ids
        browser.act('click', ref(snapshot, 'legacySuggestion'), click_mode='dom')
        assert 'Suggestion selected' in browser.wait_text('Suggestion selected')['text']
        check_interactions(browser)
        check_exploration(browser)
        snapshot = browser.open_page(f"http://127.0.0.1:{server.server_port}/child.html")
        assert 'Frame content ready' in snapshot['text']
        assert 'ie_mode_mcp_fixture=opener' in browser.driver.execute_script('return document.cookie')
        browser.close_window()
        print('PASS: IE7 document mode snapshot, labels, fill and click')
        print("PASS: IE document mode, password omission, fill, select, query, table, frame, alert, popup")
    finally:
        browser.close()
        server.shutdown()
        server.server_close()
        faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    main()
