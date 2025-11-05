# Quick Start Guide - Ubuntu VM via UTM

This is the fastest way to get started. Detailed instructions are in [UBUNTU_SETUP.md](UBUNTU_SETUP.md).

## Step 1: Create Ubuntu VM

1. Download **Ubuntu Server 22.04 LTS (AMD64)**: https://ubuntu.com/download/server
2. Open UTM → Create New Virtual Machine
3. Select "Virtualize" → Linux → Browse for Ubuntu ISO
4. Configure:
   - Memory: 4GB
   - CPU: 2-4 cores
   - Storage: 20GB
5. Install Ubuntu (set username/password)

## Step 2: Transfer Project to VM

### Option A: Via Git (Recommended)
```bash
# In Ubuntu VM
sudo apt install git -y
git clone <your-repo-url>
cd mellowtel_chrome_docker
```

### Option B: Via SCP
```bash
# From Mac terminal
cd /Users/danieljang/Desktop/mellowtel_chrome_docker
tar -czf mellowtel.tar.gz *
scp mellowtel.tar.gz username@vm-ip:~/

# In Ubuntu VM
tar -xzf mellowtel.tar.gz
cd mellowtel_chrome_docker
```

## Step 3: Install Docker

```bash
# In Ubuntu VM
./ubuntu_install.sh

# IMPORTANT: Log out and back in
exit
# SSH or login again
```

## Step 4: Transfer Extension File

```bash
# From Mac (if you have IdleForest.crx)
scp IdleForest.crx username@vm-ip:~/mellowtel_chrome_docker/
```

## Step 5: Run the Analyzer

```bash
# In Ubuntu VM
cd mellowtel_chrome_docker

# Test Chrome works
docker-compose run --rm mellowtel-analyzer python test_minimal.py

# If test passes, run experiment
docker-compose up

# Wait for completion...
# Results saved to: output/network_logs.jsonl
```

## Step 6: Get Results

```bash
# From Mac, download results
scp username@vm-ip:~/mellowtel_chrome_docker/output/network_logs.jsonl .

# Analyze
python analyze_logs.py network_logs.jsonl
```

## Troubleshooting

**Can't SSH to VM?**
```bash
# In UTM console, get IP address
ip addr show
# Look for inet 192.168.x.x

# From Mac
ssh username@192.168.x.x
```

**Docker permission denied?**
```bash
# Make sure you logged out and back in after running ubuntu_install.sh
# Or run:
newgrp docker
```

**Chrome crashes?**
```bash
docker-compose run --rm mellowtel-analyzer python diagnose.py
```

**Need more help?**
See [UBUNTU_SETUP.md](UBUNTU_SETUP.md) for detailed troubleshooting.

## What Gets Captured

The tool captures:
- ✅ All HTTP/HTTPS requests from web pages
- ✅ All requests from the Idle Forest extension
- ✅ Request/response headers
- ✅ Status codes and timestamps
- ✅ Which site triggered each request

Perfect for identifying extension network behavior!
