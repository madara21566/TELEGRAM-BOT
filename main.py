# main.py

import os
import logging
import threading
import time
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

from web.app import app as flask_app

from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers

from utils.monitor import check_expired, ensure_restart_on_boot
from utils.backup import backup_projects
from utils.helpers import backup_latest_path, restore_from_zip

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

# --------- DATA FOLDERS ---------
os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"):
    with open("data/state.json", "w", encoding="utf-8") as f:
        f.write("{}")

# --------- BOT & DISPATCHER ---------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


# --------- FLASK SERVER THREAD ---------
def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


# --------- EXPIRY CHECK THREAD ---------
def expire_checker():
    while True:
        try:
            # Free user 12h / premium 24h logic utils.monitor.check_expired ke andar hai
            check_expired()
        except Exception as e:
            logging.error("Expire Error: %s", e)
        time.sleep(60)


# --------- AUTO BACKUP THREAD (10 min) ---------
async def _send_auto_backup(path: str):
    try:
        await bot.send_document(
            OWNER_ID,
            open(path, "rb"),
            caption="📦 Auto Backup (last 10 minutes state)",
        )
        logging.info("Auto-backup sent to owner.")
    except Exception as e:
        logging.error("send backup error: %s", e)


def backup_loop():
    # Har 10 minute pura data ka backup + owner ko zip send
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            path = backup_projects()
            logging.info("Auto-backup created at %s", path)
            loop.run_until_complete(_send_auto_backup(path))
        except Exception as e:
            logging.error("backup error: %s", e)
        time.sleep(600)  # 10 minutes


# --------- START SERVICES + BOT ---------
def start_services():
    # 1) Boot pe latest backup se restore
    try:
        last = backup_latest_path()
        if last:
            restore_from_zip(last)
            logging.info("Restored from latest backup at startup: %s", last)
    except Exception as e:
        logging.error("restore error: %s", e)

    # 2) Background threads
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()

    # 3) Restart-on-boot marker (render pe auto restart ke liye)
    try:
        ensure_restart_on_boot()
    except Exception as e:
        logging.error("ensure_restart_on_boot error: %s", e)

    # 4) Start polling
    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    # Order important hai – start/project/admin/backup sab register honge
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)

    start_services()
