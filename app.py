#!/usr/bin/env python3
"""Flask web UI for GitHub Trending repositories."""

import csv
import datetime
import io
import json
import os
import pathlib
import re
from typing import Any

from flask import Flask, render_template, jsonify, request, Response

from fetch_trending import (
    fetch_trending,
    _save_snapshot,
    _load_snapshot,
    _compare_snapshots,
    _generate_markdown,
    _find_latest_snapshots,
    _fmt_date,
    _parse_stars,
)

app = Flask(__name__)

BASE_DIR = pathlib.Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"

_CACHE: dict[str, tuple[list[dict], float]] = {}
_CACHE_TTL = 900  # 15 minutes



SAHIR_FIT_LANES = {
    "hermes-agent": ["agent", "agents", "automation", "browser", "workflow", "cli", "llm", "mcp", "ai"],
    "sap": ["sap", "successfactors", "odata", "erp", "hr", "employee", "workflow"],
    "education": ["education", "learning", "quiz", "worksheet", "school", "tutor", "practice", "curriculum"],
    "property": ["property", "mortgage", "house", "home", "real estate", "map", "planning", "solihull"],
    "document-tools": ["pdf", "document", "ocr", "forms", "invoice", "scan", "parser", "extraction"],
}

SAHIR_FIT_LANGUAGE_BOOSTS = {
    "python": 10,
    "javascript": 8,
    "typescript": 8,
    "html": 6,
    "shell": 5,
}


def _sahir_fit(repo: dict) -> dict[str, Any]:
    """Rank a repo against Sahir's active build lanes."""
    text = " ".join([
        repo.get("name", ""),
        repo.get("description", ""),
        repo.get("language", ""),
    ]).lower()
    lane_scores: dict[str, int] = {}
    for lane, words in SAHIR_FIT_LANES.items():
        lane_scores[lane] = sum(18 for word in words if word in text)
    language = str(repo.get("language", "")).lower()
    language_boost = SAHIR_FIT_LANGUAGE_BOOSTS.get(language, 0)
    star_boost = min(20, _parse_stars(repo.get("stars_today", "0")) // 50)
    lane, lane_score = max(lane_scores.items(), key=lambda item: item[1])
    score = min(100, lane_score + language_boost + star_boost)
    if score < 20:
        lane = "ignore"
    priority = "high" if score >= 70 else "medium" if score >= 40 else "low" if score >= 20 else "ignore"
    return {"score": score, "lane": lane, "priority": priority}


def _add_sahir_fit(repos: list[dict]) -> list[dict]:
    """Return repos with fit_for_sahir metadata attached."""
    enriched = []
    for repo in repos:
        copy = dict(repo)
        copy["fit_for_sahir"] = _sahir_fit(copy)
        enriched.append(copy)
    return enriched


def _get_trending_cached(since: str, language: str) -> list[dict]:
    """Fetch trending repos with a 15-minute in-memory cache."""
    key = f"{since}:{language}"
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    if key in _CACHE:
        repos, ts = _CACHE[key]
        if now - ts < _CACHE_TTL:
            return list(repos)
    repos = _add_sahir_fit(fetch_trending(since=since, language=language))
    _CACHE[key] = (repos, now)
    return list(repos)


def _cache_age(since: str, language: str) -> int | None:
    """Return cache age in seconds, or None if not cached."""
    key = f"{since}:{language}"
    if key not in _CACHE:
        return None
    _, ts = _CACHE[key]
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp() - ts)


def _compute_stats(repos: list[dict]) -> dict[str, Any]:
    """Compute aggregated stats from a list of repos."""
    lang_counts: dict[str, int] = {}
    for r in repos:
        lang = r.get("language", "Unknown")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    top = sorted(
        repos,
        key=lambda r: _parse_stars(r.get("total_stars", "0")),
        reverse=True,
    )[:5]
    return {
        "total_repos": len(repos),
        "language_counts": lang_counts,
        "top_starred": [
            {
                "name": r["name"],
                "stars": r.get("total_stars", "0"),
                "url": r.get("url", ""),
            }
            for r in top
        ],
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def _safe_path(base: pathlib.Path, name: str) -> pathlib.Path | None:
    """Resolve a filename under base and verify it stays within base."""
    try:
        target = (base / name).resolve()
        if target.is_relative_to(base):
            return target
    except (ValueError, RuntimeError):
        pass
    return None


def _markdown_to_html(md: str) -> str:
    """Minimal markdown-to-HTML converter for tables and headers."""
    text = md
    # Headers
    text = re.sub(r"^#{6}\s+(.+)$", r"<h6>\1</h6>", text, flags=re.MULTILINE)
    text = re.sub(r"^#{5}\s+(.+)$", r"<h5>\1</h5>", text, flags=re.MULTILINE)
    text = re.sub(r"^#{4}\s+(.+)$", r"<h4>\1</h4>", text, flags=re.MULTILINE)
    text = re.sub(r"^#{3}\s+(.+)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^#{2}\s+(.+)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^#\s+(.+)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    # Process block by block
    blocks = []
    for block in text.split("\n\n"):
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("<"):
            blocks.append(stripped)
        elif "|" in stripped and "---" in stripped and all("|" in ln for ln in stripped.splitlines() if ln.strip()):
            # Markdown table block
            lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
            if len(lines) >= 2:
                line = lines[0].strip().strip("|")
                cells = [c.strip() for c in line.split("|")]
                thead = "<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>"
                tbody = ""
                for ln in lines[2:]:
                    line = ln.strip().strip("|")
                    cells = [c.strip() for c in line.split("|")]
                    tbody += "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
                blocks.append(f'<table style="width:100%;border-collapse:collapse;margin:1rem 0;"><thead style="border-bottom:2px solid var(--border);">{thead}</thead><tbody>{tbody}</tbody></table>')
        else:
            blocks.append(f"<p>{stripped}</p>")
    return "\n\n".join(blocks)


def _list_snapshots() -> list[dict[str, Any]]:
    """List all snapshot files with their meta info."""
    snapshots = []
    for p in sorted(DATA_DIR.glob("trending_*.json"), reverse=True):
        try:
            meta, _ = _load_snapshot(p)
            snapshots.append({
                "filename": p.name,
                "date": _fmt_date(meta.get("fetched_at", "")),
                "language": meta.get("language", "all"),
                "count": meta.get("count", 0),
                "since": meta.get("since", "daily"),
            })
        except Exception:
            continue
    return snapshots


def _list_reports() -> list[dict[str, str]]:
    """List all generated Markdown reports."""
    reports = []
    for p in sorted(REPORTS_DIR.glob("trending_*.md"), reverse=True):
        reports.append({
            "filename": p.name,
            "date": p.stem.replace("trending_", ""),
        })
    return reports


@app.route("/")
def dashboard():
    """Show today's trending repositories."""
    since = request.args.get("since", "daily")
    lang = request.args.get("lang", "")
    try:
        repos = _get_trending_cached(since=since, language=lang)
    except Exception as e:
        return render_template(
            "dashboard.html",
            repos=[],
            since=since,
            lang=lang,
            error=f"Failed to fetch trending repos: {e}",
        )
    return render_template(
        "dashboard.html",
        repos=repos,
        since=since,
        lang=lang,
        error="",
        cache_age=_cache_age(since, lang),
    )


@app.route("/trend")
def trend():
    """Compare the two most recent snapshots."""
    pair = _find_latest_snapshots(DATA_DIR)
    if pair is None:
        return render_template(
            "trend.html",
            error="Need at least two snapshots to compare. Run a few daily fetches first.",
            entered=[],
            left=[],
            stayed=[],
            old_date="",
            new_date="",
        )
    old_path, new_path = pair
    results = _compare_snapshots(old_path, new_path)
    return render_template(
        "trend.html",
        error="",
        entered=results["entered"],
        left=results["left"],
        stayed=results["stayed"],
        old_date=_fmt_date(results["old_meta"].get("fetched_at", "")),
        new_date=_fmt_date(results["new_meta"].get("fetched_at", "")),
    )


@app.route("/history")
def history():
    """List all saved snapshots."""
    snapshots = _list_snapshots()
    return render_template("history.html", snapshots=snapshots)


@app.route("/compare/<old_file>/<new_file>")
def compare(old_file: str, new_file: str):
    """Compare two specific snapshots."""
    old_path = _safe_path(DATA_DIR, old_file)
    new_path = _safe_path(DATA_DIR, new_file)
    if old_path is None or new_path is None or not old_path.exists() or not new_path.exists():
        return render_template(
            "trend.html",
            error="One or both snapshot files not found.",
            entered=[],
            left=[],
            stayed=[],
            old_date="",
            new_date="",
        )
    results = _compare_snapshots(old_path, new_path)
    return render_template(
        "trend.html",
        error="",
        entered=results["entered"],
        left=results["left"],
        stayed=results["stayed"],
        old_date=_fmt_date(results["old_meta"].get("fetched_at", "")),
        new_date=_fmt_date(results["new_meta"].get("fetched_at", "")),
    )


@app.route("/reports")
def reports():
    """List all generated Markdown reports."""
    reports_list = _list_reports()
    return render_template("reports.html", reports=reports_list)


@app.route("/report/<filename>")
def view_report(filename: str):
    """View a specific Markdown report."""
    report_path = _safe_path(REPORTS_DIR, filename)
    if report_path is None or not report_path.exists():
        return "Report not found", 404
    content = report_path.read_text(encoding="utf-8")
    html_content = _markdown_to_html(content)
    return render_template("report_view.html", content=html_content, filename=filename)


@app.route("/api/fetch")
def api_fetch():
    """JSON API: fetch trending repos."""
    since = request.args.get("since", "daily")
    lang = request.args.get("lang", "")
    try:
        repos = _get_trending_cached(since=since, language=lang)
    except Exception as e:
        return jsonify({"error": str(e)}), 503
    return jsonify(repos)


@app.route("/api/snapshot")
def api_snapshot():
    """JSON API: view a single snapshot."""
    filename = request.args.get("file", "")
    path = _safe_path(DATA_DIR, filename)
    if path is None or not path.exists():
        return jsonify({"error": "Snapshot not found"}), 404
    meta, repos = _load_snapshot(path)
    return jsonify({"meta": meta, "repositories": repos})


@app.route("/api/snapshots")
def api_snapshots():
    """JSON API: list snapshots."""
    return jsonify(_list_snapshots())


@app.route("/api/compare")
def api_compare():
    """JSON API: compare two snapshots."""
    old_file = request.args.get("old")
    new_file = request.args.get("new")
    if not old_file or not new_file:
        return jsonify({"error": "Missing old or new parameter"}), 400
    old_path = _safe_path(DATA_DIR, old_file)
    new_path = _safe_path(DATA_DIR, new_file)
    if old_path is None or new_path is None or not old_path.exists() or not new_path.exists():
        return jsonify({"error": "Snapshot not found"}), 404
    results = _compare_snapshots(old_path, new_path)
    return jsonify({
        "old_date": _fmt_date(results["old_meta"].get("fetched_at", "")),
        "new_date": _fmt_date(results["new_meta"].get("fetched_at", "")),
        "entered": results["entered"],
        "left": results["left"],
        "stayed": results["stayed"],
    })


@app.route("/api/stats")
def api_stats():
    """JSON API: aggregated stats for trending repos."""
    since = request.args.get("since", "daily")
    lang = request.args.get("lang", "")
    try:
        repos = _get_trending_cached(since=since, language=lang)
    except Exception as e:
        return jsonify({"error": str(e)}), 503
    return jsonify(_compute_stats(repos))


@app.route("/api/auto-save", methods=["POST"])
def api_auto_save():
    """Save a snapshot if one for today does not already exist."""
    since = request.json.get("since", "daily") if request.json else "daily"
    lang = request.json.get("lang", "") if request.json else ""
    today = datetime.date.today().isoformat()
    filename = f"trending_{today}.json"
    if lang:
        filename = f"trending_{lang}_{today}.json"
    filepath = DATA_DIR / filename
    if filepath.exists():
        try:
            meta, repos = _load_snapshot(filepath)
            return jsonify({"saved": str(filepath), "count": meta.get("count", 0), "skipped": True})
        except Exception:
            pass  # fall through to re-fetch and overwrite
    try:
        repos = _get_trending_cached(since=since, language=lang)
    except Exception as e:
        return jsonify({"error": str(e)}), 503
    path = _save_snapshot(repos, DATA_DIR, since, lang)
    return jsonify({"saved": str(path), "count": len(repos), "skipped": False})


@app.route("/repo/<path:repo_name>")
def repo_detail(repo_name: str):
    """Show details for a single repository from the current cache."""
    since = request.args.get("since", "daily")
    lang = request.args.get("lang", "")
    try:
        repos = _get_trending_cached(since=since, language=lang)
    except Exception as e:
        return render_template(
            "repo_detail.html",
            repo=None,
            error=f"Failed to fetch trending repos: {e}",
        )
    repo = next((r for r in repos if r["name"] == repo_name), None)
    if repo is None:
        return render_template(
            "repo_detail.html",
            repo=None,
            error=f"Repository '{repo_name}' not found in current trending list.",
        )
    rank = next((i + 1 for i, r in enumerate(repos) if r["name"] == repo_name), None)
    return render_template(
        "repo_detail.html",
        repo=repo,
        rank=rank,
        total=len(repos),
        error="",
    )


@app.route("/api/export/csv")
def api_export_csv():
    """Export current trending repos as CSV."""
    since = request.args.get("since", "daily")
    lang = request.args.get("lang", "")
    try:
        repos = _get_trending_cached(since=since, language=lang)
    except Exception as e:
        return jsonify({"error": str(e)}), 503
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Rank", "Name", "Language", "Stars Today", "Total Stars", "Fit Lane", "Fit Score", "Fit Priority", "Description", "URL"])
    for i, r in enumerate(repos, start=1):
        writer.writerow([
            i,
            r.get("name", ""),
            r.get("language", ""),
            r.get("stars_today", ""),
            r.get("total_stars", ""),
            r.get("fit_for_sahir", {}).get("lane", ""),
            r.get("fit_for_sahir", {}).get("score", ""),
            r.get("fit_for_sahir", {}).get("priority", ""),
            r.get("description", ""),
            r.get("url", ""),
        ])
    safe_since = re.sub(r'[^\w\-]', '_', since)
    safe_lang = re.sub(r'[^\w\-]', '_', lang or 'all')
    filename = f"trending_{safe_since}_{safe_lang}_{datetime.date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/save", methods=["POST"])
def api_save():
    """JSON API: save a snapshot of current trending repos."""
    since = request.json.get("since", "daily") if request.json else "daily"
    lang = request.json.get("lang", "") if request.json else ""
    try:
        repos = _get_trending_cached(since=since, language=lang)
    except Exception as e:
        return jsonify({"error": str(e)}), 503
    path = _save_snapshot(repos, DATA_DIR, since, lang)
    return jsonify({"saved": str(path), "count": len(repos)})


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG") == "1"
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.run(debug=debug, host=host, port=port)
