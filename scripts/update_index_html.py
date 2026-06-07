#!/usr/bin/env python3
"""Fetch fresh trending data and bake it into index.html."""

import datetime
import json
import pathlib
import re
import subprocess
import sys


BASE_DIR = pathlib.Path(__file__).parent.parent.resolve()
INDEX_PATH = BASE_DIR / "index.html"
FETCH_SCRIPT = BASE_DIR / "fetch_trending.py"


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
    # Use a more specific anchor to avoid matching ]; inside strings
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
        print("No changes needed — data is already up to date.")
        return False

    INDEX_PATH.write_text(new_content, encoding="utf-8")
    print(f"Updated {INDEX_PATH} with {len(repos)} repos from {today}.")
    return True


def main() -> int:
    try:
        repos = fetch_json()
    except Exception as e:
        print(f"Fetch failed, skipping update: {e}", file=sys.stderr)
        return 0  # Don't fail CI; just skip

    if not repos:
        print("No repos fetched, skipping update.")
        return 0

    try:
        changed = update_index_html(repos)
    except Exception as e:
        print(f"Update failed: {e}", file=sys.stderr)
        return 1

    return 0 if changed or not changed else 0


if __name__ == "__main__":
    sys.exit(main())
