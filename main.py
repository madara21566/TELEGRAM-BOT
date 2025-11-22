# main.py

import os
import logging
import threading
import time
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logging.getLogger("aiogram").setLevel(logging.ERROR)

os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)

from web.app import app as flask_app  # type: ignore

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# handlers
from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers

# utils
from utils.monitor import check_expired, ensure_restart_on_boot
from utils.backup import backup_projects
from utils.helpers import (
    STATE_FILE,
    backup_latest_path,
    restore_from_zip,
    load_json,
    save_json,
)
from utils.mongo_state import get_latest_state


# --------- Mongo se state restore (agar local state.json missing ho) ---------


def restore_state_from_mongo_if_needed():
    """
    Agar state.json nahi hai lekin MongoDB me snapshot hai,
    toh us snapshot se local state.json restore karo.
    """
    if os.path.exists(STATE_FILE):
        return

    try:
        state = get_latest_state()
        if state:
            save_json(STATE_FILE, state)
            logging.info("State restored from MongoDB snapshot.")
        else:
            logging.info("No Mongo snapshot found, starting with empty state.")
    except Exception as e:
        logging.error(f"Mongo restore failed: {e}")


# ---------------- FLASK SERVER ---------------- #


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


# ---------------- EXPIRY CHECK ---------------- #


def expire_checker():
    while True:
        try:
            # free users 12h limit etc
            check_expired()
        except Exception as e:
            logging.error(f"Expire Error: {e}")
        time.sleep(60)


# ---------------- AUTO BACKUP (EVERY 10 MIN) ---------------- #


async def send_auto_backup(path: str):
    try:
        await bot.send_document(
            OWNER_ID,
            open(path, "rb"),
            caption="📦 Auto Backup (last 10 minutes snapshot)",
        )
        logging.info("Auto backup sent to owner.")
    except Exception as e:
        logging.error(f"Backup send failed: {e}")


def backup_loop():
    """
    Har 10 minute me:
    - local backup zip banata hai (data/state.json + data/users)
    - owner ko Telegram pe bhejta hai
    - save_json ke through Mongo me bhi latest state snapshot chala jata hai
    """
    # async loop for sending file
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            # pehle state.json ko disk pe likh le (agar memory/state me kuch change hua ho)
            st = load_json()
            save_json(STATE_FILE, st)

            # phir ZIP backup bana
            path = backup_projects()
            logging.info(f"Auto backup created: {path}")

            loop.run_until_complete(send_auto_backup(path))
        except Exception as e:
            logging.error(f"Backup error: {e}")

        time.sleep(600)  # 10 min


# ---------------- BOOT RESTORE + SERVICE START ---------------- #


def start_services():
    # 1) MongoDB snapshot se state.json restore karne ki try
    restore_state_from_mongo_if_needed()

    # 2) Local backup zip se restore ki try (agar available ho)
    try:
        last = backup_latest_path()
        if last:
            restore_from_zip(last)
            logging.info(f"Restored from latest backup zip: {last}")
    except Exception as e:
        logging.error(f"Zip restore failed: {e}")

    # background services
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()

    try:
        ensure_restart_on_boot()
    except Exception as e:
        logging.error(f"Restart handler error: {e}")

    executor.start_polling(dp, skip_updates=True)


# ---------------- REGISTER HANDLERS & RUN ---------------- #


if __name__ == "__main__":
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)

    start_services()
