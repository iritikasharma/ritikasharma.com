#!/usr/bin/env python3
"""
Updates newsletter subscriber counts using the LinkedIn API.
No scraping, no bot detection — authenticated API calls only.

Requires GitHub Secrets:
  LINKEDIN_ACCESS_TOKEN   — OAuth 2.0 Bearer token (60-day lifetime)
  LINKEDIN_CLIENT_ID      — App client ID (for token refresh)
  LINKEDIN_CLIENT_SECRET  — App client secret (for token refresh)

Falls back to manual counts from workflow_dispatch inputs when set.
"""

import os
import re
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error

NEWSLETTERS = [
    {
        "slug": "bench-to-brain",
        "id": "7414488376021774338",
        "url": "https://www.linkedin.com/newsletters/bench-to-brain-7414488376021774338/",
        "files": ["index.html"],
        "env_var": "COUNT_BENCH_TO_BRAIN",
    },
    {
        "slug": "signal-over-noise",
        "id": "7421784782902153216",
        "url": "https://www.linkedin.com/newsletters/signal-over-noise-7421784782902153216/",
        "files": ["index.html"],
        "env_var": "COUNT_SIGNAL_OVER_NOISE",
    },
    {
        "slug": "science-tales",
        "id": "7427433291634540546",
        "url": "https://www.linkedin.com/newsletters/science-tales-7427433291634540546/",
        "files": ["index.html"],
        "env_var": "COUNT_SCIENCE_TALES",
    },
    {
        "slug": "rendered",
        "id": "7434333824727060480",
        "url": "https://www.linkedin.com/newsletters/rendered-7434333824727060480/",
        "files": ["index.html"],
        "env_var": "COUNT_RENDERED",
    },
    {
        "slug": "atomic-ambition",
        "id": "7456739889594683392",
        "url": "https://www.linkedin.com/newsletters/atomic-ambition-7456739889594683392/",
        "files": ["index.html"],
        "env_var": "COUNT_ATOMIC_AMBITION",
    },
]


def li_get(path: str, token: str) -> dict | None:
    """Make an authenticated GET request to the LinkedIn API."""
    url = f"https://api.linkedin.com{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202401",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"  HTTP {e.code} from {path}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"  Request error: {exc}", file=sys.stderr)
        return None


def refresh_token(client_id: str, client_secret: str, refresh_tok: str) -> str | None:
    """Exchange a refresh token for a new access token."""
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_tok,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("access_token")
    except Exception as exc:
        print(f"  Token refresh failed: {exc}", file=sys.stderr)
        return None


def get_subscriber_count(newsletter_id: str, token: str) -> str | None:
    """Try multiple LinkedIn API endpoints to find subscriber count."""

    # Approach 1: Newsletter details via REST API
    data = li_get(f"/rest/newsletters/urn%3Ali%3AnewsletterRootContent%3A{newsletter_id}", token)
    if data:
        for key in ("subscriberCount", "followerCount", "totalFollowerCount", "memberCount"):
            if key in data:
                n = data[key]
                if isinstance(n, int) and n > 0:
                    return f"{n:,}"

    time.sleep(1)

    # Approach 2: Newsletter via v2 API
    data = li_get(f"/v2/newsletters/{newsletter_id}", token)
    if data:
        for key in ("subscriberCount", "followerCount", "totalFollowerCount", "memberCount"):
            if key in data:
                n = data[key]
                if isinstance(n, int) and n > 0:
                    return f"{n:,}"
        # Check nested elements
        raw = json.dumps(data)
        for pat in (r'"subscriberCount"\s*:\s*(\d+)', r'"followerCount"\s*:\s*(\d+)'):
            m = re.search(pat, raw)
            if m:
                n = int(m.group(1))
                if n > 0:
                    return f"{n:,}"

    time.sleep(1)

    # Approach 3: Organization follower statistics endpoint
    urn = urllib.parse.quote(f"urn:li:newsletter:{newsletter_id}")
    data = li_get(f"/v2/organizationalEntityFollowerStatistics?q=organizationalEntity&organizationalEntity={urn}", token)
    if data:
        elements = data.get("elements", [])
        if elements:
            total = elements[0].get("followerCountsByAssociationType", {})
            count = sum(v.get("followerCounts", {}).get("organicFollowerCount", 0)
                       for v in total.values() if isinstance(v, dict))
            if count > 0:
                return f"{count:,}"

    return None


def update_file(path: str, slug: str, count: str) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()
    updated = re.sub(
        rf'(data-nl="{re.escape(slug)}">)[^<]*(</span>)',
        rf'\g<1>{count}\2',
        original,
    )
    if updated == original:
        print(f"    {path}: already {count}")
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"    {path}: → {count}")
    return True


def main() -> int:
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    client_id = os.environ.get("LINKEDIN_CLIENT_ID", "").strip()
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "").strip()
    refresh_tok = os.environ.get("LINKEDIN_REFRESH_TOKEN", "").strip()

    # Try refreshing the token if a refresh token is available
    if refresh_tok and client_id and client_secret:
        print("Refreshing access token…")
        new_token = refresh_token(client_id, client_secret, refresh_tok)
        if new_token:
            token = new_token
            print("  Token refreshed.")
        else:
            print("  Refresh failed — using stored access token.")

    if not token:
        print("ERROR: LINKEDIN_ACCESS_TOKEN not set in GitHub Secrets.", file=sys.stderr)
        return 1

    # Verify token works
    me = li_get("/v2/me", token)
    if me is None:
        print("ERROR: Token invalid or expired. Generate a new one at developer.linkedin.com.", file=sys.stderr)
        return 1
    name = me.get("localizedFirstName", "") + " " + me.get("localizedLastName", "")
    print(f"Authenticated as: {name.strip()}")

    any_changed = False

    for nl in NEWSLETTERS:
        slug = nl["slug"]
        print(f"\n── {nl['slug']}")

        # Manual override from workflow_dispatch input
        manual = (os.environ.get(nl["env_var"]) or "").strip()
        if manual:
            print(f"  Manual: {manual}")
            count = manual
        else:
            count = get_subscriber_count(nl["id"], token)
            if count:
                print(f"  API: {count}")
            else:
                print(f"  Could not fetch count — skipping", file=sys.stderr)
                continue

        for fname in nl["files"]:
            changed = update_file(fname, slug, count)
            any_changed = any_changed or changed

    return 0


if __name__ == "__main__":
    sys.exit(main())
