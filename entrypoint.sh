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
TIMEOUT=60
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
    echo "[INFO] Running speedtest-cli with ${TIMEOUT} second timeout..."

    # Run speedtest with JSON output and save (with generous timeout)
    timeout ${TIMEOUT} speedtest-cli --secure --json > "${SPEEDTEST_FILE}" 2>&1 || {
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 124 ]; then
            echo "[WARNING] speedtest-cli timed out after ${TIMEOUT} seconds"
            echo "{\"error\": \"timeout after ${TIMEOUT} seconds\", \"timestamp\": \"${TIMESTAMP}\"}" > "${SPEEDTEST_FILE}"
        else
            echo "[WARNING] speedtest-cli failed with exit code $EXIT_CODE"
            echo "{\"error\": \"speedtest-cli failed\", \"exit_code\": $EXIT_CODE, \"timestamp\": \"${TIMESTAMP}\"}" > "${SPEEDTEST_FILE}"
        fi
    }

    echo ""
    echo "[INFO] Speedtest file contents:"
    echo "----------------------------------------"
    cat "${SPEEDTEST_FILE}" || echo "[ERROR] Could not read speedtest file"
    echo ""
    echo "----------------------------------------"
fi

echo ""
echo "========================================"
echo "Running TCP RTT Measurement"
echo "========================================"
NPING_FILE="${OUTPUT_DIR}/nping_${TIMESTAMP}.txt"
echo "Target: request.mellow.tel"
echo "Output: ${NPING_FILE}"
echo ""

# Run nping to measure TCP RTT
if command -v nping &> /dev/null; then
    echo "[INFO] Running nping TCP measurement (10 packets)..."
    nping --tcp -c 10 -p 80 request.mellow.tel > "${NPING_FILE}" 2>&1 || {
        EXIT_CODE=$?
        echo "[WARNING] nping failed with exit code $EXIT_CODE"
    }

    echo ""
    echo "[INFO] Nping results:"
    echo "----------------------------------------"
    cat "${NPING_FILE}" || echo "[ERROR] Could not read nping file"
    echo ""
    echo "----------------------------------------"
else
    echo "[WARNING] nping command not found, skipping TCP RTT measurement"
fi

echo ""
echo "========================================"
echo "Starting Mellowtel Analysis Experiment"
echo "========================================"
echo ""

# Run the main experiment
exec python3 run_experiment.py "$@"
