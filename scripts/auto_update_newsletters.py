#!/usr/bin/env python3
"""
Monthly newsletter subscriber count updater.
Runs locally (not on GitHub Actions) so LinkedIn's anti-bot protection
doesn't block it. Triggered by macOS LaunchAgent on the 1st of each month.

Reads li_at from ~/.config/ritikasharma/linkedin_li_at
Updates index.html, commits, and pushes to GitHub.
"""

import os, re, sys, time, subprocess
from datetime import date
from pathlib import Path

REPO      = Path(__file__).parent.parent
LI_AT_FILE = Path.home() / ".config" / "ritikasharma" / "linkedin_li_at"
VENV_PYTHON = Path.home() / ".local" / "ritikasharma-site" / "venv" / "bin" / "python3"

NEWSLETTERS = [
    {
        "slug": "bench-to-brain",
        "name": "Bench to Brain",
        "url": "https://www.linkedin.com/newsletters/bench-to-brain-7414488376021774338/",
    },
    {
        "slug": "atomic-ambition",
        "name": "Atomic Ambition",
        "url": "https://www.linkedin.com/newsletters/atomic-ambition-7456739889594683392/",
    },
    {
        "slug": "signal-over-noise",
        "name": "Signal Over Noise",
        "url": "https://www.linkedin.com/newsletters/signal-over-noise-7421784782902153216/",
    },
    {
        "slug": "science-tales",
        "name": "Science Tales",
        "url": "https://www.linkedin.com/newsletters/science-tales-7427433291634540546/",
    },
    {
        "slug": "rendered",
        "name": "Rendered",
        "url": "https://www.linkedin.com/newsletters/rendered-7434333824727060480/",
    },
]

COUNT_PATTERNS = (
    r'"followerCount"\s*:\s*(\d+)',
    r'"subscriberCount"\s*:\s*(\d+)',
    r'"totalFollowerCount"\s*:\s*(\d+)',
    r'([\d,]+)\s+subscribers',
    r'([\d,]+)\s+followers',
)


def read_li_at() -> str | None:
    if LI_AT_FILE.exists():
        val = LI_AT_FILE.read_text().strip()
        if val:
            return val
    return os.environ.get("LINKEDIN_LI_AT", "").strip() or None


def extract_count(html: str) -> str | None:
    for pat in COUNT_PATTERNS:
        m = re.search(pat, html)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                n = int(raw)
                if n > 0:
                    return f"{n:,}"
            except ValueError:
                continue
    return None


def fetch_count(url: str, li_at: str) -> str | None:
    from playwright.sync_api import sync_playwright
    print("  → launching Chromium…")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )
            ctx.add_cookies([{
                "name": "li_at", "value": li_at,
                "domain": ".linkedin.com", "path": "/",
                "httpOnly": True, "secure": True,
            }])
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(4_000)
            html = page.content()
            browser.close()
        count = extract_count(html)
        if count:
            return count
        print("  Count not found in rendered page", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"  Playwright error: {exc}", file=sys.stderr)
        return None


def update_index(slug: str, count: str) -> bool:
    path = REPO / "index.html"
    content = path.read_text(encoding="utf-8")
    updated = re.sub(
        rf'(data-nl="{re.escape(slug)}">)[^<]*(</span>)',
        rf'\g<1>{count}\2',
        content,
    )
    if updated == content:
        print(f"  index.html: no change for {slug}")
        return False
    path.write_text(updated, encoding="utf-8")
    print(f"  index.html: {slug} → {count}")
    return True


def git_push(changed_slugs: list[str]) -> None:
    os.chdir(REPO)
    subprocess.run(["git", "add", "index.html"], check=True)
    msg = f"chore: update newsletter subscriber counts [automated {date.today()}]"
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push"], check=True)
    print(f"Pushed to GitHub — updated: {', '.join(changed_slugs)}")


def main() -> int:
    li_at = read_li_at()
    if not li_at:
        print(
            "ERROR: li_at cookie not found.\n"
            f"Save it to: {LI_AT_FILE}\n"
            "Run scripts/setup_auto_update.sh to configure.",
            file=sys.stderr,
        )
        return 1

    changed: list[str] = []

    for nl in NEWSLETTERS:
        print(f"\n── {nl['name']}")
        count = fetch_count(nl["url"], li_at)
        if count is None:
            print(f"  Skipping — could not fetch count")
            continue
        print(f"  Count: {count}")
        if update_index(nl["slug"], count):
            changed.append(nl["slug"])
        time.sleep(2)

    if changed:
        git_push(changed)
    else:
        print("\nNo changes to commit.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
