#!/usr/bin/env python3
"""
Updates newsletter subscriber counts in portfolio HTML files.

Priority order per newsletter:
  1. Manual count from env var (COUNT_BENCH_TO_BRAIN, etc.) — used when
     workflow is triggered manually with values filled in
  2. Playwright scrape — headless Chrome with li_at cookie (handles JS rendering)
  3. Requests fallback — plain HTTP, rarely works for LinkedIn but kept as last resort

Run via GitHub Actions on the 1st of each month, or trigger manually with counts.
"""

import os
import re
import sys
import time

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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xhtml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.linkedin.com/",
    "Origin": "https://www.linkedin.com",
}

COUNT_PATTERNS = (
    r'"followerCount"\s*:\s*(\d+)',
    r'"subscriberCount"\s*:\s*(\d+)',
    r'"totalFollowerCount"\s*:\s*(\d+)',
    r'"memberCount"\s*:\s*(\d+)',
    r'([\d,]+)\s+subscribers',
    r'([\d,]+)\s+followers',
)


def format_count(n: int) -> str:
    return f"{n:,}"


def extract_count_from_html(html: str) -> str | None:
    for pat in COUNT_PATTERNS:
        m = re.search(pat, html)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                n = int(raw)
                if n > 0:
                    return format_count(n)
            except ValueError:
                continue
    return None


def fetch_with_playwright(url: str, li_at: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not available", file=sys.stderr)
        return None

    print("  Trying Playwright (headless Chrome)…")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            ctx = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="en-US",
                viewport={"width": 1280, "height": 800},
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xhtml;q=0.9,*/*;q=0.8",
                },
            )
            # Mask automation fingerprint
            ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
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
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            # Check we're not on a login/redirect loop page
            if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
                print(f"  Redirected to login — li_at cookie is expired or invalid", file=sys.stderr)
                browser.close()
                return None
            # Give JS a moment to hydrate subscriber count
            page.wait_for_timeout(4_000)
            html = page.content()
            browser.close()
        return extract_count_from_html(html)
    except Exception as exc:
        print(f"  Playwright error: {exc}", file=sys.stderr)
        return None


def fetch_with_requests(url: str, li_at: str | None) -> str | None:
    import requests as req
    print("  Trying requests fallback…")
    cookies = {"li_at": li_at} if li_at else {}
    try:
        resp = req.get(url, headers=HEADERS, cookies=cookies, timeout=20, allow_redirects=True)
    except req.RequestException as exc:
        print(f"  Request failed: {exc}", file=sys.stderr)
        return None
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}", file=sys.stderr)
        return None
    return extract_count_from_html(resp.text)


def update_file(path: str, slug: str, count: str) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    updated = re.sub(
        rf'(data-nl="{re.escape(slug)}">)[^<]*(</span>)',
        rf'\g<1>{count}\2',
        original,
    )

    if updated == original:
        print(f"    {path}: no change")
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"    {path}: → {count}")
    return True


def main() -> int:
    li_at = os.environ.get("LINKEDIN_LI_AT") or None
    if not li_at:
        print("Warning: LINKEDIN_LI_AT not set", file=sys.stderr)

    any_changed = False

    for nl in NEWSLETTERS:
        slug = nl["slug"]
        print(f"\n── {slug}")

        # 1. Manual count from workflow_dispatch inputs
        manual = (os.environ.get(nl["env_var"]) or "").strip()
        if manual:
            print(f"  Manual count provided: {manual}")
            count = manual
        elif li_at:
            # 2. Playwright (handles JS-rendered counts)
            count = fetch_with_playwright(nl["url"], li_at)
            if count is None:
                # 3. requests fallback
                count = fetch_with_requests(nl["url"], li_at)
        else:
            count = fetch_with_requests(nl["url"], None)

        if count is None:
            print("  Could not determine count — skipping")
            continue

        print(f"  Count: {count}")
        for fname in nl["files"]:
            changed = update_file(fname, slug, count)
            any_changed = any_changed or changed

        time.sleep(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
