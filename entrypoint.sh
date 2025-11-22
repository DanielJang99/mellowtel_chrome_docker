#!/bin/bash
set -e

echo "========================================"
echo "Starting Xvfb Virtual Display"
echo "========================================"
export DISPLAY=:99
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!
echo "[INFO] Xvfb started on display :99 (PID: $XVFB_PID)"

sleep 2

# Generate timestamp for this run
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="/app/output"
SPEEDTEST_FILE="${OUTPUT_DIR}/speedtest_${TIMESTAMP}.json"

# Ensure output directory exists
mkdir -p "${OUTPUT_DIR}"

echo "========================================"
echo "Running Network Speed Test"
echo "========================================"
echo "Timestamp: ${TIMESTAMP}"
echo "Output: ${SPEEDTEST_FILE}"
echo ""

# Run speedtest and save results in JSON format
if command -v speedtest-cli &> /dev/null; then
    echo "[INFO] Running speedtest-cli..."

    # Run speedtest with JSON output and save
    speedtest-cli --json > "${SPEEDTEST_FILE}" 2>&1 || {
        echo "[WARNING] speedtest-cli failed, saving error to file"
        echo "{\"error\": \"speedtest-cli failed\", \"timestamp\": \"${TIMESTAMP}\"}" > "${SPEEDTEST_FILE}"
    }

    # Parse and display key metrics if speedtest succeeded
    if [ -f "${SPEEDTEST_FILE}" ] && grep -q "download" "${SPEEDTEST_FILE}"; then
        echo ""
        echo "[SUCCESS] Speed test completed!"

        # Extract key metrics using python
        python3 -c "
import json
import sys
try:
    with open('${SPEEDTEST_FILE}', 'r') as f:
        data = json.load(f)

    download_mbps = data.get('download', 0) / 1_000_000
    upload_mbps = data.get('upload', 0) / 1_000_000
    ping = data.get('ping', 0)
    server = data.get('server', {}).get('sponsor', 'Unknown')
    location = data.get('server', {}).get('name', 'Unknown')

    print(f'  Server: {server} ({location})')
    print(f'  Ping: {ping:.2f} ms')
    print(f'  Download: {download_mbps:.2f} Mbps')
    print(f'  Upload: {upload_mbps:.2f} Mbps')
except Exception as e:
    print(f'  [WARNING] Could not parse speedtest results: {e}', file=sys.stderr)
" || echo "  [WARNING] Could not display speedtest metrics"
    else
        echo "[WARNING] Speed test did not complete successfully"
    fi

    echo ""
    echo "[INFO] Speedtest results saved to: ${SPEEDTEST_FILE}"
else
    echo "[WARNING] speedtest-cli not found, skipping speed test"
    echo "{\"error\": \"speedtest-cli not installed\", \"timestamp\": \"${TIMESTAMP}\"}" > "${SPEEDTEST_FILE}"
fi

echo ""
echo "========================================"
echo "Starting Mellowtel Analysis Experiment"
echo "========================================"
echo ""

# Run the main experiment
exec python3 run_experiment.py "$@"
