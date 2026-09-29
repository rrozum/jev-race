"""End-to-end check with a clearly identified local fixture, never the real API.

Run from the repository root using a Python environment with Playwright installed.
"""
from pathlib import Path
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def serve_fixture(port):
    import uvicorn
    from race.app import Provider, create_app
    from race.brains.jev import ProviderError
    from race.contracts import Agent, Decision
    class FixtureBrain:
        def __init__(self, token):
            self.invalid = token == "invalid-test-token"
        async def choose(self, context):
            if self.invalid:
                raise ProviderError("invalid_token")
            action = "jump"
            if "low beam" in context.state or "horizontal laser" in context.state:
                action = "slide"
            if "hostile drone" in context.state:
                action = "shoot"
            return Decision(action, "test-fixture")
    app = create_app(providers={"jev":Provider("Тестовый агент",lambda token:Agent(FixtureBrain(token)))})
    uvicorn.run(app,host="127.0.0.1",port=port,access_log=False,log_level="warning")


def check():
    from playwright.sync_api import sync_playwright, expect
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    server=subprocess.Popen([sys.executable,__file__,"--serve",str(port)],cwd=ROOT)
    base=f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base+"/healthz",timeout=1);break
            except Exception:time.sleep(.1)
        else:raise RuntimeError("Fixture server did not start")
        with sync_playwright() as p, tempfile.TemporaryDirectory() as temp:
            browser=p.chromium.launch(headless=True,args=['--enable-webgl','--use-gl=angle','--use-angle=swiftshader'])
            page=browser.new_page(viewport={"width":1440,"height":1050},accept_downloads=True)
            errors=[]; calls=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' else None)
            page.on('request',lambda req:calls.append(req.url) if '/api/decide' in req.url else None)
            page.goto(base+'/race?seed=42')
            page.wait_for_selector('#prepare:not([disabled])')
            (ROOT/'artifacts').mkdir(exist_ok=True)
            page.screenshot(path=str(ROOT/'artifacts/setup.png'),full_page=True)
            page.locator('#count').fill('12')
            page.locator('#token').fill('browser-test-credential')
            page.locator('#prepare').click()
            page.wait_for_timeout(5000)
            if errors:
                print('Browser errors:',errors,flush=True)
                page.screenshot(path=str(ROOT/'artifacts/load-error.png'))
                raise AssertionError(errors)
            page.wait_for_selector('#ready:not([hidden])',timeout=60000)
            assert page.locator('#token').input_value()==''
            page.wait_for_timeout(1700)
            assert not calls, 'Race must wait for a keypress'
            page.locator('#live-camera').select_option('stack')
            page.keyboard.press('w')
            page.wait_for_selector('#stage', state='hidden')
            page.wait_for_timeout(700)
            page.screenshot(path=str(ROOT/'artifacts/stack.png'))
            page.locator('#live-camera').select_option('side')
            page.wait_for_timeout(300)
            page.screenshot(path=str(ROOT/'artifacts/side.png'))
            page.wait_for_selector('#view-report:not([hidden])',timeout=90000)
            assert len(calls)==12
            assert page.locator('#token').input_value()==''
            page.locator('#view-report').click()
            with page.expect_download() as downloaded:
                page.locator('#download-json').click()
            file=Path(temp)/'report.json';downloaded.value.save_as(file)
            report=json.loads(file.read_text())
            assert report['result']['racers']['jev']['penalties']==0, report['result']
            assert report['result']['racers']['human']['penalties']==12
            assert 'browser-test-credential' not in file.read_text()
            with page.expect_download() as downloaded:
                page.locator('#download-html').click()
            file=Path(temp)/'report.html';downloaded.value.save_as(file)
            assert '<script' not in file.read_text()
            assert page.evaluate('localStorage.length + sessionStorage.length')==0
            assert not page.context.cookies()
            page.screenshot(path=str(ROOT/'artifacts/report.png'),full_page=True)
            page.locator('#restart').click()
            assert page.locator('#report-section').is_hidden()
            assert page.locator('#report').inner_text()==''
            page.locator('#count').fill('4')
            page.locator('#token').fill('invalid-test-token')
            page.locator('#prepare').click()
            page.wait_for_selector('#ready:not([hidden])',timeout=60000)
            page.locator('#ready').click()
            expect(page.locator('#stage-title')).to_have_text('TypeSafe не принял токен',timeout=20000)
            assert page.locator('#token').input_value()==''
            page.reload()
            page.wait_for_selector('#prepare:not([disabled])')
            assert page.locator('#report-section').is_hidden()
            assert page.locator('#token').input_value()==''
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(ROOT/'artifacts/mobile.png'),full_page=True)
            assert not errors, errors
            print('Browser smoke: ready gate, both cameras, 12 obstacles, reports, token errors and cleanup passed.')
            browser.close()
    finally:
        server.terminate();server.wait(timeout=10)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--serve':serve_fixture(int(sys.argv[2]))
    else:check()
