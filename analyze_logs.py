#!/usr/bin/env python3
"""
Quick analysis script for network logs captured by the Mellowtel analyzer.
"""

import json
import sys
from collections import Counter, defaultdict
from urllib.parse import urlparse
from pathlib import Path


def load_logs(filepath):
    """Load and parse JSONL log file."""
    logs = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
        return logs
    except FileNotFoundError:
        print(f"Error: Log file not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in log file: {e}")
        sys.exit(1)


def extract_domain(url):
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or parsed.path
    except:
        return url


def analyze_logs(logs):
    """Perform basic analysis on network logs."""
    print("=" * 80)
    print("Network Log Analysis")
    print("=" * 80)

    # Basic stats
    print(f"\n📊 Total Requests: {len(logs)}")

    # Requests by visited site
    sites = Counter([log.get('visited_site', 'unknown') for log in logs])
    print(f"\n🌐 Requests by Visited Site:")
    for site, count in sites.most_common():
        print(f"  {site}: {count} requests")

    # Request methods
    methods = Counter([log.get('method', 'unknown') for log in logs])
    print(f"\n📝 Request Methods:")
    for method, count in methods.items():
        print(f"  {method}: {count}")

    # Top domains requested
    domains = Counter([extract_domain(log.get('url', '')) for log in logs])
    print(f"\n🔗 Top 20 Domains Requested:")
    for domain, count in domains.most_common(20):
        print(f"  {domain}: {count} requests")

    # Status codes
    status_codes = Counter([
        log.get('response', {}).get('status_code', 'no response')
        for log in logs
    ])
    print(f"\n📈 Response Status Codes:")
    for code, count in sorted(status_codes.items(), key=lambda x: str(x[0])):
        print(f"  {code}: {count}")

    # Identify potential extension domains
    print(f"\n🔍 Potential Extension-Related Domains:")
    print("  (Domains not matching visited sites)")
    visited_domains = {extract_domain(site) for site in sites.keys()}

    potential_extension_domains = set()
    for log in logs:
        request_domain = extract_domain(log.get('url', ''))
        visited_site = log.get('visited_site', '')
        visited_domain = extract_domain(visited_site)

        # Check if request domain is not related to visited site
        if request_domain and visited_domain:
            if visited_domain not in request_domain and request_domain not in visited_domain:
                potential_extension_domains.add(request_domain)

    # Filter out common CDN/analytics domains
    common_domains = {
        'google-analytics.com', 'googletagmanager.com', 'doubleclick.net',
        'facebook.com', 'facebook.net', 'twitter.com', 'instagram.com',
        'cloudflare.com', 'amazonaws.com', 'cloudfront.net',
        'googlesyndication.com', 'googleadservices.com'
    }

    suspicious_domains = []
    for domain in potential_extension_domains:
        is_common = any(common in domain for common in common_domains)
        if not is_common:
            # Count how many times this domain appears
            count = sum(1 for log in logs if extract_domain(log.get('url', '')) == domain)
            suspicious_domains.append((domain, count))

    suspicious_domains.sort(key=lambda x: x[1], reverse=True)

    if suspicious_domains:
        print("\n  ⚠️  Suspicious (non-CDN) domains:")
        for domain, count in suspicious_domains[:15]:
            print(f"    {domain}: {count} requests")
    else:
        print("  None detected (or only common CDN/analytics domains)")

    # Content types
    content_types = Counter()
    for log in logs:
        ct = log.get('response', {}).get('headers', {}).get('Content-Type', 'unknown')
        if ct != 'unknown':
            # Simplify content type
            ct = ct.split(';')[0].strip()
        content_types[ct] += 1

    print(f"\n📦 Top Content Types:")
    for ct, count in content_types.most_common(10):
        print(f"  {ct}: {count}")

    print("\n" + "=" * 80)


def export_to_csv(logs, output_file='output/network_logs.csv'):
    """Export logs to CSV format for further analysis."""
    import csv

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp', 'visited_site', 'request_url', 'request_domain',
            'method', 'status_code', 'content_type'
        ])

        for log in logs:
            writer.writerow([
                log.get('timestamp', ''),
                log.get('visited_site', ''),
                log.get('url', ''),
                extract_domain(log.get('url', '')),
                log.get('method', ''),
                log.get('response', {}).get('status_code', ''),
                log.get('response', {}).get('headers', {}).get('Content-Type', '').split(';')[0]
            ])

    print(f"\n✅ Exported to CSV: {output_file}")


def main():
    """Main entry point."""
    log_file = 'output/network_logs.jsonl'

    if len(sys.argv) > 1:
        log_file = sys.argv[1]

    print(f"Loading logs from: {log_file}\n")
    logs = load_logs(log_file)

    if not logs:
        print("No logs to analyze.")
        return

    analyze_logs(logs)

    # Ask to export to CSV
    try:
        response = input("\nExport to CSV? (y/n): ").lower()
        if response == 'y':
            export_to_csv(logs)
    except (EOFError, KeyboardInterrupt):
        print("\nSkipping CSV export.")


if __name__ == '__main__':
    main()
