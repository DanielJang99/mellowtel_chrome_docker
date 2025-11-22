#!/usr/bin/env python3
"""
Mellowtel SDK Network Analysis Tool
Captures all network activity from Chrome browsing with extension installed.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import urlparse

from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, TimeoutException


class NetworkAnalyzer:
    """Main class for running the network analysis experiment."""

    def __init__(self):
        self.dwell_time = int(os.getenv('DWELL_TIME', '30'))
        self.iframe_wait_time = 300  # 5 minutes after iframe detection
        self.iframe_poll_interval = 1  # Check for iframe every 2 seconds
        self.max_wait_for_iframe = 300  # Maximum 5 minutes to wait for iframe to appear
        self.headless = os.getenv('HEADLESS', 'false').lower() == 'true'
        self.disable_images = os.getenv('DISABLE_IMAGES', 'false').lower() == 'true'
        self.sites_file = 'sites.txt'
        self.extension_path = 'IdleForest.crx'

        # Generate timestamped output directory
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        self.timestamp = timestamp
        self.run_dir = f'output/run_{timestamp}'
        self.output_file = f'{self.run_dir}/network_logs.jsonl'
        self.iframe_metadata_file = f'{self.run_dir}/iframe_metadata.jsonl'
        self.post_payloads_dir = f'{self.run_dir}/post_payloads'

        self.driver = None
        self.mellowtel_iframe_urls = set()  # Track iframe URLs for filtering
        self.mellowtel_domains = set()  # Track iframe domains for filtering
        self.iframe_metadata = {}  # Track iframe metadata: {src: {first_seen, last_seen, id, data_id, domain}}
        self.extension_id = None  # Store extension ID for activation
        self.extension_activated = False  # Track if extension has been activated
        self.monitoring_start_time = None  # Track when monitoring started
        self.post_payload_counter = 0  # Counter for POST payload files

    def setup_chrome_options(self) -> Options:
        """Configure Chrome options for the experiment."""
        chrome_options = Options()

        # Critical flags for Docker environment
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--disable-software-rasterizer')

        # Headless mode (only use if explicitly enabled, Xvfb is preferred to avoid HeadlessChrome user agent)
        if self.headless:
            chrome_options.add_argument('--headless')
            print("[INFO] Using headless mode (User-Agent will show 'HeadlessChrome')")
        else:
            print("[INFO] Using Xvfb virtual display (User-Agent will show normal 'Chrome')")

        # Remote debugging (helps with stability)
        chrome_options.add_argument('--remote-debugging-port=9222')

        # Window size
        chrome_options.add_argument('--window-size=1920,1080')

        # Set unique user data directory to avoid conflicts
        import tempfile
        user_data_dir = tempfile.mkdtemp(prefix='chrome_profile_')
        chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
        print(f"[INFO] Using user data directory: {user_data_dir}")

        # Disable automation detection
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Additional stability flags
        chrome_options.add_argument('--no-first-run')
        chrome_options.add_argument('--no-default-browser-check')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')

        # Optional: Disable images for faster loading
        prefs = {}
        if self.disable_images:
            prefs["profile.managed_default_content_settings.images"] = 2

        # Disable save password prompts
        prefs["credentials_enable_service"] = False
        prefs["profile.password_manager_enabled"] = False

        if prefs:
            chrome_options.add_experimental_option("prefs", prefs)

        # Load extension if it exists
        extension_loaded = False
        if os.path.exists(self.extension_path):
            try:
                chrome_options.add_extension(self.extension_path)
                extension_loaded = True
                print(f"[INFO] Extension loaded from: {self.extension_path}")
            except Exception as e:
                print(f"[WARNING] Failed to load extension: {e}")
                print("[WARNING] Continuing without extension.")
        else:
            print(f"[WARNING] Extension file not found: {self.extension_path}")
            print("[WARNING] Continuing without extension. Network capture will only include page requests.")

        # Logging for debugging
        chrome_options.add_argument('--enable-logging')
        chrome_options.add_argument('--v=1')

        return chrome_options

    def load_sites(self) -> List[str]:
        """Load list of URLs from sites.txt."""
        try:
            with open(self.sites_file, 'r') as f:
                sites = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            print(f"[INFO] Loaded {len(sites)} sites from {self.sites_file}")
            return sites
        except FileNotFoundError:
            print(f"[ERROR] Sites file not found: {self.sites_file}")
            sys.exit(1)

    def initialize_driver(self):
        """Initialize the Selenium WebDriver with selenium-wire."""
        print("[INFO] Initializing Chrome WebDriver...")

        # Check Chrome version
        try:
            import subprocess
            chrome_version = subprocess.check_output(['google-chrome', '--version'],
                                                     stderr=subprocess.STDOUT).decode().strip()
            print(f"[INFO] {chrome_version}")
        except Exception as e:
            print(f"[WARNING] Could not determine Chrome version: {e}")

        chrome_options = self.setup_chrome_options()

        # Selenium-wire options for network interception
        seleniumwire_options = {
            'disable_encoding': True,  # Don't decode responses
        }

        try:
            print("[INFO] Starting Chrome with selenium-wire...")
            self.driver = webdriver.Chrome(
                options=chrome_options,
                seleniumwire_options=seleniumwire_options
            )
            self.driver.set_page_load_timeout(60)
            print("[INFO] WebDriver initialized successfully")
        except WebDriverException as e:
            print(f"[ERROR] Failed to initialize WebDriver: {e}")
            print("\n[DEBUG] Troubleshooting tips:")
            print("  1. Check Chrome is installed: google-chrome --version")
            print("  2. Check ChromeDriver is installed: chromedriver --version")
            print("  3. Ensure versions match")
            print("  4. Try running with HEADLESS=true")
            print("  5. Check Docker shared memory (shm_size in docker-compose.yml)")
            sys.exit(1)

    def get_extension_id(self) -> str:
        """
        Get the extension ID for IdleForest extension.
        Returns the extension ID or None if not found.
        """
        try:
            print("[INFO] Getting extension ID...")

            # Navigate to chrome://extensions
            max_retries = 3
            for ext_attempt in range(max_retries):
                try:
                    self.driver.get("chrome://extensions/")
                    time.sleep(5)
                    break
                except RuntimeError as e:
                    if "dictionary changed size during iteration" in str(e):
                        if ext_attempt < max_retries - 1:
                            print(f"[WARNING] RuntimeError navigating to extensions page (selenium-wire cert bug)")
                            print(f"[INFO] Retrying...")
                            time.sleep(0.5)
                        else:
                            print(f"[ERROR] Failed to navigate to extensions page")
                            raise
                    else:
                        raise

            # Enable developer mode to see extension IDs
            script = """
            const devModeToggle = document.querySelector('extensions-manager')
                .shadowRoot.querySelector('extensions-toolbar')
                .shadowRoot.querySelector('#devMode');
            if (devModeToggle && !devModeToggle.checked) {
                devModeToggle.click();
            }
            """
            self.driver.execute_script(script)
            time.sleep(2)

            # Get all extension IDs and find IdleForest
            script = """
            const manager = document.querySelector('extensions-manager');
            const itemList = manager.shadowRoot.querySelector('extensions-item-list');
            const items = itemList.shadowRoot.querySelectorAll('extensions-item');

            const extensions = [];
            items.forEach(item => {
                const name = item.shadowRoot.querySelector('#name').textContent.trim();
                const id = item.id;
                extensions.push({name: name, id: id});
            });

            return extensions;
            """
            extensions = self.driver.execute_script(script)
            for ext in extensions:
                print(f"[INFO] Found extension: {ext['name']} (ID: {ext['id']})")
                # Look for IdleForest or Idle Forest
                if 'idle' in ext['name'].lower() and 'forest' in ext['name'].lower():
                    self.extension_id = ext['id']
                    print(f"[SUCCESS] Found IdleForest extension ID: {self.extension_id}")

                    # Enable the extension if it's not already enabled
                    self.enable_extension(ext['id'])

                    return self.extension_id

            # If not found by name, just use the first extension (assuming it's the only one)
            if extensions and len(extensions) > 0:
                self.extension_id = extensions[0]['id']
                print(f"[WARNING] Could not find 'IdleForest' by name. Using first extension: {self.extension_id}")

                # Enable the extension
                self.enable_extension(extensions[0]['id'])

                return self.extension_id

            print("[WARNING] No extensions found")
            return None

        except Exception as e:
            print(f"[WARNING] Error getting extension ID: {e}")
            return None

    def enable_extension(self, extension_id: str):
        """
        Enable the extension via the toggle on chrome://extensions page.
        """
        try:
            print(f"[INFO] Ensuring extension is enabled...")

            # Navigate to chrome://extensions if not already there
            if not self.driver.current_url.startswith('chrome://extensions'):
                max_retries = 3
                for enable_attempt in range(max_retries):
                    try:
                        self.driver.get("chrome://extensions/")
                        time.sleep(2)
                        break
                    except RuntimeError as e:
                        if "dictionary changed size during iteration" in str(e):
                            if enable_attempt < max_retries - 1:
                                print(f"[WARNING] RuntimeError navigating to extensions (selenium-wire cert bug)")
                                print(f"[INFO] Retrying...")
                                time.sleep(0.5)
                            else:
                                print(f"[ERROR] Failed to navigate to extensions page for enabling")
                                return
                        else:
                            raise

            # Check and enable the extension toggle
            script = f"""
            const manager = document.querySelector('extensions-manager');
            const itemList = manager.shadowRoot.querySelector('extensions-item-list');
            const items = itemList.shadowRoot.querySelectorAll('extensions-item');

            let found = false;
            items.forEach(item => {{
                if (item.id === '{extension_id}') {{
                    const toggle = item.shadowRoot.querySelector('#enableToggle');
                    if (toggle && !toggle.checked) {{
                        toggle.click();
                        found = true;
                        return 'enabled';
                    }} else if (toggle && toggle.checked) {{
                        found = true;
                        return 'already_enabled';
                    }}
                }}
            }});

            return found ? 'success' : 'not_found';
            """

            result = self.driver.execute_script(script)

            if result == 'success':
                print(f"[SUCCESS] Extension is now enabled")
                time.sleep(1)
            else:
                print(f"[INFO] Extension toggle state: {result}")

        except Exception as e:
            print(f"[WARNING] Error enabling extension: {e}")

    def activate_extension(self):
        """
        Activate the IdleForest extension by navigating to its popup URL and clicking "Start Planting".
        """
        if not self.extension_id:
            print("[WARNING] Extension ID not available. Skipping activation.")
            return False

        try:
            print(f"[INFO] Activating IdleForest extension...")

            # Save current URL to return to later
            original_url = self.driver.current_url
            popup_url = f"chrome-extension://{self.extension_id}/popup.html"

            # Open extension popup
            print(f"[INFO] Opening extension popup...")
            max_retries = 3
            for popup_attempt in range(max_retries):
                try:
                    self.driver.get(popup_url)
                    time.sleep(2)
                    print(f"[SUCCESS] Navigated to extension popup: {popup_url}")
                    break  # Success
                except RuntimeError as e:
                    if "dictionary changed size during iteration" in str(e):
                        if popup_attempt < max_retries - 1:
                            print(f"[WARNING] RuntimeError opening popup (selenium-wire cert bug) on attempt {popup_attempt + 1}/{max_retries}")
                            print(f"[INFO] Retrying...")
                            time.sleep(0.5)
                        else:
                            print(f"[ERROR] Failed to open popup after {max_retries} attempts")
                            return False
                    else:
                        raise

            # Look for "Start Planting" button
            print("[INFO] Looking for 'Start Planting' button...")

            # Wait a bit for any dynamic content to load
            time.sleep(2)

            try:
                # First, list all buttons to help debug
                list_buttons_script = """
                const buttons = document.querySelectorAll('button');
                const buttonInfo = [];
                buttons.forEach((button, index) => {
                    buttonInfo.push({
                        index: index,
                        innerText: button.innerText,
                        textContent: button.textContent,
                        innerHTML: button.innerHTML
                    });
                });
                return buttonInfo;
                """

                all_buttons = self.driver.execute_script(list_buttons_script)
                print(f"[INFO] Found {len(all_buttons)} button(s) in popup:")

                # Find button with text containing "Start Planting" (case-insensitive)
                find_button_script = """
                const buttons = document.querySelectorAll('button');
                for (let button of buttons) {
                    const innerText = (button.innerText || '').trim();
                    const textContent = (button.textContent || '').trim();

                    if (innerText.toLowerCase().includes('start planting') ||
                        textContent.toLowerCase().includes('start planting')) {
                        return button;
                    }
                }
                return null;
                """

                start_button = self.driver.execute_script(find_button_script)

                if start_button:
                    print("[SUCCESS] Found 'Start Planting' button!")
                    print("[INFO] Clicking 'Start Planting' button...")

                    # Click the button
                    self.driver.execute_script("arguments[0].click();", start_button)
                    time.sleep(2)
                    print("[SUCCESS] Clicked 'Start Planting' button")

                    # Navigate back to original site
                    print(f"[INFO] Navigating back to site: {original_url}")
                    max_retries = 3
                    for back_attempt in range(max_retries):
                        try:
                            self.driver.get(original_url)
                            time.sleep(2)
                            print("[INFO] Back on site")
                            break
                        except RuntimeError as e:
                            if "dictionary changed size during iteration" in str(e):
                                if back_attempt < max_retries - 1:
                                    print(f"[WARNING] RuntimeError navigating back (selenium-wire cert bug)")
                                    print(f"[INFO] Retrying...")
                                    time.sleep(0.5)
                                else:
                                    print(f"[ERROR] Failed to navigate back after clicking button")
                                    return False
                            else:
                                raise

                    return True
                else:
                    print("[ERROR] 'Start Planting' button not found in popup!")
                    print("[ERROR] Extension activation failed. Exiting script.")
                    sys.exit(1)

            except Exception as e:
                print(f"[ERROR] Error finding/clicking 'Start Planting' button: {e}")
                import traceback
                traceback.print_exc()
                print("[ERROR] Extension activation failed. Exiting script.")
                sys.exit(1)

        except Exception as e:
            print(f"[ERROR] Error activating extension: {e}")
            import traceback
            traceback.print_exc()
            print("[ERROR] Extension activation failed. Exiting script.")
            sys.exit(1)

    def extract_request_data(self, request) -> Dict[str, Any]:
        """Extract relevant data from a request object."""
        try:
            # Extract request headers
            request_headers = {}
            if hasattr(request, 'headers'):
                request_headers = dict(request.headers)

            # Extract response data if available
            response_data = {}
            if request.response:
                response_data = {
                    'status_code': request.response.status_code,
                    'reason': request.response.reason,
                    'headers': dict(request.response.headers) if hasattr(request.response, 'headers') else {}
                }

            return {
                'timestamp': int(datetime.utcnow().timestamp()),
                'url': request.url,
                'method': request.method,
                'request_headers': request_headers,
                'response': response_data if request.response else None,
            }
        except Exception as e:
            print(f"[WARNING] Error extracting request data: {e}")
            return None

    def check_for_mellowtel_iframes(self) -> List[Dict[str, str]]:
        """
        Check DOM for iframes with 'mllwtl' in their id or data-id attributes.
        Returns list of iframe metadata dictionaries.
        """
        try:
            script = """
            const iframes = document.querySelectorAll('iframe');
            const mellowtelIframes = [];

            iframes.forEach(iframe => {
                const id = iframe.getAttribute('id') || '';
                const dataId = iframe.getAttribute('data-id') || '';

                if (id.includes('mllwtl') || dataId.includes('mllwtl')) {
                    const src = iframe.getAttribute('src') || '';
                    if (src) {
                        mellowtelIframes.push({
                            src: src,
                            id: id,
                            dataId: dataId
                        });
                    }
                }
            });

            return mellowtelIframes;
            """

            result = self.driver.execute_script(script)

            if result:
                return result
            else:
                return []

        except Exception as e:
            print(f"[WARNING] Error checking for Mellowtel iframes: {e}")
            return []

    def extract_domain(self, url: str) -> str:
        """
        Extract domain (netloc) from a URL.
        Returns empty string if URL is invalid.
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return ""

    def is_mellowtel_request(self, request_url: str) -> bool:
        """
        Check if a request is Mellowtel-related.
        Returns True if:
        - URL contains 'request.mellow.tel'
        - Request domain matches any tracked Mellowtel iframe domain
        """
        # Check for request.mellow.tel
        if 'request.mellow.tel' in request_url:
            return True

        # Extract domain from request URL
        request_domain = self.extract_domain(request_url)
        if not request_domain:
            return False

        # Check if request domain matches any tracked iframe domains
        if request_domain in self.mellowtel_domains:
            return True

        return False

    def update_iframe_metadata(self, iframe_data: Dict[str, str], current_time: float):
        """
        Update iframe metadata with current timestamp.
        Tracks first_seen and last_seen times.
        """
        src = iframe_data['src']

        if src not in self.iframe_metadata:
            # First time seeing this iframe
            domain = self.extract_domain(src)
            self.iframe_metadata[src] = {
                'src': src,
                'id': iframe_data['id'],
                'data_id': iframe_data['dataId'],
                'domain': domain,
                'first_seen': current_time,
                'last_seen': current_time
            }
        else:
            # Update last_seen time
            self.iframe_metadata[src]['last_seen'] = current_time

    def save_iframe_metadata(self, site_url: str):
        """Save iframe metadata to JSONL file."""
        try:
            # Ensure output directory exists
            Path(self.iframe_metadata_file).parent.mkdir(parents=True, exist_ok=True)

            with open(self.iframe_metadata_file, 'a') as f:
                for src, metadata in self.iframe_metadata.items():
                    # Calculate duration
                    duration = metadata['last_seen'] - metadata['first_seen']

                    iframe_record = {
                        'visited_site': site_url,
                        'src': metadata['src'],
                        'id': metadata['id'],
                        'data_id': metadata['data_id'],
                        'domain': metadata['domain'],
                        'first_seen': metadata['first_seen'],
                        'last_seen': metadata['last_seen'],
                        'duration_seconds': duration
                    }

                    # Write as JSON Lines format
                    f.write(json.dumps(iframe_record) + '\n')

            print(f"[INFO] Saved metadata for {len(self.iframe_metadata)} iframe(s)")
        except Exception as e:
            print(f"[ERROR] Failed to save iframe metadata: {e}")

    def save_post_payload(self, request, site_url: str):
        """
        Save POST request payload to a separate file if it's to request.mellow.tel
        and content-type includes 'text'.
        """
        try:
            # Check if this is a POST request to request.mellow.tel
            if request.method != 'POST' or 'request.mellow.tel' not in request.url:
                return

            # Check if content-type includes 'text'
            content_type = ''
            if hasattr(request, 'headers') and 'content-type' in request.headers:
                content_type = request.headers['content-type'].lower()

            if 'text' not in content_type:
                return

            # Ensure output directory exists
            Path(self.post_payloads_dir).mkdir(parents=True, exist_ok=True)

            # Get request body
            body = None
            if hasattr(request, 'body'):
                body = request.body

            if body is None:
                print(f"[WARNING] POST request to request.mellow.tel has no body")
                return

            # Increment counter
            self.post_payload_counter += 1

            # Create filename with timestamp, counter, and visited site
            safe_site = site_url.replace('https://', '').replace('http://', '').replace('/', '_')[:50]
            timestamp_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
            filename = f"post_payload_{self.post_payload_counter:04d}_{timestamp_str}_{safe_site}.txt"
            filepath = Path(self.post_payloads_dir) / filename

            # Decode body if it's bytes
            if isinstance(body, bytes):
                try:
                    body_text = body.decode('utf-8')
                except UnicodeDecodeError:
                    # If UTF-8 fails, try latin-1
                    try:
                        body_text = body.decode('latin-1')
                    except:
                        # Save as hex if decoding fails
                        body_text = f"[Binary data, hex dump]:\n{body.hex()}"
            else:
                body_text = str(body)

            # Save to file with metadata header
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"POST Payload Capture\n")
                f.write(f"=" * 70 + "\n")
                f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
                f.write(f"Visited Site: {site_url}\n")
                f.write(f"URL: {request.url}\n")
                f.write(f"Content-Type: {content_type}\n")
                f.write(f"Content-Length: {len(body) if body else 0} bytes\n")
                f.write(f"=" * 70 + "\n\n")
                f.write(body_text)

            print(f"[POST] Saved POST payload to: {filename} ({len(body) if body else 0} bytes)")

        except Exception as e:
            print(f"[WARNING] Failed to save POST payload: {e}")
            import traceback
            traceback.print_exc()

    def save_network_logs(self, site_url: str):
        """Save captured Mellowtel-related network requests to JSONL file."""
        max_retries = 3
        retry_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                # Ensure output directory exists
                Path(self.output_file).parent.mkdir(parents=True, exist_ok=True)

                mellowtel_requests = 0
                total_requests = len(self.driver.requests)

                with open(self.output_file, 'a') as f:
                    for request in self.driver.requests:
                        # Check and save POST payloads if applicable
                        self.save_post_payload(request, site_url)

                        # Filter for Mellowtel-related requests only
                        if self.is_mellowtel_request(request.url):
                            request_data = self.extract_request_data(request)
                            if request_data:
                                # Add metadata about which site triggered this request
                                request_data['visited_site'] = site_url

                                # Write as JSON Lines format
                                f.write(json.dumps(request_data) + '\n')
                                mellowtel_requests += 1

                print(f"[INFO] Captured {mellowtel_requests} Mellowtel requests out of {total_requests} total requests")
                break  # Success, exit retry loop

            except RuntimeError as e:
                # Handle selenium-wire certificate dictionary iteration error
                if "dictionary changed size during iteration" in str(e):
                    if attempt < max_retries - 1:
                        print(f"[WARNING] RuntimeError (selenium-wire cert bug) on attempt {attempt + 1}/{max_retries}: {e}")
                        print(f"[INFO] Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        print(f"[ERROR] Failed to save network logs after {max_retries} attempts: {e}")
                        print("[WARNING] Some network data may be lost")
                else:
                    # Re-raise if it's a different RuntimeError
                    raise
            except Exception as e:
                print(f"[ERROR] Failed to save network logs: {e}")
                break  # Don't retry for other exceptions

    def scroll_page(self):
        """Scroll down the page a bit."""
        try:
            # Scroll down by 500 pixels
            self.driver.execute_script("window.scrollBy(0, 500);")
            print("[INFO] Scrolled down 500 pixels")
        except Exception as e:
            print(f"[WARNING] Error scrolling page: {e}")

    def close_all_tabs_except_one(self):
        """Close all tabs except one to start fresh."""
        try:
            windows = self.driver.window_handles

            if len(windows) > 1:
                print(f"[INFO] Closing {len(windows) - 1} extra tab(s)...")

                # Keep the first tab, close all others
                for i in range(len(windows) - 1, 0, -1):
                    self.driver.switch_to.window(windows[i])
                    self.driver.close()

                # Switch back to the first (remaining) tab
                self.driver.switch_to.window(windows[0])
                print(f"[SUCCESS] All extra tabs closed, now have 1 tab")
            else:
                print(f"[INFO] Only 1 tab open, no need to close tabs")

        except Exception as e:
            print(f"[WARNING] Error closing tabs: {e}")
            # Try to switch to first window if possible
            try:
                if len(self.driver.window_handles) > 0:
                    self.driver.switch_to.window(self.driver.window_handles[0])
            except:
                pass

    def visit_site(self, url: str, index: int, total: int):
        """Visit a single site and capture network activity."""
        print(f"\n[{index}/{total}] Visiting: {url}")

        # Close all tabs except one to start fresh
        self.close_all_tabs_except_one()

        # Clear previous requests and iframe tracking
        try:
            del self.driver.requests
        except RuntimeError as e:
            # Handle selenium-wire certificate dictionary iteration error
            print(f"[WARNING] RuntimeError clearing requests (selenium-wire cert bug): {e}")
            print("[INFO] Continuing anyway - this is a known selenium-wire issue")

        self.mellowtel_iframe_urls.clear()
        self.mellowtel_domains.clear()
        self.iframe_metadata.clear()

        max_retries = 3
        for nav_attempt in range(max_retries):
            try:
                # Navigate to the URL
                self.driver.get(url)
                print(f"[INFO] Page loaded.")
                break  # Success, exit retry loop

            except RuntimeError as e:
                # Handle selenium-wire certificate dictionary iteration error
                if "dictionary changed size during iteration" in str(e):
                    if nav_attempt < max_retries - 1:
                        print(f"[WARNING] RuntimeError during navigation (selenium-wire cert bug) on attempt {nav_attempt + 1}/{max_retries}: {e}")
                        print(f"[INFO] Retrying navigation...")
                        time.sleep(0.5)
                    else:
                        print(f"[ERROR] Failed to navigate after {max_retries} attempts")
                        raise
                else:
                    # Re-raise if it's a different RuntimeError
                    raise

        try:
            # Set monitoring start time
            self.monitoring_start_time = time.time()

            # Activate the IdleForest extension only once (before the first site)
            if not self.extension_activated:
                self.activate_extension()
                self.extension_activated = True
                print(f"[INFO] Extension activated. This will not be repeated for subsequent sites.")

            print(f"[INFO] Monitoring for Mellowtel iframe injection for {self.max_wait_for_iframe} seconds...")

            # Poll for Mellowtel iframe detection continuously
            elapsed = 0
            last_scroll_time = 0  # Track when we last scrolled
            total_iframes_found = 0

            while elapsed < self.max_wait_for_iframe:
                iframe_data_list = self.check_for_mellowtel_iframes()

                if iframe_data_list:
                    current_time = time.time() - self.monitoring_start_time

                    # Update metadata for all currently visible iframes
                    for iframe_data in iframe_data_list:
                        self.update_iframe_metadata(iframe_data, current_time)

                    # Extract URLs for tracking
                    iframe_urls_set = set(iframe['src'] for iframe in iframe_data_list)
                    new_iframes = iframe_urls_set - self.mellowtel_iframe_urls

                    if new_iframes:
                        self.mellowtel_iframe_urls.update(new_iframes)

                        # Extract and track domains from new iframe URLs
                        for iframe_url in new_iframes:
                            domain = self.extract_domain(iframe_url)
                            if domain:
                                self.mellowtel_domains.add(domain)
                                print(f"[INFO] Tracking new domain: {domain}")

                        total_iframes_found = len(self.mellowtel_iframe_urls)
                        print(f"[SUCCESS] New Mellowtel iframe(s) detected! Total tracking: {total_iframes_found} iframe URL(s) and {len(self.mellowtel_domains)} domain(s)")

                # Scroll every 60 seconds
                if elapsed - last_scroll_time >= 60:
                    self.scroll_page()
                    last_scroll_time = elapsed

                # Wait before next poll
                time.sleep(self.iframe_poll_interval)
                elapsed += self.iframe_poll_interval

            # Summary of monitoring period
            if total_iframes_found > 0:
                print(f"[INFO] Monitoring complete. Total {total_iframes_found} Mellowtel iframe(s) detected and tracked.")
            else:
                print(f"[WARNING] No Mellowtel iframes detected after {self.max_wait_for_iframe} seconds")
                print(f"[INFO] Waiting {self.dwell_time} seconds for any potential Mellowtel activity...")

                # Additional wait with scrolling if no iframes found
                wait_elapsed = 0
                while wait_elapsed < self.dwell_time:
                    # Scroll every 60 seconds
                    if wait_elapsed > 0 and wait_elapsed % 60 == 0:
                        self.scroll_page()

                    # Wait in small increments
                    sleep_time = min(self.iframe_poll_interval, self.dwell_time - wait_elapsed)
                    time.sleep(sleep_time)
                    wait_elapsed += sleep_time

            # Save captured network requests (filtered for Mellowtel)
            self.save_network_logs(url)

            # Save iframe metadata
            self.save_iframe_metadata(url)

        except TimeoutException:
            print(f"[WARNING] Timeout loading {url} - continuing...")
            self.save_network_logs(url)
            self.save_iframe_metadata(url)
        except Exception as e:
            print(f"[ERROR] Error visiting {url}: {e}")
            # Try to save whatever data we have
            try:
                self.save_network_logs(url)
                self.save_iframe_metadata(url)
            except:
                pass

    def move_speedtest_file(self):
        """Move speedtest JSON file from output/ to run directory if it exists."""
        try:
            # Look for speedtest file matching our timestamp
            speedtest_pattern = f'output/speedtest_{self.timestamp}.json'
            speedtest_file = Path(speedtest_pattern)

            if speedtest_file.exists():
                # Move to run directory
                dest_file = Path(self.run_dir) / 'speedtest.json'
                speedtest_file.rename(dest_file)
                print(f"[INFO] Moved speedtest results to: {dest_file}")
            else:
                print(f"[INFO] No speedtest file found for this run")
        except Exception as e:
            print(f"[WARNING] Could not move speedtest file: {e}")

    def run_experiment(self):
        """Main experiment execution."""
        print("=" * 70)
        print("Mellowtel SDK Network Analysis Tool - Targeted Capture Mode")
        print("=" * 70)
        print(f"Configuration:")
        print(f"  - Iframe detection polling: every {self.iframe_poll_interval} seconds")
        print(f"  - Max wait for iframe: {self.max_wait_for_iframe} seconds")
        print(f"  - Wait after iframe detected: {self.iframe_wait_time} seconds (5 minutes)")
        print(f"  - Fallback dwell time: {self.dwell_time} seconds (if no iframe detected)")
        print(f"  - Headless mode: {self.headless}")
        print(f"  - Disable images: {self.disable_images}")
        print(f"  - Output directory: {self.run_dir}/")
        print(f"    - Network logs: network_logs.jsonl")
        print(f"    - Iframe metadata: iframe_metadata.jsonl")
        print(f"    - POST payloads: post_payloads/")
        print(f"\nFiltering:")
        print(f"  - Only capturing requests to 'request.mellow.tel'")
        print(f"  - Only capturing requests with same domain as Mellowtel iframes")
        print(f"  - Detecting iframes with 'mllwtl' in id/data-id attributes")
        print(f"  - Tracking iframe presence duration")
        print(f"  - Saving POST payloads to request.mellow.tel with text content-type")
        print("=" * 70)

        # Load sites
        sites = self.load_sites()

        if not sites:
            print("[ERROR] No sites to visit. Exiting.")
            sys.exit(1)

        # Create run directory
        Path(self.run_dir).mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Created output directory: {self.run_dir}/")

        # Move speedtest file into run directory if it exists
        self.move_speedtest_file()

        # Initialize driver
        self.initialize_driver()

        # Get extension ID for activation
        self.get_extension_id()

        try:
            # Visit each site
            for idx, site in enumerate(sites, 1):
                self.visit_site(site, idx, len(sites))

            print("\n" + "=" * 70)
            print("Experiment completed successfully!")
            print(f"\nAll output saved to: {self.run_dir}/")
            print(f"  - Speedtest: speedtest.json")
            print(f"  - Network logs: network_logs.jsonl")
            print(f"  - Iframe metadata: iframe_metadata.jsonl")
            if self.post_payload_counter > 0:
                print(f"  - POST payloads: {self.post_payload_counter} files in post_payloads/")
            else:
                print(f"  - POST payloads: none captured (no text content-type)")
            print("=" * 70)

        except KeyboardInterrupt:
            print("\n[INFO] Experiment interrupted by user")
        except Exception as e:
            print(f"\n[ERROR] Unexpected error: {e}")
        finally:
            if self.driver:
                print("[INFO] Closing browser...")
                self.driver.quit()


def main():
    """Entry point for the script."""
    analyzer = NetworkAnalyzer()
    analyzer.run_experiment()


if __name__ == '__main__':
    main()
