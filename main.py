import asyncio
import random
import time
from datetime import datetime, timedelta
import logging
from logging.handlers import RotatingFileHandler
import smtplib
from email.message import EmailMessage
import aiohttp

# Playwright async API

from playwright.async_api import async_playwright

# ================= CONFIG =================

URLS = [
"[https://example.com](https://example.com)",
"[https://httpbin.org/get](https://httpbin.org/get)",
"[https://www.google.com](https://www.google.com)",
"[https://www.github.com](https://www.github.com)",
"[https://www.python.org](https://www.python.org)",
]

# Add 2 sites for human-like interactions (must be subset of URLS or any sites you control)

HUMAN_INTERACT_SITES = [
"[https://example.com](https://example.com)",       # site A (replace)
"[https://httpbin.org](https://httpbin.org)",       # site B (replace)
]

# OPTIONAL: If you want "turn off / turn on" behavior via an API on your own site,

# set maintenance endpoints here (they must be endpoints you control).

# Example: "[https://example.com/maintenance/toggle](https://example.com/maintenance/toggle)" or two endpoints for on/off.

MAINTENANCE_ENDPOINTS = {
# domain -> {"on": "[https://example.com/maint/on](https://example.com/maint/on)", "off": "[https://example.com/maint/off"}](https://example.com/maint/off%22})
# leave empty or remove if you don't have such endpoints.
# "example.com": {"on": "[https://example.com/maint/on](https://example.com/maint/on)", "off": "[https://example.com/maint/off"}](https://example.com/maint/off%22})
}

INTERVAL_SECONDS = 120  # 2 minutes
REQUEST_TIMEOUT = 15  # seconds
RETRIES = 1
RETRY_DELAY = 3
LOG_FILE = "uptime_human_monitor.log"

# Concurrency for HTTP checks

CONCURRENT_REQUESTS = 10

# EMAIL ALERT SETTINGS (use your SMTP credentials)

EMAIL_ALERTS_ENABLED = True
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "[your_email@gmail.com](mailto:your_email@gmail.com)"
SMTP_PASS = "your_app_password_or_smtp_password"  # use app password for Gmail
ALERT_RECIPIENTS = ["[you@example.com](mailto:you@example.com)"]  # list of recipients
ALERT_FROM = SMTP_USER

# Rate-limit alerts per (site -> last_alert_time). This avoids spamming.

ALERT_COOLDOWN = timedelta(minutes=30)

# Human-sim parameters

HUMAN_ACTIONS_PER_VISIT = (3, 8)  # random actions per visit (min,max)
MAX_INTERACT_DURATION = 20  # seconds per "visit"

# ==========================================

# Setup logging

logger = logging.getLogger("uptime_human_monitor")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3)
fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
handler.setFormatter(fmt)
logger.addHandler(handler)
console = logging.StreamHandler()
console.setFormatter(fmt)
logger.addHandler(console)

last_alert_time: dict[str, datetime] = {}

# ---------------- Email alert function ----------------

def send_alert_email(subject: str, body: str):
if not EMAIL_ALERTS_ENABLED:
logger.info("Email alerts disabled; skipping email.")
return

```
now = datetime.utcnow()
# Basic SMTP send with TLS
try:
    msg = EmailMessage()
    msg["From"] = ALERT_FROM
    msg["To"] = ", ".join(ALERT_RECIPIENTS)
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)
    logger.info("Alert email sent: %s", subject)
except Exception as e:
    logger.exception("Failed to send alert email: %s", e)
```

# ----------------- HTTP check -----------------

async def fetch(session: aiohttp.ClientSession, url: str):
attempt = 0
while True:
attempt += 1
try:
start = time.monotonic()
async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
elapsed = (time.monotonic() - start) * 1000
return {"url": url, "status": resp.status, "ok": 200 <= resp.status < 400, "elapsed_ms": round(elapsed, 1)}
except asyncio.TimeoutError:
logger.warning("%s timeout attempt %d", url, attempt)
error = "timeout"
except aiohttp.ClientError as e:
logger.warning("%s client error attempt %d: %s", url, attempt, e)
error = f"client_error:{e}"
except Exception as e:
logger.exception("Unexpected error fetching %s: %s", url, e)
error = f"error:{e}"

```
    if attempt > RETRIES:
        return {"url": url, "status": None, "ok": False, "error": error}
    await asyncio.sleep(RETRY_DELAY)
```

async def check_all(session: aiohttp.ClientSession, urls: list[str]):
sem = asyncio.Semaphore(CONCURRENT_REQUESTS)
async def guarded_fetch(u):
async with sem:
return await fetch(session, u)
tasks = [asyncio.create_task(guarded_fetch(u)) for u in urls]
results = await asyncio.gather(*tasks)
ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
for r in results:
if r.get("ok"):
logger.info("%s | UP   | %s | %s ms", ts, r["url"], r.get("elapsed_ms"))
else:
logger.error("%s | DOWN | %s | err=%s", ts, r["url"], r.get("error"))
await maybe_alert(r)
return results

# ---------------- Alert cooldown logic ----------------

async def maybe_alert(result: dict):
url = result["url"]
now = datetime.utcnow()
last = last_alert_time.get(url)
if last and (now - last) < ALERT_COOLDOWN:
logger.info("Alert for %s suppressed due to rate-limit (last: %s)", url, last)
return
subj = f"[UptimeMonitor] DOWN: {url}"
body = f"Detected DOWN at {now.isoformat()} UTC\n\nDetails:\n{result}\n"
send_alert_email(subj, body)
last_alert_time[url] = now

# ------------- Human-like interactions using Playwright -------------

async def human_visit_and_act(browser, url: str, maintenance_conf: dict | None = None):
"""
Open page in a browser context and do random actions: scrolls, clicks on in-domain links, random waits.
If maintenance_conf provided like {"on": "...", "off": "..."}, this function may call those endpoints
to simulate turning maintenance on/off. ONLY USE if you control the site.
"""
logger.info("Human-sim: visiting %s", url)
try:
context = await browser.new_context()
page = await context.new_page()
# set a realistic viewport
await page.set_viewport_size({"width": 1200, "height": 800})

```
    # navigate
    await page.goto(url, wait_until="domcontentloaded", timeout=15000)

    # random number of actions
    actions = random.randint(*HUMAN_ACTIONS_PER_VISIT)
    end_time = time.monotonic() + MAX_INTERACT_DURATION
    for i in range(actions):
        if time.monotonic() > end_time:
            break
        # choose action: scroll, click link, fill input (rare), wait
        act = random.choices(["scroll", "click_link", "wait"], [0.5, 0.35, 0.15])[0]
        if act == "scroll":
            height = await page.evaluate("() => document.body.scrollHeight")
            # random scroll position
            y = random.randint(0, max(0, int(height)-100))
            await page.evaluate(f"() => window.scrollTo({{top: {y}, behavior: 'smooth'}})")
            await asyncio.sleep(random.uniform(0.8, 3.0))
        elif act == "click_link":
            # find in-domain clickable links/buttons
            anchors = await page.query_selector_all("a[href]")
            candidates = []
            for a in anchors:
                try:
                    href = await a.get_attribute("href")
                    if not href:
                        continue
                    # ignore external links
                    if href.startswith("http") and url.split("//", 1)[1] not in href:
                        continue
                    # prefer same-origin or relative links
                    candidates.append(a)
                except Exception:
                    continue
            if candidates:
                el = random.choice(candidates)
                try:
                    await el.click(timeout=5000)
                    await asyncio.sleep(random.uniform(0.8, 4.0))
                except Exception:
                    # ignore click failures
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(random.uniform(0.5, 1.5))
        else:
            # just wait a bit (reading)
            await asyncio.sleep(random.uniform(1.0, 3.5))

    # optionally call maintenance endpoints randomly (only if provided and you own the site)
    if maintenance_conf and random.random() < 0.25:
        # randomly toggle off then on (use with caution)
        if "off" in maintenance_conf and "on" in maintenance_conf:
            try:
                logger.info("Calling maintenance OFF endpoint for %s", url)
                async with aiohttp.ClientSession() as s:
                    await s.get(maintenance_conf["off"], timeout=10)
                    await asyncio.sleep(random.uniform(2, 6))
                    await s.get(maintenance_conf["on"], timeout=10)
                    logger.info("Maintenance toggled off->on for %s", url)
            except Exception:
                logger.exception("Failed maintenance toggle for %s", url)

    await context.close()
    logger.info("Human-sim: finished visit %s", url)
except Exception:
    logger.exception("Human-sim error for %s", url)
```

# ---------------- Main scheduler ----------------

async def scheduler():
connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS, ssl=False)
timeout = aiohttp.ClientTimeout(total=None)
async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
# Playwright lifecycle
async with async_playwright() as pw:
browser = await pw.chromium.launch(headless=True)  # set headless=False to see the browser
next_run = time.monotonic()
run_count = 0
while True:
run_count += 1
logger.info("=== Run #%d: checking %d URLs ===", run_count, len(URLS))
# perform HTTP checks
try:
await check_all(session, URLS)
except Exception:
logger.exception("check_all failed")

```
            # For each human-interact site, perform human-sim (run concurrently but cap total)
            human_tasks = []
            for site in HUMAN_INTERACT_SITES:
                # derive maintenance_conf if available for this domain
                domain = site.split("//", 1)[1].split("/", 1)[0]
                maintenance_conf = MAINTENANCE_ENDPOINTS.get(domain)
                # IMPORTANT: only perform maintenance toggles if maintenance_conf is provided.
                # Do NOT attempt to toggle unless you own the site.
                t = asyncio.create_task(human_visit_and_act(browser, site, maintenance_conf))
                human_tasks.append(t)

            # allow human interactions to run concurrently but don't block beyond interval significantly
            # wait for them but with a cap timeout
            if human_tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*human_tasks), timeout=INTERVAL_SECONDS * 0.8)
                except asyncio.TimeoutError:
                    logger.warning("Human interactions didn't finish before timeout; continuing.")

            # schedule next run
            next_run += INTERVAL_SECONDS
            sleep_for = next_run - time.monotonic()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            else:
                logger.warning("Checks took longer than INTERVAL_SECONDS; starting next run immediately.")

        await browser.close()
```

def main():
logger.info("Starting uptime + human-sim monitor. Interval: %ds", INTERVAL_SECONDS)
try:
asyncio.run(scheduler())
except KeyboardInterrupt:
logger.info("Shutting down by user.")
except Exception:
logger.exception("Monitor crashed.")

if **name** == "**main**":
main()
