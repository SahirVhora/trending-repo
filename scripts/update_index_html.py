#!/usr/bin/env python3
"""Fetch fresh trending data and bake it into index.html.

Strips em dashes from scraped descriptions and saves a JSON snapshot
for historical trend tracking alongside the HTML update.
"""

import datetime
import json
import pathlib
import re
import subprocess
import sys


BASE_DIR = pathlib.Path(__file__).parent.parent.resolve()
INDEX_PATH = BASE_DIR / "index.html"
SITEMAP_PATH = BASE_DIR / "sitemap.xml"
FETCH_SCRIPT = BASE_DIR / "fetch_trending.py"
DATA_DIR = BASE_DIR / "data"


def sanitize(value: str) -> str:
    """Strip em dashes, en dashes from strings to keep files consistent."""
    return value.replace("\u2014", "-").replace("\u2013", "-")


def fetch_json() -> list[dict]:
    """Run fetch_trending.py --json and return the repo list."""
    result = subprocess.run(
        [sys.executable, str(FETCH_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"fetch_trending.py failed: {result.stderr}")
    repos = json.loads(result.stdout)
    if not isinstance(repos, list):
        raise RuntimeError("Expected JSON array from fetch_trending.py")
    return repos


def format_repos_js(repos: list[dict]) -> str:
    """Format a list of repos as a JavaScript array literal."""
    lines = ["    var DEFAULT_REPOS = ["]
    for r in repos:
        entry = json.dumps(r, ensure_ascii=False)
        lines.append("      " + entry + ",")
    lines.append("    ];")
    return "\n".join(lines)


def update_index_html(repos: list[dict]) -> bool:
    """Replace DEFAULT_REPOS in index.html with fresh data. Returns True if changed."""
    content = INDEX_PATH.read_text(encoding="utf-8")

    today = datetime.date.today().isoformat()

    # Find and replace the DEFAULT_REPOS array
    start_marker = "    var DEFAULT_REPOS = ["
    end_marker = "    ];"
    start_idx = content.find(start_marker)
    if start_idx == -1:
        raise RuntimeError("Could not find DEFAULT_REPOS start marker in index.html")
    end_idx = content.find(end_marker, start_idx + len(start_marker))
    if end_idx == -1:
        raise RuntimeError("Could not find DEFAULT_REPOS end marker in index.html")
    new_js = format_repos_js(repos)
    new_content = content[:start_idx] + new_js + content[end_idx + len(end_marker):]

    # Update date strings
    new_content = re.sub(
        r"Data from \d{4}-\d{2}-\d{2}",
        f"Data from {today}",
        new_content,
    )

    if new_content == content:
        print("No changes needed - data is already up to date.")
        return False

    INDEX_PATH.write_text(new_content, encoding="utf-8")
    print(f"Updated {INDEX_PATH} with {len(repos)} repos from {today}.")
    return True


def update_sitemap(today: str) -> bool:
    """Update sitemap lastmod to match the baked-in dashboard date."""
    if not SITEMAP_PATH.exists():
        return False
    content = SITEMAP_PATH.read_text(encoding="utf-8")
    new_content = re.sub(
        r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>",
        f"<lastmod>{today}</lastmod>",
        content,
    )
    if new_content == content:
        return False
    SITEMAP_PATH.write_text(new_content, encoding="utf-8")
    print(f"Updated {SITEMAP_PATH} lastmod to {today}.")
    return True


def save_snapshot(repos: list[dict]) -> pathlib.Path:
    """Save a date-stamped JSON snapshot for trend tracking."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    filepath = DATA_DIR / f"trending_{today}.json"

    snapshot = {
        "meta": {
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "since": "daily",
            "language": "all",
            "count": len(repos),
        },
        "repositories": repos,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    print(f"Snapshot saved: {filepath}")
    return filepath


def main() -> int:
    try:
        repos = fetch_json()
    except Exception as e:
        print(f"Fetch failed, skipping update: {e}", file=sys.stderr)
        return 0  # Don't fail CI; just skip

    if not repos:
        print("No repos fetched, skipping update.")
        return 0

    # Sanitize all string fields to strip em dashes / en dashes
    for r in repos:
        for k, v in r.items():
            if isinstance(v, str):
                r[k] = sanitize(v)

    try:
        changed = update_index_html(repos)
        update_sitemap(datetime.date.today().isoformat())
    except Exception as e:
        print(f"Update failed: {e}", file=sys.stderr)
        return 1

    # Always save a snapshot for historical tracking
    try:
        save_snapshot(repos)
    except Exception as e:
        print(f"Snapshot save failed (non-fatal): {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
