#!/usr/bin/env python3
"""
Fetches Ritika Sharma's Google Scholar stats and updates portfolio HTML files.
Runs on the 1st of every month via GitHub Actions.
"""

import re
import sys

SCHOLAR_ID = "4iq6z48AAAAJ"


def fetch_stats():
    from scholarly import scholarly
    author = scholarly.search_author_id(SCHOLAR_ID)
    author = scholarly.fill(author, sections=["basics", "indices", "publications"])
    citations = author.get("citedby", 0)
    hindex = author.get("hindex", 0)
    i10index = author.get("i10index", 0)
    pub_count = len(author.get("publications", []))
    return {
        "citations": citations,
        "hindex": hindex,
        "i10index": i10index,
        "publications": pub_count,
    }


def update_publications_html(stats):
    with open("publications.html", "r") as f:
        content = f.read()

    pub_display = f"{stats['publications']}+"

    content = re.sub(
        r'(data-count=")(\d+)(">)(\d+\+?)(</div><div class="stat-lbl">Publications</div>)',
        lambda m: f'{m.group(1)}{stats["publications"]}{m.group(3)}{pub_display}{m.group(5)}',
        content,
    )
    content = re.sub(
        r'(data-count=")(\d+)(">)(\d+\+?)(</div><div class="stat-lbl">Citations</div>)',
        lambda m: f'{m.group(1)}{stats["citations"]}{m.group(3)}{stats["citations"]}{m.group(5)}',
        content,
    )
    content = re.sub(
        r'(data-count=")(\d+)(">)(\d+)(</div><div class="stat-lbl">h-index</div>)',
        lambda m: f'{m.group(1)}{stats["hindex"]}{m.group(3)}{stats["hindex"]}{m.group(5)}',
        content,
    )
    content = re.sub(
        r'(data-count=")(\d+)(">)(\d+)(</div><div class="stat-lbl">i10-index</div>)',
        lambda m: f'{m.group(1)}{stats["i10index"]}{m.group(3)}{stats["i10index"]}{m.group(5)}',
        content,
    )

    with open("publications.html", "w") as f:
        f.write(content)
    print(
        f"publications.html: {pub_display} pubs, {stats['citations']} citations, "
        f"h-index {stats['hindex']}, i10-index {stats['i10index']}"
    )


def update_about_html(stats):
    with open("about.html", "r") as f:
        content = f.read()

    pub_display = f"{stats['publications']}+"

    content = re.sub(
        r'(<div class="stat-item reveal"><div class="stat-num">)(\d+\+?)(</div><div class="stat-label">Publications</div></div>)',
        lambda m: f"{m.group(1)}{pub_display}{m.group(3)}",
        content,
    )

    with open("about.html", "w") as f:
        f.write(content)
    print(f"about.html: {pub_display} publications")


if __name__ == "__main__":
    try:
        stats = fetch_stats()
        print(f"Fetched from Google Scholar: {stats}")
        update_publications_html(stats)
        update_about_html(stats)
    except Exception as e:
        print(f"Error fetching stats: {e}", file=sys.stderr)
        sys.exit(1)
