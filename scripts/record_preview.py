"""Record a local autoplay race without writing the API token to disk.

Requires Playwright + Chromium. The browser recording is silent; add the
licensed game soundtrack during the final edit. This script only creates a
temporary raw video and prints the moment at which the ready screen appears.
"""
import argparse
import os
from pathlib import Path
import time

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a Jev Race autoplay preview")
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--output", type=Path, default=Path("artifacts/preview/raw.webm"))
    args = parser.parse_args()
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
            print(f"Ready screen begins approximately {ready_at:.2f} seconds into the raw video")
        finally:
            secret = ""
            context.close()
            page.video.save_as(str(args.output))
            browser.close()
    print(f"Raw recording: {args.output.resolve()}")


if __name__ == "__main__":
    main()
