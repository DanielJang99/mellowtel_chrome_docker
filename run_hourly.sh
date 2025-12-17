#!/bin/bash

# Set variables
PROJECT_DIR="/home/ec2-user/mellowtel_chrome_docker"
mkdir -p "$PROJECT_DIR/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$PROJECT_DIR/logs/mellowtel_cron_${TIMESTAMP}.log"

# Log start
echo "========================================" >> "$LOG_FILE"
echo "$(date): Starting Mellowtel analysis" >> "$LOG_FILE"

# Navigate to project directory
cd "$PROJECT_DIR" || {
    echo "$(date): ERROR - Failed to change to $PROJECT_DIR" >> "$LOG_FILE"
    exit 1
}

# Check if there's already a container running and kill it
echo "$(date): Checking for existing containers..." >> "$LOG_FILE"
RUNNING_CONTAINERS=$(sudo docker ps -q)
if [ -n "$RUNNING_CONTAINERS" ]; then
    echo "$(date): Found running containers, stopping them..." >> "$LOG_FILE"
    sudo docker-compose down >> "$LOG_FILE" 2>&1
    sudo docker kill $(sudo docker ps -q) >> "$LOG_FILE" 2>&1
    echo "$(date): Containers stopped" >> "$LOG_FILE"
else
    echo "$(date): No existing containers found" >> "$LOG_FILE"
fi

# Run docker-compose
echo "$(date): Starting new container..." >> "$LOG_FILE"
sudo docker-compose up >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

# Clean up
sudo docker-compose down >> "$LOG_FILE" 2>&1

# Log completion
if [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): Mellowtel analysis completed successfully" >> "$LOG_FILE"
else
    echo "$(date): ERROR - Mellowtel analysis failed with exit code $EXIT_CODE" >> "$LOG_FILE"
fi

echo "========================================" >> "$LOG_FILE"