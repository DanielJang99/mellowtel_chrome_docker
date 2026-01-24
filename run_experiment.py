#!/usr/bin/env python3
"""
Mellowtel SDK Network Analysis Tool
Captures all network activity from Chrome browsing with extension installed.
"""

import json
import logging
import logging.handlers
import os
import queue
import random
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import urlparse

from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException


# Setup async logging with QueueHandler to prevent I/O blocking
log_queue = queue.Queue(-1)  # Unlimited size
queue_handler = logging.handlers.QueueHandler(log_queue)

# Configure root logger to WARNING (suppress library INFO messages)
root_logger = logging.getLogger()
root_logger.setLevel(logging.WARNING)  # Only warnings/errors from libraries
root_logger.addHandler(queue_handler)

# Create named logger for this application (INFO level for our messages)
logger = logging.getLogger('mellowtel_analyzer')
logger.setLevel(logging.INFO)
logger.addHandler(queue_handler)
logger.propagate = False  # Prevent propagation to root logger (avoid duplicate messages)

# Setup console handler for the queue listener
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('[%(levelname)s] %(message)s')
console_handler.setFormatter(formatter)

# Start queue listener in background thread
queue_listener = logging.handlers.QueueListener(log_queue, console_handler, respect_handler_level=True)
queue_listener.start()

# Suppress verbose third-party libraries explicitly
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('selenium_wire').setLevel(logging.WARNING)
logging.getLogger('seleniumwire').setLevel(logging.WARNING)
logging.getLogger('mitmproxy').setLevel(logging.WARNING)
logging.getLogger('h11').setLevel(logging.WARNING)
logging.getLogger('hpack').setLevel(logging.WARNING)


class FileWriterQueue:
    """Thread-safe queue for async file writes to prevent I/O blocking."""

    def __init__(self):
        self.write_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._worker, daemon=False)
        self.shutdown_event = threading.Event()
        self.worker_thread.start()
        logger.info("FileWriterQueue worker thread started")

    def _worker(self):
        """Background worker that processes write tasks from the queue."""
        while not self.shutdown_event.is_set() or not self.write_queue.empty():
            try:
                task = self.write_queue.get(timeout=0.1)
                if task is None:  # Shutdown signal
                    break

                # Execute the write task
                filepath, content, mode = task
                try:
                    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
                    with open(filepath, mode) as f:
                        f.write(content)
                except Exception as e:
                    logger.error(f"Failed to write to {filepath}: {e}")
                finally:
                    self.write_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in FileWriterQueue worker: {e}")

    def enqueue_write(self, filepath: str, content: str, mode: str = 'a'):
        """Enqueue a file write operation."""
        self.write_queue.put((filepath, content, mode))

    def shutdown(self, timeout: float = 30.0):
        """Shutdown the worker thread and wait for queue to drain."""
        logger.info(f"Shutting down FileWriterQueue (queue size: {self.write_queue.qsize()})...")

        # Signal shutdown
        self.shutdown_event.set()

        # Wait for queue to drain
        try:
            self.write_queue.join()
            logger.info("FileWriterQueue drained successfully")
        except Exception as e:
            logger.warning(f"Error draining queue: {e}")

        # Send termination signal
        self.write_queue.put(None)

        # Wait for worker thread
        self.worker_thread.join(timeout=timeout)
        if self.worker_thread.is_alive():
            logger.warning("FileWriterQueue worker thread did not terminate in time")
        else:
            logger.info("FileWriterQueue worker thread terminated")


class NetworkAnalyzer:
    """Main class for running the network analysis experiment."""

    def __init__(self):
        # Initialize async file writer queue
        self.file_writer = FileWriterQueue()

        self.dwell_time = int(os.getenv('DWELL_TIME', '30'))
        self.iframe_poll_interval = 2  # Check for iframe every 2 seconds
        self.max_wait_for_iframe = 300  # Maximum 5 minutes to wait for iframe to appear
        self.headless = os.getenv('HEADLESS', 'false').lower() == 'true'
        self.disable_images = os.getenv('DISABLE_IMAGES', 'false').lower() == 'true'
        self.sites_file = 'sites.txt'

        # Randomly select extension from available options
        available_extensions = ['IdleForest.crx', 'SupportWithMellowtel.crx']
        self.extension_name = random.choice(available_extensions)
        self.extension_path = os.path.join('crx_files', self.extension_name)
        logger.info(f"Selected extension: {self.extension_name}")

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

        # Track requests per iframe/domain for aggregated writing
        self.iframe_requests = {}  # {iframe_src: {'domain': str, 'requests': [request_data]}}
        self.current_visible_iframes = set()  # Currently visible iframe URLs
        self.last_processed_request_index = 0  # Track which requests we've already processed

    def setup_chrome_options(self) -> Options:
        """Configure Chrome options for the experiment."""
        chrome_options = Options()

        # Critical flags for Docker environment
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--disable-software-rasterizer')

        chrome_options.page_load_strategy = 'eager'

        # Headless mode (only use if explicitly enabled, Xvfb is preferred to avoid HeadlessChrome user agent)
        if self.headless:
            chrome_options.add_argument('--headless')
            logger.info("Using headless mode (User-Agent will show 'HeadlessChrome')")
        else:
            logger.info("Using Xvfb virtual display (User-Agent will show normal 'Chrome')")

        # Remote debugging (helps with stability)
        chrome_options.add_argument('--remote-debugging-port=9222')

        # Window size
        chrome_options.add_argument('--window-size=1920,1080')

        # Set unique user data directory to avoid conflicts
        import tempfile
        user_data_dir = tempfile.mkdtemp(prefix='chrome_profile_')
        chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
        logger.info(f"Using user data directory: {user_data_dir}")

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
        if os.path.exists(self.extension_path):
            try:
                chrome_options.add_extension(self.extension_path)
                logger.info(f"Extension loaded from: {self.extension_path}")
            except Exception as e:
                logger.warning(f"Failed to load extension: {e}")
                logger.warning("Continuing without extension.")
        else:
            logger.warning(f"Extension file not found: {self.extension_path}")
            logger.warning("Continuing without extension. Network capture will only include page requests.")

        # Logging for debugging
        chrome_options.add_argument('--enable-logging')
        chrome_options.add_argument('--v=1')

        return chrome_options

    def load_sites(self) -> List[str]:
        """Load list of URLs from sites.txt and randomize their order."""
        try:
            with open(self.sites_file, 'r') as f:
                sites = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            logger.info(f"Loaded {len(sites)} sites from {self.sites_file}")

            # Randomize the order of sites
            random.shuffle(sites)
            logger.info(f"Randomized site visit order")

            return sites
        except FileNotFoundError:
            logger.error(f"Sites file not found: {self.sites_file}")
            sys.exit(1)

    def initialize_driver(self):
        """Initialize the Selenium WebDriver with selenium-wire."""
        logger.info("Initializing Chrome WebDriver...")

        # Check Chrome version
        try:
            import subprocess
            chrome_version = subprocess.check_output(['google-chrome', '--version'],
                                                     stderr=subprocess.STDOUT).decode().strip()
            logger.info(f"{chrome_version}")
        except Exception as e:
            logger.warning(f"Could not determine Chrome version: {e}")

        chrome_options = self.setup_chrome_options()

        # Selenium-wire options for network interception
        seleniumwire_options = {
            'disable_encoding': True,  # Don't decode responses
        }

        try:
            logger.info("Starting Chrome with selenium-wire...")
            self.driver = webdriver.Chrome(
                options=chrome_options,
                seleniumwire_options=seleniumwire_options
            )
            self.driver.set_page_load_timeout(60)
            logger.info("WebDriver initialized successfully")
        except WebDriverException as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            logger.debug("\n[DEBUG]Troubleshooting tips:")
            logger.debug("  1. Check Chrome is installed: google-chrome --version")
            logger.debug("  2. Check ChromeDriver is installed: chromedriver --version")
            logger.debug("  3. Ensure versions match")
            logger.debug("  4. Try running with HEADLESS=true")
            logger.debug("  5. Check Docker shared memory (shm_size in docker-compose.yml)")
            sys.exit(1)

    def reinitialize_driver(self, reactivate_extension: bool = False) -> bool:
        """
        Reinitialize the Chrome driver after a timeout or crash.
        Returns True if successful, False otherwise.
        """
        try:
            logger.info("Reinitializing Chrome driver...")

            # Quit existing driver if it exists
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("Closed existing driver")
                except Exception as e:
                    logger.warning(f"Error closing driver: {e}")

            self.driver = None

            # Reinitialize driver
            self.initialize_driver()

            # Get extension ID
            self.get_extension_id()

            # Optionally reactivate extension if it was previously activated
            if reactivate_extension:
                logger.info("Reactivating extension after reinitialization...")
                self.activate_extension()
                self.extension_activated = True

            logger.info("[SUCCESS]Driver reinitialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to reinitialize driver: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_extension_id(self) -> str:
        """
        Get the extension ID for IdleForest extension.
        Returns the extension ID or None if not found.
        """
        try:
            logger.info("Getting extension ID...")

            # Navigate to chrome://extensions
            max_retries = 3
            for ext_attempt in range(max_retries):
                try:
                    self.driver.get("chrome://extensions/")
                    time.sleep(5)
                    break
                except TimeoutException as e:
                    logger.error(f"Timeout navigating to extensions page (attempt {ext_attempt + 1}/{max_retries}): {e}")
                    if ext_attempt < max_retries - 1:
                        logger.info(f"Retrying...")
                        time.sleep(1)
                    else:
                        logger.error(f"Failed to navigate to extensions page after timeout")
                        raise
                except RuntimeError as e:
                    if "dictionary changed size during iteration" in str(e):
                        if ext_attempt < max_retries - 1:
                            logger.warning(f"RuntimeError navigating to extensions page (selenium-wire cert bug)")
                            logger.info(f"Retrying...")
                            time.sleep(0.5)
                        else:
                            logger.error(f"Failed to navigate to extensions page")
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
                logger.info(f"Found extension: {ext['name']} (ID: {ext['id']})")
                # Look for IdleForest or Idle Forest
                if 'idle' in ext['name'].lower() and 'forest' in ext['name'].lower():
                    self.extension_id = ext['id']
                    logger.info(f"[SUCCESS]Found IdleForest extension ID: {self.extension_id}")

                    # Enable the extension if it's not already enabled
                    self.enable_extension(ext['id'])

                    return self.extension_id

            # If not found by name, just use the first extension (assuming it's the only one)
            if extensions and len(extensions) > 0:
                self.extension_id = extensions[0]['id']
                logger.warning(f"Could not find 'IdleForest' by name. Using first extension: {self.extension_id}")

                # Enable the extension
                self.enable_extension(extensions[0]['id'])

                return self.extension_id

            logger.warning("No extensions found")
            return None

        except Exception as e:
            logger.warning(f"Error getting extension ID: {e}")
            return None

    def enable_extension(self, extension_id: str):
        """
        Enable the extension via the toggle on chrome://extensions page.
        """
        try:
            logger.info(f"Ensuring extension is enabled...")

            # Navigate to chrome://extensions if not already there
            if not self.driver.current_url.startswith('chrome://extensions'):
                max_retries = 3
                for enable_attempt in range(max_retries):
                    try:
                        self.driver.get("chrome://extensions/")
                        time.sleep(2)
                        break
                    except TimeoutException as e:
                        logger.error(f"Timeout navigating to extensions for enabling (attempt {enable_attempt + 1}/{max_retries}): {e}")
                        if enable_attempt < max_retries - 1:
                            logger.info(f"Retrying...")
                            time.sleep(1)
                        else:
                            logger.error(f"Failed to navigate to extensions page for enabling after timeout")
                            raise
                    except RuntimeError as e:
                        if "dictionary changed size during iteration" in str(e):
                            if enable_attempt < max_retries - 1:
                                logger.warning(f"RuntimeError navigating to extensions (selenium-wire cert bug)")
                                logger.info(f"Retrying...")
                                time.sleep(0.5)
                            else:
                                logger.error(f"Failed to navigate to extensions page for enabling")
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
                logger.info(f"[SUCCESS]Extension is now enabled")
                time.sleep(1)
            else:
                logger.info(f"Extension toggle state: {result}")

        except Exception as e:
            logger.warning(f"Error enabling extension: {e}")

    def activate_extension(self):
        """
        Activate the extension by navigating to its popup URL.
        - IdleForest: Clicks "Start Planting" button
        - SupportWithMellowtel: No interaction needed, popup opens automatically
        """
        if not self.extension_id:
            logger.warning("Extension ID not available. Skipping activation.")
            return False

        try:
            logger.info(f"Activating {self.extension_name} extension...")

            # Save current URL to return to later
            original_url = self.driver.current_url
            popup_url = f"chrome-extension://{self.extension_id}/popup.html"

            # Open extension popup
            logger.info(f"Opening extension popup...")
            max_retries = 3
            for popup_attempt in range(max_retries):
                try:
                    self.driver.get(popup_url)
                    time.sleep(2)
                    logger.info(f"[SUCCESS]Navigated to extension popup: {popup_url}")
                    break  # Success
                except TimeoutException as e:
                    logger.error(f"Timeout opening popup (attempt {popup_attempt + 1}/{max_retries}): {e}")
                    if popup_attempt < max_retries - 1:
                        logger.info(f"Retrying...")
                        time.sleep(1)
                    else:
                        logger.error(f"Failed to open popup after timeout")
                        raise
                except RuntimeError as e:
                    if "dictionary changed size during iteration" in str(e):
                        if popup_attempt < max_retries - 1:
                            logger.warning(f"RuntimeError opening popup (selenium-wire cert bug) on attempt {popup_attempt + 1}/{max_retries}")
                            logger.info(f"Retrying...")
                            time.sleep(0.5)
                        else:
                            logger.error(f"Failed to open popup after {max_retries} attempts")
                            return False
                    else:
                        raise

            # Handle extension-specific activation
            if 'IdleForest' in self.extension_name:
                # IdleForest requires clicking "Start Planting" button
                logger.info("Looking for 'Start Planting' button...")

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
                    logger.info(f"Found {len(all_buttons)} button(s) in popup:")

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
                        logger.info("[SUCCESS]Found 'Start Planting' button!")
                        logger.info("Clicking 'Start Planting' button...")

                        # Click the button
                        self.driver.execute_script("arguments[0].click();", start_button)
                        time.sleep(2)
                        logger.info("[SUCCESS]Clicked 'Start Planting' button")

                        # Navigate back to original site
                        logger.info(f"Navigating back to site: {original_url}")
                        max_retries = 3
                        for back_attempt in range(max_retries):
                            try:
                                self.driver.get(original_url)
                                time.sleep(2)
                                logger.info("Back on site")
                                break
                            except TimeoutException as e:
                                logger.error(f"Timeout navigating back (attempt {back_attempt + 1}/{max_retries}): {e}")
                                if back_attempt < max_retries - 1:
                                    logger.info(f"Retrying...")
                                    time.sleep(1)
                                else:
                                    logger.error(f"Failed to navigate back after timeout")
                                    raise
                            except RuntimeError as e:
                                if "dictionary changed size during iteration" in str(e):
                                    if back_attempt < max_retries - 1:
                                        logger.warning(f"RuntimeError navigating back (selenium-wire cert bug)")
                                        logger.info(f"Retrying...")
                                        time.sleep(0.5)
                                    else:
                                        logger.error(f"Failed to navigate back after clicking button")
                                        return False
                                else:
                                    raise

                        return True
                    else:
                        logger.error("'Start Planting' button not found in popup!")
                        logger.error("Extension activation failed. Exiting script.")
                        sys.exit(1)

                except Exception as e:
                    logger.error(f"Error finding/clicking 'Start Planting' button: {e}")
                    import traceback
                    traceback.print_exc()
                    logger.error("Extension activation failed. Exiting script.")
                    sys.exit(1)

            else:
                # SupportWithMellowtel: Just wait for popup to appear, no interaction needed
                logger.info("SupportWithMellowtel popup opened. No interaction required.")
                time.sleep(3)  # Wait for popup to fully load

                # Navigate back to original site
                logger.info(f"Navigating back to site: {original_url}")
                max_retries = 3
                for back_attempt in range(max_retries):
                    try:
                        self.driver.get(original_url)
                        time.sleep(2)
                        logger.info("Back on site")
                        break
                    except TimeoutException as e:
                        logger.error(f"Timeout navigating back (attempt {back_attempt + 1}/{max_retries}): {e}")
                        if back_attempt < max_retries - 1:
                            logger.info(f"Retrying...")
                            time.sleep(1)
                        else:
                            logger.error(f"Failed to navigate back after timeout")
                            raise
                    except RuntimeError as e:
                        if "dictionary changed size during iteration" in str(e):
                            if back_attempt < max_retries - 1:
                                logger.warning(f"RuntimeError navigating back (selenium-wire cert bug)")
                                logger.info(f"Retrying...")
                                time.sleep(0.5)
                            else:
                                logger.error(f"Failed to navigate back")
                                return False
                        else:
                            raise

                return True

        except Exception as e:
            logger.error(f"Error activating extension: {e}")
            import traceback
            traceback.print_exc()
            logger.error("Extension activation failed. Exiting script.")
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
            logger.warning(f"Error extracting request data: {e}")
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
            logger.warning(f"Error checking for Mellowtel iframes: {e}")
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

            logger.info(f"Saved metadata for {len(self.iframe_metadata)} iframe(s)")
        except Exception as e:
            logger.error(f"Failed to save iframe metadata: {e}")

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
                logger.warning(f"POST request to request.mellow.tel has no body")
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

            logger.info(f"[POST]Saved POST payload to: {filename} ({len(body) if body else 0} bytes)")

        except Exception as e:
            logger.warning(f"Failed to save POST payload: {e}")
            import traceback
            traceback.print_exc()

    def process_new_requests(self, site_url: str):
        """
        Process new requests since last check and categorize by iframe.
        Stores requests in memory grouped by iframe URL.
        """
        try:
            total_requests = len(self.driver.requests)

            # Only process new requests since last check
            if self.last_processed_request_index >= total_requests:
                return  # No new requests

            new_request_count = 0

            # Process only new requests
            for i in range(self.last_processed_request_index, total_requests):
                try:
                    request = self.driver.requests[i]

                    # Check and save POST payloads if applicable
                    self.save_post_payload(request, site_url)

                    # Filter for Mellowtel-related requests only
                    if self.is_mellowtel_request(request.url):
                        request_data = self.extract_request_data(request)
                        if request_data:
                            # Add metadata about which site triggered this request
                            request_data['visited_site'] = site_url

                            # Determine which iframe this request belongs to
                            request_domain = self.extract_domain(request.url)

                            # Check if it's a request to request.mellow.tel
                            if 'request.mellow.tel' in request.url:
                                # Use Referer header to match to specific iframe
                                referer = request_data['request_headers'].get('Referer') or request_data['request_headers'].get('referer')

                                if referer:
                                    referer_domain = self.extract_domain(referer)
                                    matched = False

                                    # Find matching iframe by domain
                                    for iframe_url in self.current_visible_iframes:
                                        iframe_domain = self.extract_domain(iframe_url)
                                        if referer_domain == iframe_domain:
                                            # Attribute to this specific iframe only
                                            if iframe_url not in self.iframe_requests:
                                                self.iframe_requests[iframe_url] = {
                                                    'domain': iframe_domain,
                                                    'requests': []
                                                }
                                            self.iframe_requests[iframe_url]['requests'].append(request_data)
                                            new_request_count += 1
                                            matched = True
                                            break

                                    if not matched:
                                        logger.warning(f"Could not match Referer domain '{referer_domain}' to any visible iframe")
                                else:
                                    # Fallback: no referer, attribute to all current iframes (original behavior)
                                    logger.warning(f"No Referer header for request.mellow.tel request, attributing to all iframes")
                                    for iframe_url in self.current_visible_iframes:
                                        if iframe_url not in self.iframe_requests:
                                            iframe_domain = self.extract_domain(iframe_url)
                                            self.iframe_requests[iframe_url] = {
                                                'domain': iframe_domain,
                                                'requests': []
                                            }
                                        self.iframe_requests[iframe_url]['requests'].append(request_data.copy())
                                        new_request_count += 1
                            else:
                                # Match request to iframe by domain
                                for iframe_url in self.current_visible_iframes:
                                    iframe_domain = self.extract_domain(iframe_url)
                                    if request_domain == iframe_domain:
                                        if iframe_url not in self.iframe_requests:
                                            self.iframe_requests[iframe_url] = {
                                                'domain': iframe_domain,
                                                'requests': []
                                            }
                                        self.iframe_requests[iframe_url]['requests'].append(request_data)
                                        new_request_count += 1
                                        break

                except RuntimeError as e:
                    if "dictionary changed size during iteration" in str(e):
                        # Skip this request and continue
                        logger.warning(f"RuntimeError processing request {i}, skipping")
                        continue
                    else:
                        raise

            # Update the last processed index
            self.last_processed_request_index = total_requests

            if new_request_count > 0:
                logger.info(f"Processed {new_request_count} new Mellowtel request(s)")

        except Exception as e:
            logger.error(f"Failed to process new requests: {e}")

    def write_iframe_requests(self, iframe_url: str):
        """
        Write all aggregated requests for a specific iframe to the output file.
        Called when an iframe disappears from the DOM.
        Uses async queue to prevent I/O blocking.
        """
        try:
            if iframe_url not in self.iframe_requests:
                return

            iframe_data = self.iframe_requests[iframe_url]
            request_count = len(iframe_data['requests'])

            if request_count > 0:
                # Build content in memory
                content_lines = []
                for request_data in iframe_data['requests']:
                    # Add iframe attribution
                    request_data['iframe_src'] = iframe_url
                    request_data['iframe_domain'] = iframe_data['domain']

                    # Add as JSON Lines format
                    content_lines.append(json.dumps(request_data) + '\n')

                # Enqueue the write (non-blocking)
                content = ''.join(content_lines)
                self.file_writer.enqueue_write(self.output_file, content, mode='a')

                logger.info(f"[WRITE]Queued {request_count} requests for iframe: {iframe_data['domain']}")

            # Remove from memory
            del self.iframe_requests[iframe_url]

        except Exception as e:
            logger.error(f"Failed to queue iframe requests: {e}")

    def write_all_remaining_requests(self):
        """
        Write all remaining aggregated requests to file.
        Called at the end of site monitoring when iframes may still be visible.
        Uses async queue to prevent I/O blocking.
        """
        try:
            if not self.iframe_requests:
                logger.info("No remaining requests to write")
                return

            total_queued = 0
            for iframe_url, iframe_data in list(self.iframe_requests.items()):
                request_count = len(iframe_data['requests'])

                if request_count > 0:
                    # Build content in memory
                    content_lines = []
                    for request_data in iframe_data['requests']:
                        # Add iframe attribution
                        request_data['iframe_src'] = iframe_url
                        request_data['iframe_domain'] = iframe_data['domain']

                        # Add as JSON Lines format
                        content_lines.append(json.dumps(request_data) + '\n')

                    # Enqueue the write (non-blocking)
                    content = ''.join(content_lines)
                    self.file_writer.enqueue_write(self.output_file, content, mode='a')

                    total_queued += request_count
                    logger.info(f"[WRITE]Queued {request_count} remaining requests for iframe: {iframe_data['domain']}")

            # Clear all
            self.iframe_requests.clear()
            logger.info(f"Total remaining requests queued: {total_queued}")

        except Exception as e:
            logger.error(f"Failed to queue remaining requests: {e}")

    def scroll_page(self):
        """Scroll down the page a bit."""
        try:
            # Scroll down by 500 pixels
            self.driver.execute_script("window.scrollBy(0, 500);")
            logger.info("Scrolled down 500 pixels")
        except Exception as e:
            logger.warning(f"Error scrolling page: {e}")

    def close_all_tabs_except_one(self):
        """Close all tabs except one to start fresh."""
        try:
            windows = self.driver.window_handles

            if len(windows) > 1:
                logger.info(f"Closing {len(windows) - 1} extra tab(s)...")

                # Keep the first tab, close all others
                for i in range(len(windows) - 1, 0, -1):
                    self.driver.switch_to.window(windows[i])
                    self.driver.close()

                # Switch back to the first (remaining) tab
                self.driver.switch_to.window(windows[0])
                logger.info(f"[SUCCESS]All extra tabs closed, now have 1 tab")
            else:
                logger.info(f"Only 1 tab open, no need to close tabs")

        except Exception as e:
            logger.warning(f"Error closing tabs: {e}")
            # Try to switch to first window if possible
            try:
                if len(self.driver.window_handles) > 0:
                    self.driver.switch_to.window(self.driver.window_handles[0])
            except:
                pass

    def visit_site(self, url: str, index: int, total: int):
        """Visit a single site and capture network activity."""
        logger.info(f"\n[{index}/{total}] Visiting: {url}")

        # Timeout retry loop - reinitialize driver on timeout
        max_timeout_retries = 2
        for timeout_attempt in range(max_timeout_retries + 1):
            try:
                # Track if we need to reactivate extension after reinitialization
                need_reactivation = self.extension_activated

                # If this is a retry attempt, reinitialize the driver
                if timeout_attempt > 0:
                    logger.info(f"Timeout retry attempt {timeout_attempt + 1}/{max_timeout_retries + 1} for {url}")
                    if not self.reinitialize_driver(reactivate_extension=need_reactivation):
                        logger.error(f"Failed to reinitialize driver on attempt {timeout_attempt + 1}")
                        if timeout_attempt < max_timeout_retries:
                            continue
                        else:
                            logger.error(f"Skipping site {url} after {max_timeout_retries + 1} failed attempts")
                            return

                # Close all tabs except one to start fresh
                self.close_all_tabs_except_one()

                # Clear previous requests and iframe tracking
                try:
                    del self.driver.requests
                except RuntimeError as e:
                    # Handle selenium-wire certificate dictionary iteration error
                    logger.warning(f"RuntimeError clearing requests (selenium-wire cert bug): {e}")
                    logger.info("Continuing anyway - this is a known selenium-wire issue")

                self.mellowtel_iframe_urls.clear()
                self.mellowtel_domains.clear()
                self.iframe_metadata.clear()
                self.iframe_requests.clear()
                self.current_visible_iframes.clear()
                self.last_processed_request_index = 0

                # Navigation with RuntimeError retry logic
                max_retries = 3
                nav_success = False
                for nav_attempt in range(max_retries):
                    try:
                        # Navigate to the URL
                        self.driver.get(url)
                        logger.info(f"Page loaded.")
                        nav_success = True
                        break  # Success, exit retry loop

                    except RuntimeError as e:
                        # Handle selenium-wire certificate dictionary iteration error
                        if "dictionary changed size during iteration" in str(e):
                            if nav_attempt < max_retries - 1:
                                logger.warning(f"RuntimeError during navigation (selenium-wire cert bug) on attempt {nav_attempt + 1}/{max_retries}: {e}")
                                logger.info(f"Retrying navigation...")
                                time.sleep(0.5)
                            else:
                                logger.error(f"Failed to navigate after {max_retries} attempts")
                                raise
                        else:
                            # Re-raise if it's a different RuntimeError
                            raise
                    except TimeoutException:
                        # Re-raise TimeoutException to be caught by outer loop
                        raise

                if not nav_success:
                    logger.error(f"Failed to navigate to {url}")
                    return

                # Continue with the rest of the site visit logic
                self._process_site_after_navigation(url)

                # If we got here, the site visit was successful
                logger.info(f"[SUCCESS]Successfully completed visit to {url}")
                return

            except TimeoutException as e:
                logger.error(f"Timeout visiting {url} (attempt {timeout_attempt + 1}/{max_timeout_retries + 1}): {e}")
                if timeout_attempt < max_timeout_retries:
                    logger.info(f"Will reinitialize driver and retry...")
                else:
                    logger.error(f"All retry attempts exhausted for {url}. Skipping site.")
                    # Try to save whatever data we have
                    try:
                        self.process_new_requests(url)
                        self.write_all_remaining_requests()
                        self.save_iframe_metadata(url)
                    except:
                        pass
                    return
            except Exception as e:
                logger.error(f"Unexpected error visiting {url}: {e}")
                # Try to save whatever data we have
                try:
                    self.process_new_requests(url)
                    self.write_all_remaining_requests()
                    self.save_iframe_metadata(url)
                except:
                    pass
                return

    def _process_site_after_navigation(self, url: str):
        """Process site after successful navigation. Extracted from visit_site for clarity."""
        try:
            # Set monitoring start time
            self.monitoring_start_time = time.time()

            # Activate the IdleForest extension only once (before the first site)
            if not self.extension_activated:
                self.activate_extension()
                self.extension_activated = True
                logger.info(f"Extension activated. This will not be repeated for subsequent sites.")

            logger.info(f"Monitoring for Mellowtel iframe injection for {self.max_wait_for_iframe} seconds...")

            # Poll for Mellowtel iframe detection continuously
            elapsed = 0
            last_scroll_time = 0  # Track when we last scrolled
            total_iframes_found = 0

            while elapsed < self.max_wait_for_iframe:
                iframe_data_list = self.check_for_mellowtel_iframes()

                # Get currently visible iframe URLs
                currently_visible = set()
                if iframe_data_list:
                    current_time = time.time() - self.monitoring_start_time

                    # Update metadata for all currently visible iframes
                    for iframe_data in iframe_data_list:
                        self.update_iframe_metadata(iframe_data, current_time)

                    # Extract URLs for currently visible iframes
                    currently_visible = set(iframe['src'] for iframe in iframe_data_list)

                    # Detect new iframes
                    new_iframes = currently_visible - self.mellowtel_iframe_urls

                    if new_iframes:
                        self.mellowtel_iframe_urls.update(new_iframes)

                        # Extract and track domains from new iframe URLs
                        for iframe_url in new_iframes:
                            domain = self.extract_domain(iframe_url)
                            if domain:
                                self.mellowtel_domains.add(domain)
                                logger.info(f"Tracking new domain: {domain}")

                        total_iframes_found = len(self.mellowtel_iframe_urls)
                        logger.info(f"[SUCCESS]New Mellowtel iframe(s) detected! Total tracking: {total_iframes_found} iframe URL(s) and {len(self.mellowtel_domains)} domain(s)")

                # Detect disappeared iframes (iframes that were visible but are no longer)
                disappeared_iframes = self.current_visible_iframes - currently_visible
                if disappeared_iframes:
                    # Process any remaining new requests before writing
                    self.process_new_requests(url)

                    for iframe_url in disappeared_iframes:
                        logger.info(f"[IFRAME]Iframe disappeared: {self.extract_domain(iframe_url)}")
                        # Write requests for this iframe to file
                        self.write_iframe_requests(iframe_url)

                # Update current visible iframes
                self.current_visible_iframes = currently_visible

                # Process new requests on each iteration
                self.process_new_requests(url)

                # Scroll every 60 seconds
                if elapsed - last_scroll_time >= 60:
                    self.scroll_page()
                    last_scroll_time = elapsed

                # Wait before next poll
                time.sleep(self.iframe_poll_interval)
                elapsed = int(time.time() - self.monitoring_start_time)

            # Summary of monitoring period
            if total_iframes_found > 0:
                logger.info(f"Monitoring complete. Total {total_iframes_found} Mellowtel iframe(s) detected and tracked.")
            else:
                logger.warning(f"No Mellowtel iframes detected after {self.max_wait_for_iframe} seconds")
                logger.info(f"Waiting {self.dwell_time} seconds for any potential Mellowtel activity...")

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

            # Process any final new requests
            logger.info(f"Processing final requests...")
            self.process_new_requests(url)

            # Write all remaining requests to file (for iframes still visible)
            self.write_all_remaining_requests()

            # Save iframe metadata
            self.save_iframe_metadata(url)

        except TimeoutException:
            # Re-raise TimeoutException to be handled by outer retry loop in visit_site()
            logger.warning(f"Timeout during site monitoring - will retry with driver reinitialization")
            raise
        except Exception as e:
            logger.error(f"Error during site monitoring {url}: {e}")
            # Try to save whatever data we have
            try:
                self.process_new_requests(url)
                self.write_all_remaining_requests()
                self.save_iframe_metadata(url)
            except:
                pass
            # Re-raise to be handled by visit_site()
            raise

    def run_experiment(self):
        """Main experiment execution."""
        logger.info("=" * 70)
        logger.info("Mellowtel SDK Network Analysis Tool - Targeted Capture Mode")
        logger.info("=" * 70)
        logger.info(f"Configuration:")
        logger.info(f"  - Iframe detection polling: every {self.iframe_poll_interval} seconds")
        logger.info(f"  - Max wait for iframe: {self.max_wait_for_iframe} seconds")
        logger.info(f"  - Fallback dwell time: {self.dwell_time} seconds (if no iframe detected)")
        logger.info(f"  - Headless mode: {self.headless}")
        logger.info(f"  - Disable images: {self.disable_images}")
        logger.info(f"  - Output directory: {self.run_dir}/")
        logger.info(f"    - Network logs: network_logs.jsonl")
        logger.info(f"    - Iframe metadata: iframe_metadata.jsonl")
        logger.info(f"    - POST payloads: post_payloads/")
        logger.info(f"\nFiltering & Aggregation:")
        logger.info(f"  - Only capturing requests to 'request.mellow.tel'")
        logger.info(f"  - Only capturing requests with same domain as Mellowtel iframes")
        logger.info(f"  - Detecting iframes with 'mllwtl' in id/data-id attributes")
        logger.info(f"  - Tracking iframe presence duration")
        logger.info(f"  - Categorizing requests by iframe/domain in real-time")
        logger.info(f"  - Writing to file when iframe disappears from DOM")
        logger.info(f"  - Saving POST payloads to request.mellow.tel with text content-type")
        logger.info("=" * 70)

        # Load sites
        sites = self.load_sites()

        if not sites:
            logger.error("No sites to visit. Exiting.")
            sys.exit(1)

        # Create run directory
        Path(self.run_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Created output directory: {self.run_dir}/")


        # Initialize driver with retry logic for TimeoutException
        max_init_retries = 2
        init_success = False

        for init_attempt in range(max_init_retries + 1):
            try:
                if init_attempt == 0:
                    # First attempt - normal initialization
                    logger.info("Initializing Chrome driver...")
                    self.initialize_driver()
                    self.get_extension_id()
                else:
                    # Retry attempt - full reinitialization
                    logger.info(f"Initialization attempt {init_attempt + 1}/{max_init_retries + 1} after timeout")
                    if not self.reinitialize_driver(reactivate_extension=False):
                        logger.error(f"Reinitialization failed on attempt {init_attempt + 1}")
                        continue

                init_success = True
                logger.info("[SUCCESS]Driver initialization completed")
                break

            except TimeoutException as e:
                logger.error(f"Timeout during initialization (attempt {init_attempt + 1}/{max_init_retries + 1}): {e}")
                if init_attempt < max_init_retries:
                    logger.info(f"Retrying initialization...")
                else:
                    logger.error(f"All initialization attempts exhausted. Cannot continue.")
                    sys.exit(1)
            except Exception as e:
                logger.error(f"Unexpected error during initialization: {e}")
                import traceback
                traceback.print_exc()
                if init_attempt < max_init_retries:
                    logger.info(f"Retrying initialization...")
                else:
                    logger.error(f"All initialization attempts exhausted. Cannot continue.")
                    sys.exit(1)

        if not init_success:
            logger.error("Failed to initialize driver after all retries")
            sys.exit(1)

        # Track experiment start time for 55-minute timeout
        experiment_start_time = time.time()

        try:
            # Visit each site
            for idx, site in enumerate(sites, 1):
                # Check if more than 55 minutes have elapsed
                elapsed_minutes = (time.time() - experiment_start_time) / 60
                if elapsed_minutes > 55:
                    logger.info(f"\n55 minutes have elapsed ({elapsed_minutes:.1f} minutes). Finishing experiment early.")
                    logger.info(f"Visited {idx - 1}/{len(sites)} sites before timeout.")
                    break

                self.visit_site(site, idx, len(sites))

            logger.info("\n" + "=" * 70)
            logger.info("Experiment completed successfully!")
            logger.info(f"\nAll output saved to: {self.run_dir}/")
            logger.info(f"  - Speedtest: speedtest.json")
            logger.info(f"  - Network logs: network_logs.jsonl")
            logger.info(f"  - Iframe metadata: iframe_metadata.jsonl")
            if self.post_payload_counter > 0:
                logger.info(f"  - POST payloads: {self.post_payload_counter} files in post_payloads/")
            else:
                logger.info(f"  - POST payloads: none captured (no text content-type)")
            logger.info("=" * 70)

        except KeyboardInterrupt:
            logger.info("\nExperiment interrupted by user")
        except Exception as e:
            logger.error(f"\nUnexpected error: {e}")
        finally:
            # Shutdown file writer queue to ensure all writes complete
            logger.info("Shutting down file writer queue...")
            self.file_writer.shutdown()

            if self.driver:
                logger.info("Closing browser...")
                self.driver.quit()


def main():
    """Entry point for the script."""
    try:
        analyzer = NetworkAnalyzer()
        analyzer.run_experiment()
    finally:
        # Shutdown logging queue listener
        logger.info("Shutting down logging queue...")
        queue_listener.stop()


if __name__ == '__main__':
    main()
