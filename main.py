import os
import logging
import threading
import time
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

# .env se values load karo
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "")
PORT = int(os.getenv("PORT", "10000"))

# --------- BASIC LOGGING ---------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logging.getLogger("aiogram").setLevel(logging.ERROR)

# --------- DATA FOLDERS ENSURE ---------
os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"):
    open("data/state.json", "w").write("{}")

# --------- IMPORTS (BOT + WEB + UTILS) ---------
from web.app import app as flask_app

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers

from utils.monitor import check_expired, ensure_restart_on_boot
from utils.backup import backup_projects
from utils.helpers import backup_latest_path, restore_from_zip


# ---------------- FLASK SERVER (WEB DASHBOARD) ---------------- #
def run_flask():
    """
    Web dashboard ko alag thread pe chalao.
    """
    flask_app.run(host="0.0.0.0", port=PORT)


# ---------------- EXPIRY CHECK (FREE USER 12H LIMIT) ---------------- #
def expire_checker():
    """
    Har 60 second me free/premium expiry check karega.
    """
    while True:
        try:
            check_expired()
        except Exception as e:
            logging.error(f"Expire Error: {e}")
        time.sleep(60)


# ---------------- AUTO BACKUP LOOP (EVERY 10 MIN) ---------------- #
def backup_loop():
    """
    Har 10 minute me backup_projects() chalata rahega.
    backup_projects() ke andar chahe local ZIP banta ho
    ya Google Drive upload ho – yahan se sirf call ho raha hai.
    """
    while True:
        try:
            path = backup_projects()
            logging.info(f"[AUTO BACKUP] Backup created: {path}")
        except Exception as e:
            logging.error(f"[AUTO BACKUP] Backup error: {e}")
        # 600 sec = 10 minute
        time.sleep(600)


# ---------------- BOOT RESTORE + STARTUP BACKUP + SERVICES ---------------- #
def start_services():
    """
    - Bot start hone par:
        1) Agar koi latest backup ZIP hai -> restore_from_zip()
        2) Turant ek fresh backup bhi le (startup snapshot)
    - Phir Flask / expiry checker / auto-backup threads start kare
    - Aakhri me aiogram polling start kare
    """

    # 1) BOOT RESTORE (AGAR BACKUP HAI TO)
    try:
        last = backup_latest_path()
        if last:
            logging.info(f"[BOOT RESTORE] Found latest backup: {last} -> restoring...")
            restore_from_zip(last)
            logging.info("[BOOT RESTORE] Restore complete.")
        else:
            logging.info("[BOOT RESTORE] No backup zip found, skipping restore.")
    except Exception as e:
        logging.error(f"[BOOT RESTORE] Restore failed: {e}")

    # 2) STARTUP BACKUP (BOT DUBARA START HOTE HI BACKUP LE)
    try:
        first_path = backup_projects()
        logging.info(f"[STARTUP BACKUP] Initial backup created: {first_path}")
    except Exception as e:
        logging.error(f"[STARTUP BACKUP] Failed to create initial backup: {e}")

    # 3) BACKGROUND THREADS
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()

    # 4) RESTART-ON-BOOT HANDLING (AGAR utils.monitor ME IMPLEMENT HAI)
    try:
        ensure_restart_on_boot()
    except Exception as e:
        logging.error(f"[RESTART HANDLER] Error: {e}")

    # 5) START TELEGRAM BOT
    executor.start_polling(dp, skip_updates=True)


# ---------------- REGISTER HANDLERS + START ---------------- #
if __name__ == "__main__":
    # saare handlers register karo
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)

    # services + auto backup + restore start
    start_services()
