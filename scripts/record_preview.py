"""Record a local autoplay race without writing the API token to disk.

Requires Playwright + Chromium. The browser recording is silent; add the
licensed game soundtrack during the final edit. This script only creates a
temporary raw video and prints the moment at which the ready screen appears.
"""
import argparse
import json
import os
from pathlib import Path
import time

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a Jev Race autoplay preview")
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--mistake-obstacles", default="",
                        help="One-based obstacle numbers where the recorded player makes a staged mistake")
    parser.add_argument("--output", type=Path, default=Path("artifacts/preview/raw.webm"))
    args = parser.parse_args()
    try:
        mistake_numbers = [int(number.strip()) for number in args.mistake_obstacles.split(",") if number.strip()]
    except ValueError:
        parser.error("--mistake-obstacles must contain comma-separated numbers")
    if len(set(mistake_numbers)) != len(mistake_numbers) or any(
            number < 1 or number > args.count for number in mistake_numbers):
        parser.error("mistake obstacles must be distinct and inside the track")
    secret = os.environ.pop("TYPESAFE_API_KEY")
    if len(secret) < 8:
        raise ValueError("TYPESAFE_API_KEY is missing or too short")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=[
            "--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader",
        ])
        context = browser.new_context(viewport={"width": 1200, "height": 720},
                                      record_video_dir=str(args.output.parent),
                                      record_video_size={"width": 1200, "height": 720})
        page = context.new_page()
        started = time.monotonic()
        errors: list[str] = []
        responses: list[dict] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: responses.append(response.json())
                if response.url.endswith("/api/decide") and response.status == 200 else None)
        try:
            track_response = page.request.post(f"{args.url}/api/track",
                                               data={"seed": args.seed, "count": args.count})
            if not track_response.ok:
                raise RuntimeError("Cannot obtain the track for the recording")
            track = track_response.json()
            # Change only the recording page's JavaScript. The server, game and
            # normal human-vs-Jev mode are left untouched. Both API calls still
            # happen; the original model action remains in the report JSON.
            wrong_actions = {}
            for number in mistake_numbers:
                obstacle = track["events"][number - 1]
                wrong_actions[obstacle["id"]] = "jump" if obstacle["type"] in ("beam", "laser") else "slide"
            needle = "  response.actor=actor;\n  response.roundtrip_ms="
            replacement = ("  response.actor=actor;\n"
                           f"  const stagedMistakes={json.dumps(wrong_actions)};\n"
                           "  if(actor==='human' && response.status==='ok' && "
                           "Object.hasOwn(stagedMistakes,event.event_id)){\n"
                           "    response.model_action=response.action;\n"
                           "    response.action=stagedMistakes[event.event_id];\n"
                           "    response.staged_mistake=true;\n"
                           "  }\n  response.roundtrip_ms=")

            def patch_recording_page(route):
                upstream = route.fetch()
                source = upstream.text()
                if source.count(needle) != 1:
                    raise RuntimeError("The recording hook no longer matches app.js")
                route.fulfill(response=upstream, body=source.replace(needle, replacement))

            if wrong_actions:
                page.route("**/assets/app.js", patch_recording_page)
            page.goto(f"{args.url}/race?seed={args.seed}&autoplay=1")
            page.add_style_tag(content="""
                body { background: #061524; }
                main { max-width: none; padding: 0; }
                header, aside, footer, #report-section, .toolbar { display: none !important; }
                .layout { display: block; }
                .arena { border: 0; border-radius: 0; box-shadow: none; }
                .viewport { aspect-ratio: auto; height: 100vh; }
            """)
            page.locator("#count").fill(str(args.count))
            page.locator("#token").fill(secret)
            page.locator("#prepare").click()
            secret = ""
            try:
                page.wait_for_selector("#ready:not([hidden])", timeout=30000)
            except Exception:
                print("Preparation stopped at:", page.locator("#stage-title").inner_text())
                print("Setup error:", page.locator("#setup-error").inner_text())
                print("Browser errors:", errors)
                raise
            ready_at = time.monotonic() - started
            page.wait_for_timeout(1200)
            page.locator("#ready").click()
            page.wait_for_selector("#view-report:not([hidden])", timeout=120000)
            with page.expect_download() as download_event:
                page.locator("#download-json").evaluate("button => button.click()")
            report = json.loads(Path(download_event.value.path()).read_text())
            mistakes = [row for row in report["human_decisions"] if row.get("staged_mistake")]
            if len(mistakes) != len(mistake_numbers):
                raise RuntimeError("Not all staged player mistakes were applied")
            page.wait_for_timeout(3200)
            if errors:
                raise RuntimeError("Browser errors: " + "; ".join(errors))
            if len(responses) != args.count * 2 or any(row.get("status") != "ok" for row in responses):
                raise RuntimeError("The race did not receive two successful Jev answers per obstacle")
            if page.evaluate("localStorage.length + sessionStorage.length") != 0:
                raise RuntimeError("Unexpected browser storage")
            if page.locator("#token").input_value():
                raise RuntimeError("Token field was not cleared")
            print(f"Race complete: {len(responses)} real Jev answers; estimated cost "
                  f"${sum(row.get('cost_usd', 0) for row in responses):.6f}")
            print(f"Winner: {report['result']['winner']}; recorded player mistakes: {mistake_numbers}; "
                  f"penalties {report['result']['racers']['human']['penalties']}:"
                  f"{report['result']['racers']['jev']['penalties']}")
            print(f"Ready screen begins approximately {ready_at:.2f} seconds into the raw video")
        finally:
            secret = ""
            context.close()
            page.video.save_as(str(args.output))
            browser.close()
    print(f"Raw recording: {args.output.resolve()}")


if __name__ == "__main__":
    main()
