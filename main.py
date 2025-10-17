#!/usr/bin/env python3
"""
telegram_monitor_bot.py

Safe Telegram bot for admin-controlled website monitoring.

Requirements:
  pip install python-telegram-bot==20.5 aiohttp aiosqlite

Usage:
  - Set BOT_TOKEN and ADMIN_USER_ID below
  - Run: python telegram_monitor_bot.py
  - Admin commands (Telegram chat with bot):
      /start
      /addsite <https://example.com>  -> bot gives a verification token & instructions
      /verify <site_id>               -> bot verifies token placed by admin on site
      /removesite <site_id>
      /listsites
      /status <site_id>
      /addviewer <telegram_user_id>   -> optional: give read-only access
"""

import asyncio
import os
import secrets
import time
from datetime import datetime, timezone

import aiohttp
import aiosqlite
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, filters

# ---------- CONFIG ----------
BOT_TOKEN = "7869581039:AAHTdLIasMTXuONwmo790sCI7J8pJpQsNJg"
ADMIN_USER_ID = 7640327597  # replace with your Telegram user id (int)
DATABASE = "monitor.db"

# Monitoring settings
DEFAULT_CHECK_INTERVAL = 90  # seconds between checks (per site) minimum
MIN_CHECK_INTERVAL = 30
MAX_CONCURRENT_REQUESTS = 6  # concurrency limit for async pings
RATE_LIMIT_PER_HOUR = 120  # max checks per site per hour (safety)
# -----------------------------

# --- Utilities ---
def now_iso():
    return datetime.now(timezone.utc).isoformat()

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                verified INTEGER NOT NULL DEFAULT 0,
                token TEXT,
                created_at TEXT,
                last_status INTEGER,
                last_resp_ms REAL,
                last_checked TEXT,
                check_interval INTEGER DEFAULT ?
            )""",
            (DEFAULT_CHECK_INTERVAL,),
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS viewers (
                user_id INTEGER PRIMARY KEY
            )"""
        )
        await db.commit()

# Note: aiosqlite parameter substitution for default in CREATE may not be supported on all versions.
# To keep it robust, we'll recreate table properly if needed:
async def ensure_tables():
    async with aiosqlite.connect(DATABASE) as db:
        # create sites table if not exists (without param)
        await db.execute(
            """CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                verified INTEGER NOT NULL DEFAULT 0,
                token TEXT,
                created_at TEXT,
                last_status INTEGER,
                last_resp_ms REAL,
                last_checked TEXT,
                check_interval INTEGER DEFAULT 90,
                hourly_count INTEGER DEFAULT 0,
                hourly_window_start INTEGER DEFAULT 0
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS viewers (
                user_id INTEGER PRIMARY KEY
            )"""
        )
        await db.commit()

# --- Bot command handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == ADMIN_USER_ID:
        await update.message.reply_text("Hello Admin — use /addsite <url> to add a site for monitoring.")
    else:
        await update.message.reply_text("Hello — If you need access, ask the admin. This bot is admin-controlled.")

async def addsite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID:
        return await update.message.reply_text("Only admin can add sites.")

    if len(context.args) < 1:
        return await update.message.reply_text("Usage: /addsite https://example.com")

    url = context.args[0].rstrip("/")
    # basic validation
    if not (url.startswith("http://") or url.startswith("https://")):
        return await update.message.reply_text("URL must start with http:// or https://")

    token = secrets.token_hex(10)
    created_at = now_iso()

    async with aiosqlite.connect(DATABASE) as db:
        try:
            await db.execute(
                "INSERT INTO sites (url, verified, token, created_at) VALUES (?, 0, ?, ?)",
                (url, token, created_at),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            return await update.message.reply_text("That URL is already added.")

        # get site id
        cur = await db.execute("SELECT id FROM sites WHERE url = ?", (url,))
        row = await cur.fetchone()
        site_id = row[0]

    msg = (
        f"Site registered (id={site_id}).\n\n"
        f"To verify ownership, create a plain text file at:\n"
        f"{url.rstrip('/')}/.well-known/uptime-token.txt\n\n"
        f"Put exactly this token (no extra spaces/newlines):\n\n"
        f"{token}\n\n"
        f"Then run:\n/verify {site_id}\n\n"
        f"Note: Verification is required before monitoring starts."
    )
    await update.message.reply_text(msg)

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID:
        return await update.message.reply_text("Only admin can verify sites.")
    if len(context.args) < 1:
        return await update.message.reply_text("Usage: /verify <site_id>")

    try:
        site_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("site_id must be a number")

    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT url, token, verified FROM sites WHERE id = ?", (site_id,))
        row = await cur.fetchone()
        if not row:
            return await update.message.reply_text("Site not found.")
        url, token, verified = row
        if verified:
            return await update.message.reply_text("Site already verified.")

    # try fetching token
    token_url = url.rstrip("/") + "/.well-known/uptime-token.txt"
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(token_url, timeout=10) as resp:
                text = await resp.text()
                if token.strip() == text.strip():
                    async with aiosqlite.connect(DATABASE) as db:
                        await db.execute("UPDATE sites SET verified = 1 WHERE id = ?", (site_id,))
                        await db.commit()
                    return await update.message.reply_text(f"Verified! Site {url} is now monitored.")
                else:
                    return await update.message.reply_text(
                        "Token not found or does not match. Please ensure the file exists and contains the exact token."
                    )
    except Exception as e:
        return await update.message.reply_text(f"Error fetching token file: {e}")

async def removesite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID:
        return await update.message.reply_text("Only admin can remove sites.")
    if len(context.args) < 1:
        return await update.message.reply_text("Usage: /removesite <site_id>")

    try:
        site_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("site_id must be a number")

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM sites WHERE id = ?", (site_id,))
        await db.commit()
    await update.message.reply_text(f"Removed site id={site_id} (if it existed).")

async def listsites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID:
        return await update.message.reply_text("Only admin can list sites.")
    rows_text = []
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT id, url, verified, last_status, last_resp_ms, last_checked FROM sites ORDER BY id")
        rows = await cur.fetchall()
        if not rows:
            return await update.message.reply_text("No sites added yet.")
        for r in rows:
            id_, url, verified, last_status, last_resp_ms, last_checked = r
            rows_text.append(
                f"{id_}: {url}\n  verified={'yes' if verified else 'no'}  last_status={last_status} resp_ms={last_resp_ms} last_checked={last_checked}"
            )
    await update.message.reply_text("\n\n".join(rows_text))

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # allow admin or viewers
    uid = update.effective_user.id
    allowed = False
    if uid == ADMIN_USER_ID:
        allowed = True
    else:
        async with aiosqlite.connect(DATABASE) as db:
            cur = await db.execute("SELECT 1 FROM viewers WHERE user_id = ?", (uid,))
            if await cur.fetchone():
                allowed = True
    if not allowed:
        return await update.message.reply_text("You don't have permission to view status. Ask admin for access.")

    if len(context.args) < 1:
        return await update.message.reply_text("Usage: /status <site_id>")

    try:
        site_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("site_id must be a number")

    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT url, verified, last_status, last_resp_ms, last_checked FROM sites WHERE id = ?", (site_id,))
        row = await cur.fetchone()
        if not row:
            return await update.message.reply_text("Site not found.")
        url, verified, last_status, last_resp_ms, last_checked = row
        msg = f"Site {site_id}: {url}\nverified={'yes' if verified else 'no'}\nlast_status={last_status}\nlast_resp_ms={last_resp_ms}\nlast_checked={last_checked}"
        return await update.message.reply_text(msg)

async def addviewer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_USER_ID:
        return await update.message.reply_text("Only admin can add viewers.")
    if len(context.args) < 1:
        return await update.message.reply_text("Usage: /addviewer <telegram_user_id>")

    try:
        viewer_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("user_id must be a number")

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT OR IGNORE INTO viewers (user_id) VALUES (?)", (viewer_id,))
        await db.commit()
    await update.message.reply_text(f"Added viewer {viewer_id}")

# --- Background monitor ---
async def fetch_site(session: aiohttp.ClientSession, site_row):
    # site_row: (id, url, verified, token, created_at, last_status, last_resp_ms, last_checked, check_interval, hourly_count, hourly_window_start)
    site_id = site_row[0]
    url = site_row[1]
    verified = site_row[2]
    check_interval = site_row[8] or DEFAULT_CHECK_INTERVAL

    # simple hourly rate limiting per-site (in-db)
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT hourly_count, hourly_window_start FROM sites WHERE id = ?", (site_id,))
        r = await cur.fetchone()
        hour_now = int(time.time() // 3600)
        if r:
            count, window = r
            if window != hour_now:
                # reset window
                await db.execute("UPDATE sites SET hourly_count = 0, hourly_window_start = ? WHERE id = ?", (hour_now, site_id))
                await db.commit()
                count = 0
        else:
            count = 0

        if count >= RATE_LIMIT_PER_HOUR:
            return  # skip due to rate limit

        # increment
        await db.execute("UPDATE sites SET hourly_count = hourly_count + 1 WHERE id = ?", (site_id,))
        await db.commit()

    if not verified:
        return

    start = time.time()
    status = None
    resp_ms = None
    try:
        async with session.get(url, timeout=20) as resp:
            status = resp.status
            _ = await resp.read()  # ensure full read
            resp_ms = (time.time() - start) * 1000.0
    except Exception:
        status = None
        resp_ms = None

    now = now_iso()
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "UPDATE sites SET last_status = ?, last_resp_ms = ?, last_checked = ? WHERE id = ?",
            (status, resp_ms, now, site_id),
        )
        await db.commit()

async def monitor_loop(stop_event: asyncio.Event):
    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            # fetch list of verified sites
            async with aiosqlite.connect(DATABASE) as db:
                cur = await db.execute("SELECT id, url, verified, token, created_at, last_status, last_resp_ms, last_checked, check_interval, hourly_count, hourly_window_start FROM sites")
                rows = await cur.fetchall()

            tasks = []
            tnow = time.time()
            for r in rows:
                site_id = r[0]
                verified = r[2]
                interval = r[8] or DEFAULT_CHECK_INTERVAL
                last_checked = r[7]
                should_check = False
                if not verified:
                    continue
                if not last_checked:
                    should_check = True
                else:
                    # parse last_checked
                    try:
                        last_ts = datetime.fromisoformat(last_checked).timestamp()
                        if (tnow - last_ts) >= interval:
                            should_check = True
                    except Exception:
                        should_check = True

                if should_check:
                    # respect concurrency
                    async def guarded_fetch(row):
                        async with sem:
                            await fetch_site(session, row)
                    tasks.append(asyncio.create_task(guarded_fetch(r)))

            if tasks:
                await asyncio.gather(*tasks)

            # small sleep to avoid tight loop; main interval = 10s to re-evaluate scheduling
            await asyncio.sleep(10)

# --- Main startup ---
async def main():
    await ensure_tables()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addsite", addsite))
    application.add_handler(CommandHandler("verify", verify))
    application.add_handler(CommandHandler("removesite", removesite))
    application.add_handler(CommandHandler("listsites", listsites))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("addviewer", addviewer))

    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_loop(stop_event))

    # start the bot
    await application.initialize()
    await application.start()
    print("Bot started. Press Ctrl+C to stop.")
    try:
        await application.updater.start_polling()  # for long-polling
        # keep running
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down...")
    finally:
        stop_event.set()
        monitor_task.cancel()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
