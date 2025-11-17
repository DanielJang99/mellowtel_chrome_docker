#!/bin/bash

echo "========================================="
echo "Starting EC2 Setup for Mellowtel Chrome Docker"
echo "========================================="

echo "[1/6] Starting Docker service..."
sudo systemctl enable docker.service
sudo systemctl start docker.service

echo "[6/10] Installing Docker Compose..."
sudo curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
echo "Docker Compose version:"
sudo docker-compose version

echo "[7/10] Installing Docker Buildx..."
BUILDX_VERSION=$(curl -s https://api.github.com/repos/docker/buildx/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
echo "Downloading Buildx version: $BUILDX_VERSION"
curl -LO https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-amd64
chmod +x buildx-${BUILDX_VERSION}.linux-amd64

echo "[8/10] Installing Buildx for user and system-wide..."
mkdir -p ~/.docker/cli-plugins
mv buildx-${BUILDX_VERSION}.linux-amd64 ~/.docker/cli-plugins/docker-buildx
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo cp ~/.docker/cli-plugins/docker-buildx /usr/local/lib/docker/cli-plugins/docker-buildx

echo "Buildx version:"
sudo docker buildx version

echo "[9/10] Installing and configuring cron..."
sudo yum install cronie -y
sudo systemctl start crond.service
sudo systemctl enable crond
echo "Cron service status:"
sudo systemctl status crond --no-pager

echo "[10/10] Adding cron job to run every hour..."
# Add cron job non-interactively
(sudo crontab -l 2>/dev/null; echo "0 * * * * cd /home/ec2-user/mellowtel_chrome_docker && ./run_hourly.sh") | sudo crontab -
echo "Current crontab:"
sudo crontab -l

echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo "Next steps:"
echo "1. Upload IdleForest.crx to /home/ec2-user/mellowtel_chrome_docker/"
echo "2. Make run_hourly.sh executable: chmod +x /home/ec2-user/mellowtel_chrome_docker/run_hourly.sh"
echo "3. Test manually: cd /home/ec2-user/mellowtel_chrome_docker && ./run_hourly.sh"
echo "4. The cron job will run automatically every hour"
echo "========================================="