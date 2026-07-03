# 🔥 GitHub Trending Dashboard - Daily Trending Repositories & Analytics

A beautiful, interactive dashboard for exploring [GitHub's trending repositories](https://sahirvhora.github.io/trending-repo/). Track top starred open-source projects daily, weekly, or monthly with live search, sortable columns, interactive charts, CSV export, dark/light themes, and snapshot comparison - all in a clean web UI.

![GitHub Trending Dashboard](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## ✨ Features

- **Real-time Scraping** - Fetches today's trending repos directly from GitHub
- **Interactive Dashboard** - Search, sort, paginate through repos with live charts
- **Dark / Light Theme** - Toggle between themes with localStorage persistence
- **Snapshot System** - Save daily JSON snapshots and compare them over time
- **Trend Analysis** - See which repos entered, left, or stayed in trending
- **CSV Export** - Download the current view as a CSV file
- **Standalone HTML** - `index.html` works in any browser with zero setup
- **Flask API** - JSON endpoints for programmatic access
- **SEO Optimized** - Meta tags, structured data, sitemap, and Open Graph for social sharing

---

## 🚀 Quick Start

### Option 1: Single HTML File (Zero Setup)

1. Open [`index.html`](index.html) in any modern browser
2. The latest snapshot is already baked in - no server needed
3. Use the search box, sortable table, charts, theme toggle, and CSV export directly in the page

> 💡 **For non-technical users:** Just double-click `index.html`. It works offline.  
> 🌐 **Or enable GitHub Pages** (see below) and share the URL - no downloads needed!

### Option 2: Flask Server (Full Features)

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python app.py

# Open http://localhost:5000 in your browser
```

---

## 📦 Project Structure

```
.
├── app.py                 # Flask web server
├── fetch_trending.py      # GitHub scraper + snapshot tools
├── index.html             # Standalone client-side dashboard
├── daily_trending.sh      # Cron script for daily snapshots
├── requirements.txt       # Python dependencies
├── data/                  # Saved JSON snapshots
├── reports/               # Generated Markdown reports
└── templates/             # Jinja2 HTML templates
```

---

## 🔧 Command Line Usage

```bash
# Fetch and print today's trending repos
python fetch_trending.py

# Save a snapshot
python fetch_trending.py --save

# Filter by language
python fetch_trending.py --lang python

# Weekly trending
python fetch_trending.py --since weekly

# Compare two snapshots
python fetch_trending.py --compare data/trending_2026-06-06.json data/trending_2026-06-07.json

# Auto-compare the two most recent snapshots
python fetch_trending.py --trend --markdown --output reports/trending_report.md
```

---

## 🌐 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/api/fetch` | GET | JSON list of trending repos |
| `/api/stats` | GET | Aggregated stats (top starred, language counts) |
| `/api/export/csv` | GET | Download CSV export |
| `/api/save` | POST | Save a snapshot |
| `/api/auto-save` | POST | Save only if today's snapshot doesn't exist |
| `/api/snapshots` | GET | List all saved snapshots |
| `/api/compare` | GET | Compare two snapshots (JSON) |

---

## 🗓️ Daily Cron Job

Add to your crontab to auto-fetch and compare daily:

```bash
# Every day at 9 AM
0 9 * * * /path/to/daily_trending.sh
```

---

## 🌐 GitHub Pages (Share with Anyone)

The public site is deployed by GitHub Actions to avoid exposing server-side source files on GitHub Pages. Only the static dashboard assets are published.

Live site: [https://sahirvhora.github.io/trending-repo/](https://sahirvhora.github.io/trending-repo/)

Required repository settings:

1. Go to **Settings → Pages**
2. Set **Build and deployment → Source** to **GitHub Actions**
3. Go to **Settings → Actions → General → Workflow permissions**
4. Select **Read and write permissions** so the scheduled update workflow can commit fresh snapshots

Published files are built by `scripts/build_pages_artifact.sh` into `dist/`. The artifact intentionally includes only:

- `index.html`
- `favicon.svg`
- `preview.png`
- `robots.txt`
- `sitemap.xml`
- `data/*.json` snapshots
- `.nojekyll`

## 📝 Updating the Standalone HTML

The `index.html` includes a baked-in dataset. To update it with fresh data and refresh the sitemap date:

```bash
python scripts/update_index_html.py
```

The scheduled GitHub Actions workflow runs this every 3 hours, commits changes when data shifts, then deploys the curated Pages artifact.

---

## 🧪 Development

```bash
# Run the Flask dev server on http://127.0.0.1:5000
python app.py

# Enable debug mode
FLASK_DEBUG=1 python app.py

# Optional: expose on a different host/port
FLASK_HOST=0.0.0.0 FLASK_PORT=5000 python app.py
```

---

## 📄 License

MIT License - feel free to use, modify, and share!

---

Made with ❤️ for the open-source community.
