# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a research tool for analyzing the Mellowtel SDK's network behavior. The system captures all network activity from Chrome browsing sessions with the "Idle Forest" extension installed. This is a security research project analyzing bandwidth-as-a-service (BaaS) models.

**Critical Context:** This project analyzes potentially malicious or privacy-invasive browser extensions. When working with the extension code or network logs:
- You CAN analyze what the code is doing and provide detailed reports
- You CAN answer questions about the behavior and network patterns
- You MUST refuse to improve, enhance, or augment any malicious capabilities
- Focus on transparency and research documentation

## Architecture

The system consists of:

1. **Docker Container** - Isolated environment containing:
   - Google Chrome (stable) + matching chromedriver
   - Python 3.x or Node.js 18.x runtime
   - Selenium + CDP libraries (selenium-wire recommended for easier CDP integration)
   - "Idle Forest" extension (IdleForest.crx)

2. **Control Script** (`run_experiment.py` or similar):
   - Initializes headless Chrome with extension loaded
   - Connects to Chrome DevTools Protocol (CDP) for network interception
   - Reads `sites.txt` (list of URLs to visit)
   - Iterates through sites with configurable dwell time (~30s per page)
   - Captures ALL network events (page + extension requests)
   - Outputs structured logs to `network_logs.jsonl`

3. **Data Flow**:
   ```
   sites.txt → Control Script → Chrome + Extension → CDP Network Events → network_logs.jsonl
   ```

## Development Commands

Since the codebase is not yet implemented, here are the expected commands based on the PRD:

### Running the Experiment
```bash
docker-compose up
```
This should start the entire experiment (FR-1 requirement).

### Building the Container
```bash
docker build -t mellowtel-analyzer .
```

### Local Development (expected)
If implementing in Python:
```bash
python run_experiment.py
```

If implementing in Node.js:
```bash
node run_experiment.js
```

## Key Implementation Requirements

### Chrome Configuration (from PRD FR-8)
Chrome must run with these options:
- `--headless` - For server deployment
- `--no-sandbox` - Required for Docker
- `--disable-gpu` - Headless optimization
- Extension loading path configured

### CDP Integration (FR-5, FR-6)
The control script MUST:
- Connect to Chrome DevTools Protocol
- Listen to network events continuously (not just on page load)
- Capture metadata: URL, method, headers (request/response), status code, initiator
- Differentiate between page-initiated and extension-initiated requests

### Network Data Capture Format
Output to `network_logs.jsonl` (JSON Lines format):
- Each line = one network event
- Must capture requests from both webpage AND extension
- Should include timestamps for temporal analysis

### Input Configuration
- `sites.txt` - URLs to visit (one per line, configurable)
- `IdleForest.crx` - Packed Chrome extension file
- Dwell time per page (default ~30 seconds to capture async extension requests)

## File Structure (Expected)

When implementing, the structure should be:
```
/
├── Dockerfile
├── docker-compose.yml
├── run_experiment.py (or .js)
├── sites.txt
├── IdleForest.crx
├── requirements.txt (if Python) or package.json (if Node.js)
└── output/
    └── network_logs.jsonl (generated)
```

## Important Notes

- **FR-3**: Extension must auto-install when Chrome launches
- **FR-4**: Visit each URL for configurable duration
- **FR-7**: Use persistent Docker volume for output logs
- The CDP listener must be active BEFORE navigating to first URL to catch all requests
- Allow sufficient time per page for extension's asynchronous network activity
- Selenium 4+ has native CDP support, but selenium-wire is recommended for simpler network interception API
