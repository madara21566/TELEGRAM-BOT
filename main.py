import asyncio
import random
import time
from datetime import datetime, timedelta
import logging
import os
import aiohttp
from playwright.async_api import async_playwright

# ================= CONFIG =================

HUMAN_INTERACT_SITES = [
"[https://telegram-bot-ddhv.onrender.com/](https://telegram-bot-ddhv.onrender.com/)", # replace with your sites
"[https://telegram-bot-1-58nb.onrender.com](https://telegram-bot-1-58nb.onrender.com)",
]

INTERVAL_SECONDS = 120 # 2 minutes
REQUEST_TIMEOUT = 15
RETRIES = 1
RETRY_DELAY = 3
CONCURRENT_REQUESTS = 4
HUMAN_ACTIONS_PER_VISIT = (3, 8)
MAX_INTERACT_DURATION = 20
HEADLESS = True

# Telegram config (from Render Environment Variables)

TELEGRAM_ALERTS_ENABLED = True
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ALERT_COOLDOWN = timedelta(minutes=30)

# ==========================================

# Logging setup

logging.basicConfig(
level=logging.INFO,
format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("render_bot")
last_alert_time: dic = {}

# ---------- Telegram helper ----------

async def send_telegram_message(session: aiohttp.ClientSession, text: str):
if not TELEGRAM_ALERTS_ENABLED:
return
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
logger.warning("Telegram bot token or chat id not configured.")
return
url = f"[https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage](https://api.telegram.org/bot%7BTELEGRAM_BOT_TOKEN%7D/sendMessage)"
payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
try:
async with session.post(url, json=payload, timeout=10) as resp:
if resp.status == 200:
logger.info("Telegram alert sent.")
else:
logger.warning("Telegram API error: %s", await resp.text())
except Exception as e:
logger.error("Telegram send failed: %s", e)

# ---------- HTTP check ----------

async def fetch(session: aiohttp.ClientSession, url: str):
attempt = 0
while True:
attempt += 1
try:
start = time.monotonic()
async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
elapsed = (time.monotonic() - start) * 1000
return {"url": url, "status": resp.status, "ok": 200 <= resp.status < 400, "elapsed_ms": round(elapsed, 1)}
except Exception as e:
if attempt > RETRIES:
return {"url": url, "status": None, "ok": False, "error": str(e)}
await asyncio.sleep(RETRY_DELAY)

async def check_all(session: aiohttp.ClientSession, sites: list[str]):
sem = asyncio.Semaphore(CONCURRENT_REQUESTS)
async def guarded_fetch(u):
async with sem:
return await fetch(session, u)
results = await asyncio.gather(*(guarded_fetch(u) for u in sites))
for r in results:
if r.get("ok"):
logger.info("UP | %s | %s ms", r["url"], r.get("elapsed_ms"))
else:
logger.error("DOWN | %s | err=%s", r["url"], r.get("error"))
await maybe_alert(session, r)
return results

# --------- Alert cooldown ----------

async def maybe_alert(session: aiohttp.ClientSession, result: dict):
url = result["url"]
now = datetime.utcnow()
last = last_alert_time.get(url)
if last and (now - last) < ALERT_COOLDOWN:
logger.info("Cooldown active, skipping alert for %s", url)
return
msg = f"🚨 *Site DOWN*: `{url}`\nTime: `{now.isoformat()} UTC`\nDetails: `{result}`"
await send_telegram_message(session, msg)
last_alert_time[url] = now

# --------- Human-like interactions ----------

async def human_visit_and_act(browser, url: str):
logger.info("Human-like visit: %s", url)
try:
context = await browser.new_context()
page = await context.new_page()
await page.set_viewport_size({"width": 1200, "height": 800})
await page.goto(url, wait_until="domcontentloaded", timeout=15000)

```
    actions = random.randint(*HUMAN_ACTIONS_PER_VISIT)
    end_time = time.monotonic() + MAX_INTERACT_DURATION
    for _ in range(actions):
        if time.monotonic() > end_time:
            break
        act = random.choice(["scroll", "click", "wait"])
        if act == "scroll":
            height = await page.evaluate("() => document.body.scrollHeight")
            y = random.randint(0, max(0, int(height)-100)) if height else 0
            await page.evaluate(f"() => window.scrollTo({{top:{y}, behavior:'smooth'}})")
            await asyncio.sleep(random.uniform(0.5, 2))
        elif act == "click":
            anchors = await page.query_selector_all("a[href]")
            if anchors:
                el = random.choice(anchors)
                try:
                    await el.click(timeout=3000)
                    await asyncio.sleep(random.uniform(0.5, 2))
                except:
                    pass
        else:
            await asyncio.sleep(random.uniform(0.5, 2))

    await context.close()
except Exception as e:
    logger.error("Human visit error for %s: %s", url, e)
```

# ---------------- Main loop ----------------

async def scheduler():
connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS, ssl=False)
async with aiohttp.ClientSession(connector=connector) as session:
async with async_playwright() as pw:
browser = await pw.chromium.launch(headless=HEADLESS)
run_count = 0
while True:
run_count += 1
logger.info("=== Run #%d ===", run_count)
await check_all(session, HUMAN_INTERACT_SITES)
await asyncio.gather(*(human_visit_and_act(browser, site) for site in HUMAN_INTERACT_SITES))
await asyncio.sleep(INTERVAL_SECONDS)

def main():
try:
asyncio.run(scheduler())
except KeyboardInterrupt:
logger.info("Stopped by user.")

if **name** == "**main**":
main()
