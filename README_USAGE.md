# Mellowtel SDK Network Analysis Tool - Usage Guide

This tool captures all network activity from Chrome browsing sessions with the "Idle Forest" extension installed, for security research purposes.

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- (Optional) `IdleForest.crx` extension file placed in the project root

### Run the Experiment

```bash
# Start the experiment
docker-compose up

# Or build and run
docker-compose up --build
```

The experiment will:
1. Start Chrome with the extension (if provided)
2. Visit each URL in `sites.txt`
3. Wait 30 seconds on each page (configurable)
4. Capture all network requests
5. Save logs to `output/network_logs.jsonl`

## Configuration

### Environment Variables (in `docker-compose.yml`)

- `DWELL_TIME`: Seconds to wait on each page (default: 30)
- `HEADLESS`: Run Chrome in headless mode (default: true)
- `DISABLE_IMAGES`: Disable image loading for faster execution (default: false)

Example:
```yaml
environment:
  - DWELL_TIME=60
  - HEADLESS=false
  - DISABLE_IMAGES=true
```

### Customize URLs

Edit `sites.txt` to add or remove websites:
```
https://www.example.com
https://www.another-site.com
```

Lines starting with `#` are ignored (comments).

## Adding the Extension

To analyze the Idle Forest extension's network behavior:

1. Obtain the `IdleForest.crx` file
2. Place it in the project root directory
3. The Dockerfile will automatically mount and load it

Without the extension, the tool will still capture network activity from regular page loads.

## Output Format

Network logs are saved in JSON Lines (`.jsonl`) format at `output/network_logs.jsonl`.

Each line is a JSON object representing one network request:

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

### Analyzing the Data

```bash
# Count total requests
wc -l output/network_logs.jsonl

# View requests with jq
cat output/network_logs.jsonl | jq '.'

# Filter requests by domain
cat output/network_logs.jsonl | jq 'select(.url | contains("mellowtel"))'

# Get unique domains
cat output/network_logs.jsonl | jq -r '.url' | sed 's|https\?://||' | cut -d'/' -f1 | sort -u
```

## Local Development (Without Docker)

If you want to run locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Install Chrome and ChromeDriver manually
# (OS-specific, see Chrome documentation)

# Run the script
python run_experiment.py
```

## Troubleshooting

### Chrome crashes or doesn't start

Increase shared memory size in `docker-compose.yml`:
```yaml
shm_size: 4gb
```

### Timeout errors

Increase the page load timeout or dwell time:
```yaml
environment:
  - DWELL_TIME=60
```

### Permission errors in Docker

Try running with:
```bash
docker-compose up --build --force-recreate
```

### Extension not loading

Verify the extension file:
- Must be named `IdleForest.crx`
- Must be in the project root directory
- Check Dockerfile mounts it correctly

## Research Notes

This tool is designed for security research on bandwidth-as-a-service (BaaS) models. Key considerations:

- **Network requests from extensions** may be asynchronous and delayed
- The `DWELL_TIME` should be long enough to capture background extension activity
- Look for requests to non-visited domains (potential extension endpoints)
- Check for requests that occur across multiple page visits (persistent extension behavior)

## Project Structure

```
.
├── Dockerfile              # Container definition
├── docker-compose.yml      # Orchestration config
├── requirements.txt        # Python dependencies
├── run_experiment.py       # Main control script
├── sites.txt              # URLs to visit
├── IdleForest.crx         # Extension file (not included)
├── output/                # Network logs output
│   └── network_logs.jsonl
└── README_USAGE.md        # This file
```

## License & Ethics

This tool is for authorized security research only. Ensure you have:
- Permission to analyze the extension
- Consent for any network traffic analysis
- Compliance with applicable laws and terms of service

Do not use this tool to:
- Enhance or improve malicious capabilities
- Circumvent security measures
- Violate privacy or computer fraud laws
