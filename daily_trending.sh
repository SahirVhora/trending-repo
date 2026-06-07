#!/usr/bin/env bash
# Daily GitHub Trending fetch + comparison report
#
# Usage: ./daily_trending.sh
# Install in crontab:
#   0 9 * * * /home/sahirvhora/projects/sapsf/experiments/daily_trending.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FETCH_SCRIPT="${SCRIPT_DIR}/fetch_trending.py"
DATA_DIR="${SCRIPT_DIR}/data"
REPORTS_DIR="${SCRIPT_DIR}/reports"
LOG_FILE="${SCRIPT_DIR}/daily_trending.log"

# Ensure directories exist
mkdir -p "${DATA_DIR}" "${REPORTS_DIR}"

log() {
    echo "[$(date -Iseconds)] $*" | tee -a "${LOG_FILE}"
}

log "Starting daily trending fetch..."

# Fetch today's trending repos and save snapshot
if python3 "${FETCH_SCRIPT}" --save --quiet --data-dir "${DATA_DIR}"; then
    log "Snapshot saved successfully."
else
    log "ERROR: Failed to fetch trending repos."
    exit 1
fi

# Count how many snapshots we have
SNAP_COUNT=$(find "${DATA_DIR}" -maxdepth 1 -name 'trending_*.json' | wc -l)

if [ "${SNAP_COUNT}" -ge 2 ]; then
    REPORT_FILE="${REPORTS_DIR}/trending_$(date +%Y-%m-%d).md"
    log "Generating comparison report -> ${REPORT_FILE}"

    if python3 "${FETCH_SCRIPT}" \
        --trend \
        --data-dir "${DATA_DIR}" \
        --markdown \
        --output "${REPORT_FILE}"; then
        log "Report generated successfully."
    else
        log "ERROR: Failed to generate comparison report."
        exit 1
    fi
else
    log "Only ${SNAP_COUNT} snapshot(s) available. Need 2+ for comparison."
fi

log "Daily run complete."
