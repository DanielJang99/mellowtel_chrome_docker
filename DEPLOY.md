# Deployment Guide - AMD64 Linux Servers

Quick guide for deploying on cloud instances or Linux servers.

## 1. Prepare Linux Server

### Option A: AWS EC2
```bash
# Launch Ubuntu 22.04 LTS instance (t3.medium recommended)
# Security group: Allow SSH (22) from your IP

# SSH into instance
ssh -i your-key.pem ubuntu@ec2-ip-address
```

### Option B: DigitalOcean
```bash
# Create Droplet: Ubuntu 22.04, Basic 4GB
# SSH into droplet
ssh root@droplet-ip
```

### Option C: Google Cloud
```bash
# Create VM instance
gcloud compute instances create mellowtel \
  --machine-type=e2-medium \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud

# SSH
gcloud compute ssh mellowtel
```

### Option D: Your Own Linux Server
```bash
# Just SSH in
ssh user@server-ip
```

## 2. Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose -y

# Log out and back in
exit
# SSH back in
```

## 3. Transfer Project

### Method A: Git (Recommended)
```bash
git clone <your-repo-url>
cd mellowtel_chrome_docker
```

### Method B: SCP from Local Machine
```bash
# From your local machine
cd /path/to/mellowtel_chrome_docker
tar -czf mellowtel.tar.gz *

# Transfer
scp mellowtel.tar.gz user@server-ip:~/

# On server
tar -xzf mellowtel.tar.gz
cd mellowtel_chrome_docker
```

## 4. Configure and Run

```bash
# Edit sites if needed
nano sites.txt

# Test Chrome setup
docker-compose run --rm mellowtel-analyzer python test_minimal.py

# Should output:
# ✓ Chrome started successfully!
# ✓ Page title:
# ✓ Page title: Example Domain
# ✓ All tests passed!

# Run full experiment
docker-compose up

# Or run in background
docker-compose up -d
docker-compose logs -f  # View logs
```

## 5. Monitor Progress

```bash
# View logs
docker-compose logs -f

# Check container status
docker ps

# Check resource usage
docker stats
```

## 6. Retrieve Results

### Method A: SCP to Local Machine
```bash
# From local machine
scp user@server-ip:~/mellowtel_chrome_docker/output/network_logs.jsonl .
```

### Method B: Analyze on Server
```bash
# On server
docker-compose run --rm mellowtel-analyzer python analyze_logs.py

# Export to CSV (if prompted 'y')
# Then download CSV
scp user@server-ip:~/mellowtel_chrome_docker/output/network_logs.csv .
```

## 7. Cleanup

```bash
# Stop container
docker-compose down

# Remove all Docker data (optional)
docker system prune -a

# Remove project (optional)
cd ~
rm -rf mellowtel_chrome_docker
```

## Configuration Tips

### Adjust Dwell Time
For more thorough extension analysis:
```yaml
# In docker-compose.yml
environment:
  - DWELL_TIME=120  # 2 minutes per page
```

### Run in Headless Mode
For servers without display:
```yaml
environment:
  - HEADLESS=true  # Default
```

### Disable Images for Speed
```yaml
environment:
  - DISABLE_IMAGES=true
```

### Increase Shared Memory
If Chrome crashes:
```yaml
shm_size: 4gb  # Increase from 2gb
```

## Cost Estimates

### AWS EC2 t3.medium
- **Cost**: ~$0.042/hour (~$1/day)
- **Specs**: 2 vCPU, 4GB RAM
- **Runtime**: ~30 minutes for 20 sites @ 60s each

### DigitalOcean Basic Droplet
- **Cost**: $24/month (delete after use for prorated cost)
- **Specs**: 2 vCPU, 4GB RAM

### Google Cloud e2-medium
- **Cost**: ~$0.033/hour (~$0.80/day)
- **Specs**: 2 vCPU, 4GB RAM

**Tip**: Use spot/preemptible instances for even cheaper!

## Performance Benchmarks

- **16 sites @ 60s/page**: ~16 minutes
- **50 sites @ 60s/page**: ~50 minutes
- **100 sites @ 30s/page**: ~50 minutes

Add build time (~5 minutes first run).

## Troubleshooting

### Can't Connect to Server
```bash
# Check server is running
ping server-ip

# Check SSH port
telnet server-ip 22

# Try with verbose SSH
ssh -v user@server-ip
```

### Docker Permission Denied
```bash
# Make sure you logged out after adding to docker group
# Or run:
newgrp docker
```

### Chrome Fails to Start
```bash
# Run diagnostics
docker-compose run --rm mellowtel-analyzer python diagnose.py

# Check system resources
free -h
df -h
```

### Out of Memory
```bash
# Check memory
free -h

# Increase swap (temporary fix)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Slow Performance
- Use instances with more CPU cores
- Enable `DISABLE_IMAGES=true`
- Reduce `DWELL_TIME`
- Use SSD-backed storage

## Security Best Practices

1. **Firewall**: Only allow SSH from your IP
2. **SSH Keys**: Use key-based auth, disable password auth
3. **Updates**: Keep server updated
4. **Cleanup**: Remove project and data after completion
5. **Monitoring**: Check for unusual network activity
6. **Backup**: Save results before terminating instance

## Quick Reference

```bash
# Full workflow
ssh user@server-ip
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit
# SSH back in
git clone <repo>
cd mellowtel_chrome_docker
docker-compose run --rm mellowtel-analyzer python test_minimal.py
docker-compose up
# Wait for completion
scp user@server-ip:~/mellowtel_chrome_docker/output/network_logs.jsonl .
```
