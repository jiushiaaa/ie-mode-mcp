"""Opt-in focused native coverage for large pages in IE11 and IE7."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from ie_mode_mcp.browser import Browser
from smoke_ie import check_exploration


def main():
    handler = partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).parent / 'fixtures'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    browser = Browser()
    try:
        base = f'http://127.0.0.1:{server.server_port}/'
        browser.start(base + 'child.html')
        print('STEP: small page started', flush=True)
        for filename, mode in [('interactions.html', 11), ('legacy.html', 7)]:
            page = browser.navigate(base + filename)
            assert page['document_mode'] == mode
            check_exploration(browser)
            print('PASS: exploration in IE' + str(mode), flush=True)
    finally:
        browser.close()
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
