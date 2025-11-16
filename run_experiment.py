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

from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, TimeoutException


class NetworkAnalyzer:
    """Main class for running the network analysis experiment."""

    def __init__(self):
        self.dwell_time = int(os.getenv('DWELL_TIME', '30'))
        self.iframe_wait_time = 300  # 5 minutes after iframe detection
        self.iframe_poll_interval = 2  # Check for iframe every 2 seconds
        self.max_wait_for_iframe = 300  # Maximum 5 minutes to wait for iframe to appear
        self.headless = os.getenv('HEADLESS', 'true').lower() == 'true'
        self.disable_images = os.getenv('DISABLE_IMAGES', 'false').lower() == 'true'
        self.sites_file = 'sites.txt'
        self.extension_path = 'IdleForest.crx'

        # Generate timestamped output filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        self.output_file = f'output/network_logs_{timestamp}.jsonl'

        self.driver = None
        self.mellowtel_iframe_urls = set()  # Track iframe URLs for filtering
        self.extension_id = None  # Store extension ID for activation
        self.extension_activated = False  # Track if extension has been activated

    def setup_chrome_options(self) -> Options:
        """Configure Chrome options for the experiment."""
        chrome_options = Options()

        # Critical flags for Docker environment
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--disable-software-rasterizer')

        # Headless mode (use old headless for better Docker compatibility)
        if self.headless:
            chrome_options.add_argument('--headless')

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
            self.driver.get("chrome://extensions/")
            time.sleep(5)

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
                self.driver.get("chrome://extensions/")
                time.sleep(2)

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
            self.driver.get(popup_url)
            time.sleep(2)
            print(f"[SUCCESS] Navigated to extension popup: {popup_url}")

            # Print the DOM of the extension popup
            try:
                popup_html = self.driver.page_source
                print("[INFO] Extension Popup DOM:")
                print("=" * 70)
                print(popup_html)
                print("=" * 70)
            except Exception as e:
                print(f"[WARNING] Could not retrieve popup DOM: {e}")

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
                for btn_info in all_buttons:
                    print(f"  Button {btn_info['index']}:")
                    print(f"    innerText: '{btn_info['innerText']}'")
                    print(f"    textContent: '{btn_info['textContent']}'")
                    print(f"    innerHTML: '{btn_info['innerHTML']}'")

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
                    self.driver.get(original_url)
                    time.sleep(2)
                    print("[INFO] Back on site")

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
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'url': request.url,
                'method': request.method,
                'request_headers': request_headers,
                'response': response_data if request.response else None,
            }
        except Exception as e:
            print(f"[WARNING] Error extracting request data: {e}")
            return None

    def check_for_mellowtel_iframes(self) -> List[str]:
        """
        Check DOM for iframes with 'mllwtl' in their id or data-id attributes.
        Returns list of iframe src URLs.
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
            iframe_urls = []

            if result:
                for iframe in result:
                    iframe_urls.append(iframe['src'])
                    print(f"[DETECTED] Mellowtel iframe: id='{iframe['id']}', data-id='{iframe['dataId']}', src='{iframe['src']}'")

            return iframe_urls

        except Exception as e:
            print(f"[WARNING] Error checking for Mellowtel iframes: {e}")
            return []

    def is_mellowtel_request(self, request_url: str) -> bool:
        """
        Check if a request is Mellowtel-related.
        Returns True if:
        - URL contains 'request.mellow.tel'
        - URL matches a tracked Mellowtel iframe URL
        """
        # Check for request.mellow.tel
        if 'request.mellow.tel' in request_url:
            return True

        # Check if URL matches any tracked iframe URLs
        for iframe_url in self.mellowtel_iframe_urls:
            if iframe_url and iframe_url in request_url:
                return True

        return False

    def save_network_logs(self, site_url: str):
        """Save captured Mellowtel-related network requests to JSONL file."""
        try:
            # Ensure output directory exists
            Path(self.output_file).parent.mkdir(parents=True, exist_ok=True)

            mellowtel_requests = 0
            total_requests = len(self.driver.requests)

            with open(self.output_file, 'a') as f:
                for request in self.driver.requests:
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
        except Exception as e:
            print(f"[ERROR] Failed to save network logs: {e}")

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
        del self.driver.requests
        self.mellowtel_iframe_urls.clear()

        try:
            # Navigate to the URL
            self.driver.get(url)
            print(f"[INFO] Page loaded.")

            # Activate the IdleForest extension only once (before the first site)
            if not self.extension_activated:
                self.activate_extension()
                self.extension_activated = True
                print(f"[INFO] Extension activated. This will not be repeated for subsequent sites.")

            print(f"[INFO] Monitoring for Mellowtel iframe injection...")

            # Poll for Mellowtel iframe detection
            iframe_detected = False
            elapsed = 0

            while elapsed < self.max_wait_for_iframe:
                iframe_urls = self.check_for_mellowtel_iframes()

                if iframe_urls:
                    # Iframe detected!
                    iframe_detected = True
                    self.mellowtel_iframe_urls.update(iframe_urls)
                    print(f"[SUCCESS] Mellowtel iframe(s) detected! Tracking {len(iframe_urls)} iframe URL(s)")
                    print(f"[INFO] Waiting {self.iframe_wait_time} seconds to capture Mellowtel activity...")

                    # Wait 5 minutes after detection
                    time.sleep(self.iframe_wait_time)
                    break

                # Wait before next poll
                time.sleep(self.iframe_poll_interval)
                elapsed += self.iframe_poll_interval

            if not iframe_detected:
                print(f"[WARNING] No Mellowtel iframe detected after {self.max_wait_for_iframe} seconds")
                print(f"[INFO] Waiting {self.dwell_time} seconds for any potential Mellowtel activity...")
                time.sleep(self.dwell_time)

            # Save captured network requests (filtered for Mellowtel)
            self.save_network_logs(url)

        except TimeoutException:
            print(f"[WARNING] Timeout loading {url} - continuing...")
            self.save_network_logs(url)
        except Exception as e:
            print(f"[ERROR] Error visiting {url}: {e}")

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
        print(f"  - Output file: {self.output_file}")
        print(f"\nFiltering:")
        print(f"  - Only capturing requests to 'request.mellow.tel'")
        print(f"  - Only capturing requests to iframes with 'mllwtl' in id/data-id")
        print("=" * 70)

        # Load sites
        sites = self.load_sites()

        if not sites:
            print("[ERROR] No sites to visit. Exiting.")
            sys.exit(1)

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
            print(f"Network logs saved to: {self.output_file}")
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
