# Ubuntu VM Setup Guide (UTM)

This guide shows you how to set up and run the Mellowtel network analyzer on Ubuntu VM via UTM.

## Part 1: Create Ubuntu VM in UTM

### 1.1 Download Ubuntu Server
- Download Ubuntu Server 22.04 LTS ISO from https://ubuntu.com/download/server
- Choose AMD64 architecture

### 1.2 Create VM in UTM
1. Open UTM
2. Click "Create a New Virtual Machine"
3. Choose "Virtualize" (for Intel/AMD)
4. Select "Linux"
5. Browse and select the Ubuntu ISO
6. Configure:
   - **Memory**: 4096 MB (4GB minimum)
   - **CPU Cores**: 2-4 cores
   - **Storage**: 20GB minimum
7. Create and start the VM

### 1.3 Install Ubuntu
1. Boot from ISO
2. Follow Ubuntu installation:
   - Choose "Install Ubuntu Server"
   - Set username/password (remember these!)
   - Install OpenSSH server (optional but recommended)
   - Complete installation and reboot

## Part 2: Set Up Docker on Ubuntu

### 2.1 SSH into VM (Optional)
If you enabled SSH during install:
```bash
# From your Mac terminal, find VM IP
# In UTM console, run: ip addr show

# SSH from Mac
ssh username@vm-ip-address
```

### 2.2 Install Docker
Run these commands in Ubuntu VM:

```bash
# Update system
sudo apt update
sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group (avoid using sudo)
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose -y

# Log out and back in for group changes
exit
# Then SSH back in or restart VM
```

### 2.3 Verify Docker
```bash
docker --version
docker-compose --version
```

## Part 3: Transfer Project to Ubuntu VM

### Method A: Using Git (Recommended)
```bash
# In Ubuntu VM
sudo apt install git -y
git clone <your-repo-url>
cd mellowtel_chrome_docker
```

### Method B: Using SCP from Mac
```bash
# From Mac terminal (where the project is)
cd /Users/danieljang/Desktop/mellowtel_chrome_docker
tar -czf mellowtel.tar.gz .
scp mellowtel.tar.gz username@vm-ip:/home/username/

# In Ubuntu VM
cd ~
tar -xzf mellowtel.tar.gz
cd mellowtel_chrome_docker
```

### Method C: Using Shared Folder (UTM)
1. In UTM, click on VM → Edit
2. Go to Sharing
3. Add shared directory from Mac
4. In Ubuntu:
```bash
sudo apt install virtiofsd -y
# Mount and copy files
```

## Part 4: Run the Analyzer

### 4.1 Place Extension File
If you have the IdleForest.crx extension:
```bash
# Transfer it to the project directory
# Using scp from Mac:
scp IdleForest.crx username@vm-ip:/home/username/mellowtel_chrome_docker/
```

### 4.2 Build and Run
```bash
cd mellowtel_chrome_docker

# Test Chrome setup first
docker-compose build
docker-compose run --rm mellowtel-analyzer python test_minimal.py

# If test passes, run full experiment
docker-compose up

# Or run in background
docker-compose up -d

# View logs
docker-compose logs -f
```

### 4.3 Retrieve Results
After the experiment completes:

```bash
# From Mac, download results via SCP
scp username@vm-ip:/home/username/mellowtel_chrome_docker/output/network_logs.jsonl .

# Or use the analysis script in VM
docker-compose run --rm mellowtel-analyzer python analyze_logs.py
```

## Part 5: Configuration

### Edit Sites to Visit
```bash
nano sites.txt
# Add URLs, one per line
```

### Adjust Settings
Edit `docker-compose.yml`:
```yaml
environment:
  - DWELL_TIME=60      # Seconds per page (increase for more extension activity)
  - HEADLESS=true      # Set to false to see browser window
  - DISABLE_IMAGES=false  # Set to true for faster execution
```

## Troubleshooting

### Docker Permission Denied
```bash
# Make sure you logged out and back in after adding user to docker group
# Or manually activate:
newgrp docker
```

### Out of Disk Space
```bash
# Check space
df -h

# Clean up Docker
docker system prune -a
```

### Container Won't Start
```bash
# Check logs
docker-compose logs

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up
```

### Chrome Crashes
```bash
# Run diagnostics
docker-compose run --rm mellowtel-analyzer python diagnose.py

# Check Chrome works
docker-compose run --rm mellowtel-analyzer google-chrome --version
```

## Quick Reference Commands

```bash
# Start experiment
docker-compose up

# Stop experiment
docker-compose down

# View logs
docker-compose logs -f

# Run specific test
docker-compose run --rm mellowtel-analyzer python test_minimal.py

# Rebuild container
docker-compose build --no-cache

# Analyze captured data
docker-compose run --rm mellowtel-analyzer python analyze_logs.py

# Clean everything
docker-compose down -v
docker system prune -a
```

## Performance Tips

1. **Allocate enough resources**: 4GB RAM minimum, 2+ CPU cores
2. **Use SSD storage** in UTM for better performance
3. **Disable GUI** in Ubuntu Server (already done)
4. **Run in headless mode** (HEADLESS=true)
5. **Increase DWELL_TIME** if extension needs more time to activate

## Next Steps

Once you have captured data in `output/network_logs.jsonl`:
1. Transfer to Mac for analysis
2. Use `analyze_logs.py` to identify suspicious domains
3. Export to CSV for further processing
4. Review extension-initiated requests vs page requests
