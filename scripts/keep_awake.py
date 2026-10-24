#!/usr/bin/env python3
"""Ping Pramaan web and API health endpoints to prevent Render free-tier sleep.

Usage:
    python scripts/keep_awake.py [WEB_URL] [API_URL]
    python scripts/keep_awake.py --loop 600 [WEB_URL] [API_URL]
"""

import argparse
import sys
import time
import urllib.error
import urllib.request


def ping(url: str, timeout: int = 60) -> int:
    if not url.endswith("/api/health"):
        url = url.rstrip("/") + "/api/health"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Pramaan-KeepAwake/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        print(f"Error pinging {url}: {e}", file=sys.stderr)
        return -1


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep Render services awake")
    parser.add_argument("urls", nargs="*", help="Web and API URLs to ping")
    parser.add_argument("--loop", type=int, default=0, help="Loop interval in seconds (0 = run once)")
    args = parser.parse_args()

    urls = args.urls or [
        "https://pramaan-web.onrender.com",
        "https://pramaan-api.onrender.com",
    ]

    while True:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        print(f"[{timestamp}] Pinging services...")
        for u in urls:
            code = ping(u)
            status_text = "OK" if 200 <= code < 400 else "FAIL"
            print(f"  {u} -> HTTP {code} ({status_text})")

        if args.loop <= 0:
            break
        print(f"Waiting {args.loop} seconds before next ping...")
        time.sleep(args.loop)

    return 0


if __name__ == "__main__":
    sys.exit(main())
