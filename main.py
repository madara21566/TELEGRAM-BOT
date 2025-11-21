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
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logging.getLogger("aiogram").setLevel(logging.ERROR)

# ---- data/ structure ensure ----
os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"):
    with open("data/state.json", "w", encoding="utf-8") as f:
        f.write("{}")

# ---- web app (dashboard/filemanager) ----
from web.app import app as flask_app

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ---- handlers ----
from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers  # even if empty, must exist

# ---- utils ----
from utils.monitor import check_expired, ensure_restart_on_boot
from utils.backup import backup_projects
from utils.helpers import backup_latest_path, restore_from_zip


# ---------------- FLASK SERVER ---------------- #
def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


# ---------------- EXPIRY CHECK ---------------- #
def expire_checker():
    """
    Free / premium user ka project expiry check loop
    (tumhare utils.monitor.check_expired ke according)
    """
    while True:
        try:
            check_expired()
        except Exception as e:
            logging.error(f"Expire Error: {e}")
        time.sleep(60)


# ---------------- AUTO BACKUP LOOP ---------------- #
async def _send_auto_backup(path: str):
    """
    Owner ko auto-backup zip bhejna (Telegram par).
    """
    try:
        await bot.send_document(
            OWNER_ID,
            open(path, "rb"),
            caption="📦 Auto Backup (last 10 minutes state)"
        )
        logging.info("Auto backup sent to owner.")
    except Exception as e:
        logging.error(f"Send auto-backup error: {e}")


def backup_loop():
    """
    Har 10 minute me:
    - backup_projects() se zip banata hai
    - owner ko Telegram me bhejta hai
    """

    # is thread ke liye dedicated event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            path = backup_projects()
            logging.info(f"Backup created at {path}")
            loop.run_until_complete(_send_auto_backup(path))
        except Exception as e:
            logging.error(f"Backup loop error: {e}")
        time.sleep(600)  # 10 minutes


# ---------------- BOOT RESTORE + SERVICE START ---------------- #
def start_services():
    # boot pe auto-restore (agar koi latest local backup hai)
    try:
        last = backup_latest_path()
        if last:
            restore_from_zip(last)
            logging.info(f"Restored from latest backup at startup: {last}")
        else:
            logging.info("No local backup found at startup.")
    except Exception as e:
        logging.error(f"Startup restore failed: {e}")

    # side services as daemon threads
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()

    # ensure restart behaviour
    try:
        ensure_restart_on_boot()
    except Exception as e:
        logging.error(f"ensure_restart_on_boot error: {e}")

    # start bot polling
    executor.start_polling(dp, skip_updates=True)


# ---------------- REGISTER HANDLERS + RUN ---------------- #
if __name__ == "__main__":
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)

    start_services()
