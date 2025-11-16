# Mellowtel SDK Network Analysis Platform

A Docker-based research tool for analyzing the Mellowtel SDK's network behavior in browser extensions. Designed to run on AMD64/x86 Linux machines (cloud instances, servers, or local Linux).

## Quick Start

### Prerequisites
- AMD64/x86 Linux machine (Ubuntu, Debian, etc.)
- Docker and Docker Compose installed
- 4GB RAM minimum, 2+ CPU cores

### Installation

1. **Install Docker** (if not already installed):
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# Log out and back in for group changes
```

2. **Install Docker Compose**:
```bash
sudo apt install docker-compose -y
```

3. **Clone or transfer this project**:
```bash
cd /path/to/mellowtel_chrome_docker
```

4. **Add the extension file**:
   - Place `IdleForest.crx` in the project root directory

5. **Run the experiment**:
```bash
# Test Chrome setup first
docker-compose run --rm mellowtel-analyzer python test_minimal.py

# If successful, run full experiment
docker-compose up

# Or run in background
docker-compose up -d
```

Results will be saved to `output/network_logs.jsonl`.

## Project Overview

This tool:
- Runs Chrome in Docker with the Idle Forest extension loaded
- Visits websites from `sites.txt` (configurable)
- Captures ALL network requests (webpage + extension)
- Saves detailed network logs in JSON Lines format

**Purpose**: Security research analyzing bandwidth-as-a-service (BaaS) models.

## Configuration

### Modify Sites to Visit
Edit `sites.txt`:
```bash
nano sites.txt
# Add URLs, one per line
```

### Adjust Behavior
Edit `docker-compose.yml`:
```yaml
environment:
  - DWELL_TIME=60      # Seconds to wait on each page
  - HEADLESS=true      # Run Chrome in headless mode
  - DISABLE_IMAGES=false  # Set to true for faster execution
```

## Analyzing Results

```bash
# Run analysis tool
docker-compose run --rm mellowtel-analyzer python analyze_logs.py

# View summary statistics and identify suspicious domains
```

The analysis tool will show:
- Total requests captured
- Requests per site visited
- Top domains requested
- Potential extension-related domains
- Response status codes

## Commands Reference

```bash
# Start experiment (foreground)
docker-compose up

# Start experiment (background)
docker-compose up -d

# Stop experiment
docker-compose down

# View logs in real-time
docker-compose logs -f

# Test Chrome setup
docker-compose run --rm mellowtel-analyzer python test_minimal.py

# Run diagnostics
docker-compose run --rm mellowtel-analyzer python diagnose.py

# Analyze captured data
docker-compose run --rm mellowtel-analyzer python analyze_logs.py

# Rebuild container
docker-compose build --no-cache

# Clean up everything
docker-compose down -v
docker system prune -a
```

## Cloud Deployment

### AWS EC2
1. Launch Ubuntu 22.04 LTS instance (t3.medium or larger)
2. SSH into instance
3. Install Docker and Docker Compose
4. Transfer project files
5. Run `docker-compose up`

### Google Cloud Platform
```bash
# Create VM instance
gcloud compute instances create mellowtel-analyzer \
  --machine-type=e2-medium \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud

# SSH and install
gcloud compute ssh mellowtel-analyzer
# Then follow installation steps
```

### DigitalOcean
1. Create Droplet (Ubuntu 22.04, Basic 4GB)
2. SSH into droplet
3. Follow installation steps above

### Transfer Files to Server
```bash
# Using SCP
scp -r mellowtel_chrome_docker user@server-ip:~/

# Or using Git
git clone <repo-url>
```

## Output Format

Network logs in `output/network_logs.jsonl` (JSON Lines format):
```json
{
  "timestamp": "2025-11-04T19:30:00.000Z",
  "url": "https://example.com/api/data",
  "method": "GET",
  "request_headers": {
    "User-Agent": "...",
    "Accept": "..."
  },
  "response": {
    "status_code": 200,
    "reason": "OK",
    "headers": {
      "Content-Type": "application/json"
    }
  },
  "visited_site": "https://www.example.com"
}
```

Each line represents one network request with full metadata.

## Troubleshooting

### Test Chrome Works
```bash
docker-compose run --rm mellowtel-analyzer google-chrome --version
docker-compose run --rm mellowtel-analyzer python test_minimal.py
```

### Run Full Diagnostics
```bash
docker-compose run --rm mellowtel-analyzer python diagnose.py
```

### Chrome Crashes
- Check Docker has enough memory (4GB minimum)
- Increase shared memory: Edit `shm_size: 4gb` in docker-compose.yml
- Check logs: `docker-compose logs`

### Permission Denied
```bash
# Make sure user is in docker group
sudo usermod -aG docker $USER
# Log out and back in
```

### Out of Disk Space
```bash
df -h
docker system prune -a
```

## File Structure

```
mellowtel_chrome_docker/
├── Dockerfile              # Chrome + Python container
├── docker-compose.yml      # Container orchestration
├── requirements.txt        # Python dependencies
├── run_experiment.py       # Main control script
├── analyze_logs.py         # Network log analysis
├── test_minimal.py         # Chrome test script
├── diagnose.py             # Diagnostic tool
├── sites.txt               # URLs to visit
├── IdleForest.crx          # Extension file (you provide)
├── output/                 # Network logs output
│   └── network_logs.jsonl
├── README.md               # This file
├── README_USAGE.md         # Detailed usage guide
└── CLAUDE.md               # Developer guidance
```

## Requirements

- **OS**: Linux (AMD64/x86_64) - Ubuntu, Debian, CentOS, etc.
- **RAM**: 4GB minimum
- **CPU**: 2+ cores recommended
- **Disk**: 20GB free space
- **Software**: Docker & Docker Compose

## Security Notice

This tool is for **authorized security research only**. It analyzes browser extension behavior for privacy and security analysis.

**Ethical Use Only:**
- ✅ Authorized security research
- ✅ Privacy impact analysis
- ✅ Academic research with consent
- ❌ Enhancing malicious capabilities
- ❌ Unauthorized monitoring
- ❌ Violating laws or ToS

## Documentation

- **[README_USAGE.md](README_USAGE.md)** - Detailed usage instructions
- **[CLAUDE.md](CLAUDE.md)** - Developer guidance for Claude Code

## Example Analysis Workflow

```bash
# 1. Customize sites to visit
nano sites.txt

# 2. Run experiment (16 sites × 60 seconds = ~16 minutes)
docker-compose up

# 3. Analyze results
docker-compose run --rm mellowtel-analyzer python analyze_logs.py

# 4. Export to CSV for further analysis
# (Analysis script offers CSV export option)

# 5. Examine suspicious domains
cat output/network_logs.jsonl | jq 'select(.url | contains("suspicious-domain"))'
```

## Support

For issues:
1. Run diagnostics: `docker-compose run --rm mellowtel-analyzer python diagnose.py`
2. Check logs: `docker-compose logs`
3. Verify Chrome: `docker-compose run --rm mellowtel-analyzer google-chrome --version`
4. Check disk space: `df -h`
