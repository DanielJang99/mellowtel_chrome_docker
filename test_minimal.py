#!/usr/bin/env python3
"""
Minimal Chrome test - simplest possible Selenium setup.
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import sys

print("Testing minimal Chrome setup...")

# Minimal Chrome options for Docker
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')

print("Chrome options configured:")
for arg in options.arguments:
    print(f"  {arg}")

try:
    print("\nStarting Chrome WebDriver...")
    driver = webdriver.Chrome(options=options)

    print("✓ Chrome started successfully!")

    print("\nTesting navigation to about:blank...")
    driver.get("about:blank")
    print(f"✓ Page title: {driver.title}")

    print("\nTesting navigation to example.com...")
    driver.get("https://example.com")
    print(f"✓ Page title: {driver.title}")

    driver.quit()
    print("\n✓ All tests passed!")
    sys.exit(0)

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
