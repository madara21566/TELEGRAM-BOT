#!/usr/bin/env python3
"""
human_uptime.py
Simple "human-like" uptime pinger.
Replace TARGET_URL with your website.

Usage:
    python3 human_uptime.py
"""

import requests
import time
import random
import logging
import sys
import signal
from datetime import datetime

# === CONFIGURE ===
TARGET_URL = "https://telegram-bot-ddhv.onrender.com"   # ← <-- Replace with your website (keep scheme: https://)
MIN_SECS = 60       # minimum wait (1 minute)
MAX_SECS = 120      # maximum wait (2 minutes)
LOGFILE = "human_uptime.log"
REQUEST_TIMEOUT = 20    # seconds
# Probability to also fetch a small secondary resource to look more human-like
FETCH_SECONDARY_PROB = 0.35

# A small list of common user agents to rotate through
USER_AGENTS = [
    # desktop browsers
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.90 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.90 Safari/537.36",
    # mobile
    "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.90 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

# Secondary paths to randomly fetch sometimes (favicon, robots)
SECONDARY_PATHS = ["/favicon.ico", "/robots.txt", "/sitemap.xml"]

# === Logging setup ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOGFILE),
        logging.StreamHandler(sys.stdout)
    ]
)

running = True

def signal_handler(sig, frame):
    global running
    logging.info("Shutdown signal received. Exiting gracefully...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def build_headers():
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        # optional: keep-referer sometimes to mimic navigation
    }
    # occasionally add a referer to look more human
    if random.random() < 0.25:
        headers["Referer"] = random.choice([TARGET_URL, TARGET_URL + "/"])
    return headers

def visit(url):
    try:
        headers = build_headers()
        start = time.time()
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        elapsed = time.time() - start
        logging.info(f"Visited {url}  status={r.status_code}  time={elapsed:.2f}s  UA={headers.get('User-Agent')[:60]!s}")
        return r.status_code, elapsed
    except requests.RequestException as e:
        logging.warning(f"Error visiting {url}: {e}")
        return None, None

def maybe_fetch_secondary(base_url):
    if random.random() < FETCH_SECONDARY_PROB:
        path = random.choice(SECONDARY_PATHS)
        full = base_url.rstrip("/") + path
        try:
            # small timeout for secondary
            r = requests.get(full, headers=build_headers(), timeout=8)
            logging.info(f"Also fetched {path} status={r.status_code}")
        except Exception as e:
            logging.debug(f"Secondary fetch failed {path}: {e}")

def human_sleep():
    # pick random seconds between MIN_SECS and MAX_SECS but add small jitter
    secs = random.uniform(MIN_SECS, MAX_SECS)
    # small human-like micro-jitter
    jitter = random.uniform(-3, 3)
    final = max(1, secs + jitter)
    logging.info(f"Sleeping for {final:.1f} seconds")
    time.sleep(final)

def main():
    logging.info("Starting human-like uptime pinger.")
    logging.info(f"Target: {TARGET_URL}  Interval: {MIN_SECS}-{MAX_SECS}s")
    # initial small randomized delay to avoid exact alignments on restart
    initial_delay = random.uniform(1, 8)
    logging.info(f"Initial randomized delay: {initial_delay:.1f}s")
    time.sleep(initial_delay)

    consecutive_errors = 0
    while running:
        status, elapsed = visit(TARGET_URL)
        if status is None or (isinstance(status, int) and status >= 500):
            consecutive_errors += 1
        else:
            consecutive_errors = 0

        # sometimes do a secondary resource fetch to mimic a browser
        maybe_fetch_secondary(TARGET_URL)

        # if many consecutive errors, back off a bit (but keep trying)
        if consecutive_errors >= 6:
            backoff = min(300, 60 * (consecutive_errors - 4))  # up to 5 minutes
            logging.warning(f"{consecutive_errors} consecutive errors — backing off {backoff}s")
            time.sleep(backoff)

        human_sleep()

    logging.info("Stopped.")

if __name__ == "__main__":
    main()
