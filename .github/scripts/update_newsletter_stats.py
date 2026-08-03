#!/usr/bin/env python3
"""
Updates newsletter subscriber counts in portfolio HTML files.

Uses one persistent Playwright browser session for all newsletters.
Intercepts LinkedIn's internal Voyager API responses to get subscriber
counts from structured JSON — more reliable than parsing rendered HTML.
"""

import os
import re
import sys
import time
import random

NEWSLETTERS = [
    {
        "slug": "bench-to-brain",
        "url": "https://www.linkedin.com/newsletters/bench-to-brain-7414488376021774338/",
        "files": ["index.html"],
        "env_var": "COUNT_BENCH_TO_BRAIN",
    },
    {
        "slug": "signal-over-noise",
        "url": "https://www.linkedin.com/newsletters/signal-over-noise-7421784782902153216/",
        "files": ["index.html"],
        "env_var": "COUNT_SIGNAL_OVER_NOISE",
    },
    {
        "slug": "science-tales",
        "url": "https://www.linkedin.com/newsletters/science-tales-7427433291634540546/",
        "files": ["index.html"],
        "env_var": "COUNT_SCIENCE_TALES",
    },
    {
        "slug": "rendered",
        "url": "https://www.linkedin.com/newsletters/rendered-7434333824727060480/",
        "files": ["index.html"],
        "env_var": "COUNT_RENDERED",
    },
    {
        "slug": "atomic-ambition",
        "url": "https://www.linkedin.com/newsletters/atomic-ambition-7456739889594683392/",
        "files": ["index.html"],
        "env_var": "COUNT_ATOMIC_AMBITION",
    },
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

COUNT_PATTERNS = (
    r'"followerCount"\s*:\s*(\d+)',
    r'"subscriberCount"\s*:\s*(\d+)',
    r'"totalFollowerCount"\s*:\s*(\d+)',
    r'"memberCount"\s*:\s*(\d+)',
    r'([\d,]+)\s+subscribers',
    r'([\d,]+)\s+followers',
)


def extract_count(text: str) -> str | None:
    for pat in COUNT_PATTERNS:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                n = int(raw)
                if 10 < n < 10_000_000:
                    return f"{n:,}"
            except ValueError:
                continue
    return None


def fetch_all_with_playwright(newsletters: list[dict], li_at: str) -> dict[str, str]:
    from playwright.sync_api import sync_playwright

    counts: dict[str, str] = {}
    api_buffer: list[str] = []

    def capture_api(response):
        if "voyager/api" in response.url or "linkedin.com/api" in response.url:
            try:
                api_buffer.append(response.text())
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
            ],
        )
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        ctx.add_cookies([
            {
                "name": "li_at",
                "value": li_at,
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            },
            {
                "name": "lang",
                "value": "v=2&lang=en-us",
                "domain": ".linkedin.com",
                "path": "/",
            },
        ])

        page = ctx.new_page()
        page.on("response", capture_api)

        # Warm up: visit the feed so LinkedIn establishes a real session
        print("  Warming up session on linkedin.com/feed…")
        try:
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30_000)
            if "linkedin.com/login" in page.url or "authwall" in page.url:
                print("  ERROR: Redirected to login — li_at cookie is expired. Get a fresh one from Chrome DevTools.", file=sys.stderr)
                browser.close()
                return {}
            page.wait_for_timeout(3_000)
            print("  Session OK — logged in as expected")
        except Exception as exc:
            print(f"  Warm-up failed: {exc}", file=sys.stderr)
            browser.close()
            return {}

        for nl in newsletters:
            slug = nl["slug"]
            url = nl["url"]
            api_buffer.clear()
            print(f"\n  → {slug}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)

                if "linkedin.com/login" in page.url or "authwall" in page.url:
                    print(f"    Blocked by login wall", file=sys.stderr)
                    continue

                # Wait for JS to load subscriber count
                page.wait_for_timeout(5_000)

                # Try API responses first (most reliable)
                count = None
                for api_text in api_buffer:
                    count = extract_count(api_text)
                    if count:
                        print(f"    Count (from API): {count}")
                        break

                # Fall back to rendered HTML
                if count is None:
                    count = extract_count(page.content())
                    if count:
                        print(f"    Count (from HTML): {count}")

                if count:
                    counts[slug] = count
                else:
                    print(f"    Count not found", file=sys.stderr)

            except Exception as exc:
                print(f"    Error: {exc}", file=sys.stderr)

            # Human-like delay: 4–8 seconds between pages
            delay = random.uniform(4, 8)
            print(f"    Waiting {delay:.1f}s before next page…")
            time.sleep(delay)

        browser.close()

    return counts


def update_file(path: str, slug: str, count: str) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    updated = re.sub(
        rf'(data-nl="{re.escape(slug)}">)[^<]*(</span>)',
        rf'\g<1>{count}\2',
        original,
    )

    if updated == original:
        print(f"    {path}: no change (already {count})")
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"    {path}: updated → {count}")
    return True


def main() -> int:
    li_at = os.environ.get("LINKEDIN_LI_AT", "").strip() or None
    if not li_at:
        print("ERROR: LINKEDIN_LI_AT not set", file=sys.stderr)
        return 1

    manual_counts: dict[str, str] = {}
    needs_scrape: list[dict] = []

    for nl in NEWSLETTERS:
        manual = (os.environ.get(nl["env_var"]) or "").strip()
        if manual:
            print(f"Manual override — {nl['slug']}: {manual}")
            manual_counts[nl["slug"]] = manual
        else:
            needs_scrape.append(nl)

    scraped: dict[str, str] = {}
    if needs_scrape:
        print(f"\nScraping {len(needs_scrape)} newsletter(s)…")
        scraped = fetch_all_with_playwright(needs_scrape, li_at)

    all_counts = {**manual_counts, **scraped}

    print("\nUpdating index.html…")
    for nl in NEWSLETTERS:
        slug = nl["slug"]
        count = all_counts.get(slug)
        if count is None:
            print(f"  {slug}: skipped")
            continue
        for fname in nl["files"]:
            update_file(fname, slug, count)

    return 0


if __name__ == "__main__":
    sys.exit(main())
