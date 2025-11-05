#!/bin/bash
# Automated setup script for Ubuntu VM
# Run this on fresh Ubuntu Server installation

set -e

echo "=========================================="
echo "Mellowtel Analyzer - Ubuntu Setup"
echo "=========================================="
echo ""

# Check if running on Ubuntu
if ! grep -q "Ubuntu" /etc/os-release; then
    echo "Warning: This script is designed for Ubuntu"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Step 1: Updating system..."
sudo apt update
sudo apt upgrade -y

echo ""
echo "Step 2: Installing Docker..."
if command -v docker &> /dev/null; then
    echo "Docker already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    rm /tmp/get-docker.sh

    # Add current user to docker group
    sudo usermod -aG docker $USER
    echo "Added $USER to docker group"
fi

echo ""
echo "Step 3: Installing Docker Compose..."
if command -v docker-compose &> /dev/null; then
    echo "Docker Compose already installed: $(docker-compose --version)"
else
    sudo apt install docker-compose -y
fi

echo ""
echo "Step 4: Installing useful tools..."
sudo apt install -y git curl wget nano

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "IMPORTANT: You must log out and back in for Docker group changes to take effect"
echo ""
echo "After logging back in, run:"
echo "  cd mellowtel_chrome_docker"
echo "  docker-compose build"
echo "  docker-compose run --rm mellowtel-analyzer python test_minimal.py"
echo "  docker-compose up"
echo ""
echo "To log out: exit"
echo ""
