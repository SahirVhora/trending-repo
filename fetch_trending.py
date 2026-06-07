#!/usr/bin/env python3
"""
Fetch and display trending GitHub repositories.

Usage:
    python fetch_trending.py
    python fetch_trending.py --since weekly
    python fetch_trending.py --lang python
    python fetch_trending.py --json
"""

import argparse
import datetime
import glob
import html
import json
import pathlib
import re
import shutil
import sys
import urllib.request
from urllib.error import HTTPError, URLError


def fetch_trending(since: str = "daily", language: str = "") -> list[dict]:
    """Fetch trending repositories from GitHub."""
    url = "https://github.com/trending"
    if language:
        url += f"/{language}"
    url += f"?since={since}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
    }

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8")
    except HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"URL error: {e.reason}", file=sys.stderr)
        sys.exit(1)

    return _parse_repos(html)


def _parse_repos(html: str) -> list[dict]:
    """Parse repository data from GitHub trending HTML."""
    repos = []

    # Split by article.Box-row to isolate each repo card
    cards = re.split(r'<article[^>]*class="Box-row"[^>]*>', html)[1:]

    for card in cards:
        # Close the card at the next </article> or end
        card = card.split("</article>")[0]

        # Repo full name: inside h2 > a
        name_match = re.search(
            r'<h2[^>]*class="h3 lh-condensed"[^>]*>.*?<a[^>]*href="/([^"]+)"[^>]*>.*?<span[^>]*class="text-normal"[^>]*>(.*?)</span>(.*?)</a>',
            card,
            re.DOTALL,
        )
        if not name_match:
            continue

        full_name = name_match.group(1).strip()
        # Clean up any stray whitespace or newlines in the name
        full_name = re.sub(r"\s+", "", full_name)

        # Description
        desc_match = re.search(
            r'<p[^>]*class="col-9[^"]*"[^>]*>(.*?)</p>',
            card,
            re.DOTALL,
        )
        description = _clean_html(desc_match.group(1)) if desc_match else ""

        # Language
        lang_match = re.search(
            r'<span[^>]*itemprop="programmingLanguage"[^>]*>(.*?)</span>',
            card,
        )
        language = lang_match.group(1).strip() if lang_match else "Unknown"

        # Total stars
        total_stars_match = re.search(
            r'<a[^>]*href="/' + re.escape(full_name) + r'/stargazers"[^>]*>.*?([\d,]+)</a>',
            card,
            re.DOTALL,
        )
        total_stars = total_stars_match.group(1).strip() if total_stars_match else "0"

        # Stars today (trending metric)
        # GitHub shows this as text like "1,234 stars today"
        stars_today_match = re.search(
            r'([\d,]+)\s+stars?\s+today',
            card,
        )
        stars_today = stars_today_match.group(1).strip() if stars_today_match else "0"

        repos.append({
            "name": full_name,
            "description": description,
            "language": language,
            "stars_today": stars_today,
            "total_stars": total_stars,
            "url": f"https://github.com/{full_name}",
        })

    return repos


def _clean_html(raw: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _load_snapshot(path: pathlib.Path) -> tuple[dict, list[dict]]:
    """Load a snapshot file and return its meta + repos."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    meta = data.get("meta", {})
    repos = data.get("repositories", [])
    return meta, repos


def _parse_stars(stars_str: str) -> int:
    """Parse a star count string like '1,234' into an integer."""
    s = str(stars_str).replace(",", "").strip()
    if s.endswith("k"):
        return int(float(s[:-1]) * 1000)
    if s.endswith("M"):
        return int(float(s[:-1]) * 1_000_000)
    try:
        return int(s)
    except ValueError:
        return 0


def _compare_snapshots(
    old_path: pathlib.Path,
    new_path: pathlib.Path,
) -> dict:
    """Compare two snapshots and return differences."""
    old_meta, old_repos = _load_snapshot(old_path)
    new_meta, new_repos = _load_snapshot(new_path)

    old_map = {r["name"]: r for r in old_repos}
    new_map = {r["name"]: r for r in new_repos}
    old_ranks = {r["name"]: i + 1 for i, r in enumerate(old_repos)}
    new_ranks = {r["name"]: i + 1 for i, r in enumerate(new_repos)}

    old_names = set(old_map.keys())
    new_names = set(new_map.keys())

    entered = [new_map[name] for name in sorted(new_names - old_names)]
    left = [old_map[name] for name in sorted(old_names - new_names)]

    stayed = []
    for name in sorted(old_names & new_names):
        old_r = old_map[name]
        new_r = new_map[name]
        old_stars = _parse_stars(old_r.get("total_stars", "0"))
        new_stars = _parse_stars(new_r.get("total_stars", "0"))
        stayed.append({
            "name": name,
            "language": new_r.get("language", "Unknown"),
            "old_stars": old_r.get("total_stars", "0"),
            "new_stars": new_r.get("total_stars", "0"),
            "delta": new_stars - old_stars,
            "old_rank": old_ranks[name],
            "new_rank": new_ranks[name],
        })

    return {
        "old_meta": old_meta,
        "new_meta": new_meta,
        "entered": entered,
        "left": left,
        "stayed": stayed,
    }


def _fmt_date(ts: str) -> str:
    """Format an ISO timestamp to YYYY-MM-DD."""
    try:
        return ts[:10]
    except Exception:
        return str(ts)


def _generate_markdown(results: dict) -> str:
    """Generate a Markdown report from comparison results."""
    old_meta = results["old_meta"]
    new_meta = results["new_meta"]

    old_date = _fmt_date(old_meta.get("fetched_at", "unknown"))
    new_date = _fmt_date(new_meta.get("fetched_at", "unknown"))

    lines = [
        "# GitHub Trending Comparison",
        "",
        f"| | Date |",
        f"|---|---|",
        f"| Old | {old_date} |",
        f"| New | {new_date} |",
        "",
    ]

    entered = results["entered"]
    left = results["left"]
    stayed = results["stayed"]

    if entered:
        lines.append(f"## 🆕 Entered trending ({len(entered)})")
        lines.append("")
        lines.append("| Repository | Language | Stars |")
        lines.append("|---|---|---|")
        for r in entered:
            lines.append(f"| {r['name']} | {r['language']} | {r['total_stars']} |")
        lines.append("")

    if left:
        lines.append(f"## ❌ Left trending ({len(left)})")
        lines.append("")
        lines.append("| Repository | Language | Stars |")
        lines.append("|---|---|---|")
        for r in left:
            lines.append(f"| {r['name']} | {r['language']} | {r['total_stars']} |")
        lines.append("")

    if stayed:
        lines.append(f"## 📊 Still trending ({len(stayed)})")
        lines.append("")
        lines.append("| Repository | Language | Old | New | Δ | Rank Δ |")
        lines.append("|---|---|---|---|---|---|")
        for s in stayed:
            rank_delta = s["new_rank"] - s["old_rank"]
            rank_str = f"{rank_delta:+d}" if rank_delta != 0 else "-"
            delta_str = f"{s['delta']:+d}" if s["delta"] != 0 else "-"
            lines.append(
                f"| {s['name']} | {s['language']} | "
                f"{s['old_stars']} | {s['new_stars']} | "
                f"{delta_str} | {rank_str} |"
            )
        lines.append("")

    lines.append(
        f"**Summary:** {len(entered)} entered, {len(left)} left, "
        f"{len(stayed)} stayed"
    )
    lines.append("")
    return "\n".join(lines)


def _find_latest_snapshots(data_dir: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path] | None:
    """Find the two most recent unfiltered snapshot files in the data directory."""
    # Only match plain date-stamped files (not language-filtered like trending_python_*.json)
    pattern = str(data_dir / "trending_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json")
    files = sorted(glob.glob(pattern), reverse=True)
    if len(files) < 2:
        return None
    return pathlib.Path(files[1]), pathlib.Path(files[0])


def _print_comparison(results: dict) -> None:
    """Print a human-readable comparison between two snapshots."""
    old_meta = results["old_meta"]
    new_meta = results["new_meta"]

    old_date = _fmt_date(old_meta.get("fetched_at", "unknown"))
    new_date = _fmt_date(new_meta.get("fetched_at", "unknown"))
    print(f"Comparing snapshots")
    print(f"  Old: {old_date}")
    print(f"  New: {new_date}")
    print()

    entered = results["entered"]
    left = results["left"]
    stayed = results["stayed"]

    if entered:
        print(f"🆕 Entered trending ({len(entered)})")
        for r in entered:
            print(f"   + {r['name']} ({r['language']}) - {r['total_stars']} stars")
        print()

    if left:
        print(f"❌ Left trending ({len(left)})")
        for r in left:
            print(f"   - {r['name']} ({r['language']}) - {r['total_stars']} stars")
        print()

    if stayed:
        print(f"📊 Still trending ({len(stayed)})")
        # Column widths
        name_width = max(len(s["name"]) for s in stayed)
        name_width = max(name_width, 10)
        header = (
            f"{'Repository':<{name_width}}  "
            f"{'Lang':<10}  "
            f"{'Old':>8}  "
            f"{'New':>8}  "
            f"{'Δ':>7}  "
            f"{'Rank Δ':>6}"
        )
        print(header)
        print("-" * len(header))
        for s in stayed:
            rank_delta = s["new_rank"] - s["old_rank"]
            rank_str = f"{rank_delta:+d}" if rank_delta != 0 else "-"
            delta_str = f"{s['delta']:+d}" if s["delta"] != 0 else "-"
            print(
                f"{s['name']:<{name_width}}  "
                f"{s['language']:<10}  "
                f"{s['old_stars']:>8}  "
                f"{s['new_stars']:>8}  "
                f"{delta_str:>7}  "
                f"{rank_str:>6}"
            )
        print()

    print(f"Summary: {len(entered)} entered, {len(left)} left, {len(stayed)} stayed")



def _save_snapshot(
    repos: list[dict],
    data_dir: pathlib.Path,
    since: str,
    lang: str,
) -> pathlib.Path:
    """Save a date-stamped JSON snapshot of the trending repos."""
    data_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    filename = f"trending_{today}.json"
    if lang:
        filename = f"trending_{lang}_{today}.json"
    filepath = data_dir / filename

    snapshot = {
        "meta": {
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "since": since,
            "language": lang or "all",
            "count": len(repos),
        },
        "repositories": repos,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    return filepath


def print_table(repos: list[dict]) -> None:
    """Print repos in a readable table format."""
    if not repos:
        print("No trending repositories found.", file=sys.stderr)
        return

    # Determine column widths
    name_width = max(len(r["name"]) for r in repos)
    name_width = max(name_width, 10)

    lang_width = max(len(r["language"]) for r in repos)
    lang_width = max(lang_width, 8)

    stars_width = max(len(r["stars_today"]) for r in repos)
    stars_width = max(stars_width, 5)

    total_width = max(len(r["total_stars"]) for r in repos)
    total_width = max(total_width, 5)

    header = (
        f"{'Repository':<{name_width}}  "
        f"{'Lang':<{lang_width}}  "
        f"{'Today':>{stars_width}}  "
        f"{'Total':>{total_width}}  "
        f"Description"
    )
    print(header)
    print("-" * len(header))

    for r in repos:
        desc = r["description"]
        # Truncate description to fit terminal
        term_width = shutil.get_terminal_size().columns
        avail = max(30, term_width - name_width - lang_width - stars_width - total_width - 10)
        if len(desc) > avail:
            desc = desc[: avail - 3] + "..."
        print(
            f"{r['name']:<{name_width}}  "
            f"{r['language']:<{lang_width}}  "
            f"{r['stars_today']:>{stars_width}}  "
            f"{r['total_stars']:>{total_width}}  "
            f"{desc}"
        )

    print(f"\nTotal: {len(repos)} repositories")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch trending GitHub repositories.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s\n"
            "  %(prog)s --since weekly --lang python\n"
            "  %(prog)s --json\n"
            "  %(prog)s --save --quiet        # cron-friendly daily fetch\n"
        "  %(prog)s --compare old.json new.json\n"
        "  %(prog)s --trend --markdown --output report.md"
        ),
    )
    parser.add_argument(
        "--since",
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="Time range for trending repos (default: daily)",
    )
    parser.add_argument(
        "--lang",
        default="",
        metavar="LANGUAGE",
        help="Filter by programming language (e.g., python, javascript, rust)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of a formatted table",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save a date-stamped JSON snapshot to the data directory",
    )
    parser.add_argument(
        "--data-dir",
        default="",
        metavar="PATH",
        help=(
            "Directory to store saved snapshots "
            "(default: <script-dir>/data)"
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress table/JSON output (useful with --save in cron)",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar="FILE",
        help="Compare two saved snapshot files (old new)",
    )
    parser.add_argument(
        "--trend",
        action="store_true",
        help="Auto-compare the two most recent snapshots in the data directory",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Output comparison as Markdown instead of terminal table",
    )
    parser.add_argument(
        "--output",
        default="",
        metavar="FILE",
        help="Write Markdown output to a file (used with --trend or --compare)",
    )
    args = parser.parse_args()

    # Resolve data_dir once for reuse
    if args.data_dir:
        data_dir = pathlib.Path(args.data_dir)
    else:
        script_dir = pathlib.Path(__file__).parent.resolve()
        data_dir = script_dir / "data"

    if args.compare or args.trend:
        if args.trend:
            pair = _find_latest_snapshots(data_dir)
            if pair is None:
                print(
                    "Need at least two snapshots to compare. "
                    "Run with --save a few times first.",
                    file=sys.stderr,
                )
                sys.exit(1)
            old_path, new_path = pair
        else:
            old_path = pathlib.Path(args.compare[0])
            new_path = pathlib.Path(args.compare[1])

        if not old_path.exists():
            print(f"Snapshot not found: {old_path}", file=sys.stderr)
            sys.exit(1)
        if not new_path.exists():
            print(f"Snapshot not found: {new_path}", file=sys.stderr)
            sys.exit(1)

        results = _compare_snapshots(old_path, new_path)

        if args.markdown or args.output:
            md = _generate_markdown(results)
            if args.output:
                out_path = pathlib.Path(args.output)
                out_path.write_text(md, encoding="utf-8")
                print(f"Markdown report written to {out_path}")
            else:
                print(md)
        else:
            _print_comparison(results)
        return

    repos = fetch_trending(since=args.since, language=args.lang)

    if args.save:
        saved_path = _save_snapshot(repos, data_dir, args.since, args.lang)
        if not args.quiet:
            print(f"Saved snapshot: {saved_path}", file=sys.stderr)

    if not args.quiet:
        if args.json:
            print(json.dumps(repos, indent=2))
        else:
            print_table(repos)


if __name__ == "__main__":
    main()
