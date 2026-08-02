#!/usr/bin/env python3
"""
Scrapes LinkedIn newsletter follower counts and updates portfolio HTML files.
Runs on the 1st of every month via GitHub Actions.

Requires the LINKEDIN_LI_AT GitHub Secret (your li_at session cookie).
Without it the script still runs but LinkedIn may redirect to the login wall,
in which case counts are left unchanged.
"""

import os
import re
import sys
import time

import requests

NEWSLETTERS = [
    {
        "slug": "bench-to-brain",
        "url": "https://www.linkedin.com/newsletters/bench-to-brain-7414488376021774338/",
        "files": ["bench-to-brain.html", "index.html"],
    },
    {
        "slug": "signal-over-noise",
        "url": "https://www.linkedin.com/newsletters/signal-over-noise-7421784782902153216/",
        "files": ["signal-over-noise.html", "index.html"],
    },
    {
        "slug": "science-tales",
        "url": "https://www.linkedin.com/newsletters/science-tales-7427433291634540546/",
        "files": ["science-tales.html", "index.html"],
    },
    {
        "slug": "rendered",
        "url": "https://www.linkedin.com/newsletters/rendered-7434333824727060480/",
        "files": ["rendered.html", "index.html"],
    },
    {
        "slug": "atomic-ambition",
        "url": "https://www.linkedin.com/newsletters/atomic-ambition-7456739889594683392/",
        "files": ["atomic-ambition.html", "index.html"],
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xhtml;q=0.9,*/*;q=0.8",
}


def fetch_follower_count(url: str, li_at: str | None) -> str | None:
    cookies = {"li_at": li_at} if li_at else {}
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=20, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"  Request failed: {exc}", file=sys.stderr)
        return None

    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code} — skipping", file=sys.stderr)
        return None

    html = resp.text

    # LinkedIn embeds JSON data in the page. Try several known field names.
    for pattern in (
        r'"followerCount"\s*:\s*(\d+)',
        r'"subscriberCount"\s*:\s*(\d+)',
        r'"totalFollowerCount"\s*:\s*(\d+)',
        r'"memberCount"\s*:\s*(\d+)',
    ):
        m = re.search(pattern, html)
        if m:
            count = int(m.group(1))
            if count > 0:
                return format_count(count)

    # Fallback: plain-text patterns like "1,243 followers"
    m = re.search(r'([\d,]+)\s+followers', html)
    if m:
        return m.group(1).replace(",", "")

    print("  Could not find follower count in page HTML", file=sys.stderr)
    return None


def format_count(n: int) -> str:
    """Return a human-readable count: 1234 → '1,234'."""
    return f"{n:,}"


def update_file(path: str, slug: str, count: str) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    updated = re.sub(
        rf'(data-nl="{re.escape(slug)}">)[^<]*(</span>)',
        rf'\g<1>{count}\2',
        original,
    )

    if updated == original:
        print(f"  {path}: no change (pattern not found or count unchanged)")
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"  {path}: updated to {count}")
    return True


def main():
    li_at = os.environ.get("LINKEDIN_LI_AT") or None
    if not li_at:
        print("Warning: LINKEDIN_LI_AT not set — LinkedIn may redirect to login wall", file=sys.stderr)

    any_changed = False
    seen_files: set[str] = set()

    for nl in NEWSLETTERS:
        slug = nl["slug"]
        print(f"\n{slug}")
        count = fetch_follower_count(nl["url"], li_at)
        if count is None:
            print("  Skipping — could not retrieve count")
            continue

        print(f"  Fetched count: {count}")
        for fname in nl["files"]:
            if fname not in seen_files:
                seen_files.add(fname)
            changed = update_file(fname, slug, count)
            any_changed = any_changed or changed

        time.sleep(2)  # polite delay between requests

    return 0 if any_changed else 0


if __name__ == "__main__":
    sys.exit(main())
