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

Each experiment run creates a timestamped directory: `output/run_YYYYMMDD_HHMMSS/`

All output files for that run are saved in this directory:

### Network Logs
`output/run_YYYYMMDD_HHMMSS/network_logs.jsonl` (JSON Lines format):
```json
{
  "timestamp": 1763420740,
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

### Speed Test Results
`output/run_YYYYMMDD_HHMMSS/speedtest.json`:
```json
{
  "download": 125680000.0,
  "upload": 45320000.0,
  "ping": 12.5,
  "server": {
    "sponsor": "ISP Name",
    "name": "City, Country"
  },
  "timestamp": "2025-11-18T17:30:00.000000",
  "client": {
    "ip": "1.2.3.4",
    "isp": "Internet Service Provider"
  }
}
```

This allows you to correlate network conditions with experiment results.

### Iframe Metadata
`output/run_YYYYMMDD_HHMMSS/iframe_metadata.jsonl`:
```json
{
  "visited_site": "https://www.example.com",
  "src": "https://iframe-domain.com/page",
  "id": "mllwtl-frame-id",
  "data_id": "",
  "domain": "iframe-domain.com",
  "first_seen": 114.77,
  "last_seen": 313.92,
  "duration_seconds": 199.15
}
```

Tracks when Mellowtel iframes were injected and how long they persisted.

### POST Payloads
Whenever a POST request is sent to `https://request.mellow.tel` with a content-type header containing "text" (e.g., `text/plain`, `text/html`), the request body is automatically saved to a separate file in `output/run_YYYYMMDD_HHMMSS/post_payloads/`.

Each file contains:
```
POST Payload Capture
======================================================================
Timestamp: 2025-11-18T17:30:00.000000
Visited Site: https://www.example.com
URL: https://request.mellow.tel/
Content-Type: text/plain
Content-Length: 89851 bytes
======================================================================

[Request body content here...]
```

Filenames follow the pattern: `post_payload_0001_YYYYMMDD_HHMMSS_microseconds_site.txt`

This allows you to analyze what data Mellowtel is exfiltrating to its servers.

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
├── Dockerfile                  # Chrome + Python container
├── docker-compose.yml          # Container orchestration
├── requirements.txt            # Python dependencies
├── entrypoint.sh               # Startup script (runs speedtest then experiment)
├── run_experiment.py           # Main control script
├── test_minimal.py             # Chrome test script
├── diagnose.py                 # Diagnostic tool
├── sites.txt                   # URLs to visit
├── IdleForest.crx              # Extension file (you provide)
├── output/                     # Experiment output (one subdirectory per run)
│   └── run_YYYYMMDD_HHMMSS/    # Timestamped run directory
│       ├── speedtest.json      # Network speed test results
│       ├── network_logs.jsonl  # Network request logs
│       ├── iframe_metadata.jsonl # Iframe injection tracking
│       └── post_payloads/      # POST request bodies to request.mellow.tel
├── README.md                   # This file
├── README_USAGE.md             # Detailed usage guide
└── CLAUDE.md                   # Developer guidance
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

# 3. Check output directory (shows timestamped run)
ls -l output/
# drwxr-xr-x  run_20251118_173000/

## Support

For issues:
1. Run diagnostics: `docker-compose run --rm mellowtel-analyzer python diagnose.py`
2. Check logs: `docker-compose logs`
3. Verify Chrome: `docker-compose run --rm mellowtel-analyzer google-chrome --version`
4. Check disk space: `df -h`
