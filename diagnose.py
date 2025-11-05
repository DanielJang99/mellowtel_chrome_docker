#!/usr/bin/env python3
"""
Diagnostic script to check Chrome and ChromeDriver setup.
Run this inside the Docker container to troubleshoot issues.
"""

import subprocess
import sys


def run_command(cmd, description):
    """Run a command and print the result."""
    print(f"\n{'='*70}")
    print(f"Checking: {description}")
    print(f"{'='*70}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"✓ SUCCESS")
            print(result.stdout)
        else:
            print(f"✗ FAILED (exit code: {result.returncode})")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
    except subprocess.TimeoutExpired:
        print("✗ TIMEOUT")
    except Exception as e:
        print(f"✗ ERROR: {e}")


def main():
    print("\n" + "="*70)
    print("Chrome/ChromeDriver Diagnostic Tool")
    print("="*70)

    # Check Chrome
    run_command("google-chrome --version", "Chrome version")
    run_command("which google-chrome", "Chrome location")

    # Check ChromeDriver
    run_command("chromedriver --version", "ChromeDriver version")
    run_command("which chromedriver", "ChromeDriver location")

    # Check Python packages
    run_command("pip list | grep -i selenium", "Selenium packages")

    # Check if Chrome can start (simple version test)
    print(f"\n{'='*70}")
    print("Checking: Chrome headless test (simple)")
    print(f"{'='*70}")
    try:
        result = subprocess.run(
            ["google-chrome", "--headless", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
             "--dump-dom", "about:blank"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("✓ SUCCESS - Chrome can run in headless mode")
            output_lines = result.stdout.split('\n')[:5]
            for line in output_lines:
                if line.strip():
                    print(f"  {line[:100]}")
        else:
            print(f"✗ FAILED (exit code: {result.returncode})")
            print("STDERR:", result.stderr[:500])
    except subprocess.TimeoutExpired:
        print("✗ TIMEOUT - Chrome is hanging")
        print("  This usually indicates missing dependencies or incompatible flags")
    except Exception as e:
        print(f"✗ ERROR: {e}")

    # Check shared memory
    run_command("df -h /dev/shm", "Shared memory (/dev/shm)")

    # Check display
    run_command("echo $DISPLAY", "Display variable")

    # Check for required libraries
    print(f"\n{'='*70}")
    print("Checking required libraries")
    print(f"{'='*70}")
    libraries = [
        'libasound2', 'libatk-bridge2.0-0', 'libatk1.0-0', 'libatspi2.0-0',
        'libcups2', 'libdbus-1-3', 'libdrm2', 'libgbm1', 'libgtk-3-0',
        'libnspr4', 'libnss3', 'libxcomposite1', 'libxdamage1'
    ]

    for lib in libraries:
        run_command(f"dpkg -l | grep {lib}", f"Library: {lib}")

    print("\n" + "="*70)
    print("Diagnostic complete!")
    print("="*70 + "\n")


if __name__ == '__main__':
    main()
