#!/bin/bash
set -e

echo "========================================"
echo "Determining Client Network Information"
echo "========================================"
# Fetch public IP information and extract ASN and City
IP_INFO=$(curl -s --max-time 10 http://ip-api.com/json/ 2>/dev/null || echo "")

if [ -n "$IP_INFO" ] && echo "$IP_INFO" | grep -q "\"status\":\"success\""; then
    # Extract ASN (format: "AS15169 Google LLC" -> "AS15169")
    ASN=$(echo "$IP_INFO" | grep -o '"as":"[^"]*"' | cut -d'"' -f4 | awk '{print $1}')
    # Extract City
    CITY=$(echo "$IP_INFO" | grep -o '"city":"[^"]*"' | cut -d'"' -f4)

    # Replace spaces with underscores in city name
    CITY=$(echo "$CITY" | sed 's/ /_/g')

    # Set client_network variable
    if [ -n "$ASN" ] && [ -n "$CITY" ]; then
        client_network="${ASN}-${CITY}"
        echo "[INFO] Client Network: ${client_network}"
    else
        client_network="unknown"
        echo "[WARNING] Could not determine ASN or City, using 'unknown'"
    fi
else
    client_network="unknown"
    echo "[WARNING] Could not fetch IP information, using 'unknown'"
fi

export client_network
echo ""

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

echo ""
echo "========================================"
echo "Applying Download Bandwidth Limiting"
echo "========================================"

if [ "${ENABLE_RATE_LIMIT}" = "true" ]; then
    # Randomly select bandwidth: 0=2Mbps, 1=25Mbps, 2=100Mbps
    BANDWIDTH_CHOICE=$((RANDOM % 3))

    case $BANDWIDTH_CHOICE in
        0)
            BANDWIDTH="2mbit"
            echo "[INFO] Download bandwidth limit: 2 Mbps"
            ;;
        1)
            BANDWIDTH="25mbit"
            echo "[INFO] Download bandwidth limit: 25 Mbps"
            ;;
        2)
            BANDWIDTH="100mbit"
            echo "[INFO] Download bandwidth limit: 100 Mbps"
            ;;
    esac

    echo "[INFO] Configuring ingress traffic control..."

    # Note: ifb module should be loaded on host before starting container
    # Bring up ifb0 interface
    ip link set dev ifb0 up || echo "[WARNING] Could not bring up ifb0"

    # Redirect ingress traffic from eth0 to ifb0
    tc qdisc add dev eth0 handle ffff: ingress || echo "[WARNING] Could not add ingress qdisc"
    tc filter add dev eth0 parent ffff: protocol ip u32 match u32 0 0 action mirred egress redirect dev ifb0 || echo "[WARNING] Could not add ingress filter"

    # Apply rate limit on ifb0 (limit sets max queue size in bytes)
    tc qdisc add dev ifb0 root tbf rate $BANDWIDTH burst 32kbit limit 10000 || echo "[WARNING] Could not apply rate limit"

    echo "[INFO] Download bandwidth limited to $BANDWIDTH"
else
    echo "[INFO] Bandwidth rate limiting disabled (ENABLE_RATE_LIMIT not set)"
fi

echo ""
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
echo "Applying Network Latency Conditions"
echo "========================================"

if [ "${ENABLE_TC}" = "true" ]; then
    # Randomly select latency: 0=none, 1=100ms, 2=200ms
    LATENCY_CHOICE=$((RANDOM % 3))

    case $LATENCY_CHOICE in
        0)
            LATENCY="none"
            echo "[INFO] Network latency condition: none (no additional latency)"
            ;;
        1)
            LATENCY="100ms"
            echo "[INFO] Network latency condition: 100ms"
            ;;
        2)
            LATENCY="200ms"
            echo "[INFO] Network latency condition: 200ms"
            ;;
    esac

    # Apply latency if not "none"
    if [ "$LATENCY" != "none" ]; then
        echo "[INFO] Configuring traffic control for Mellowtel servers..."

        # Resolve Mellowtel domain to IP addresses
        MELLOWTEL_IPS=$(getent ahosts request.mellow.tel | awk '{print $1}' | sort -u)

        if [ -z "$MELLOWTEL_IPS" ]; then
            echo "[WARNING] Could not resolve request.mellow.tel, skipping latency configuration"
        else
            echo "[INFO] Mellowtel IPs: $MELLOWTEL_IPS"

            # Setup tc qdisc on eth0
            tc qdisc add dev eth0 root handle 1: prio
            tc qdisc add dev eth0 parent 1:3 handle 30: netem delay $LATENCY
            tc filter add dev eth0 protocol ip parent 1:0 prio 3 handle 1 fw flowid 1:3

            # Mark packets destined for Mellowtel IPs
            for IP in $MELLOWTEL_IPS; do
                iptables -t mangle -A OUTPUT -d $IP -j MARK --set-mark 1
                echo "[INFO] Marked traffic to $IP for ${LATENCY} latency"
            done

            echo "[INFO] Traffic control configured successfully"
        fi
    fi
else
    echo "[INFO] Traffic control disabled (ENABLE_TC not set)"
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
