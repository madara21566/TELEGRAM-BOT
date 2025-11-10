import os, logging, threading, time
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("aiogram").setLevel(logging.ERROR)

os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"):
    open("data/state.json", "w").write("{}")

from web.app import app as flask_app
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Handlers
from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers

# Monitors / maintenance
from utils.monitor import check_expired, restore_processes_after_restart
from utils.backup import backup_projects_and_notify_owner

def run_flask():
    logging.info(f"🌐 Starting Flask web server on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)

def expire_checker():
    while True:
        try:
            check_expired()
        except Exception as e:
            logging.error(f"expire_checker error: {e}")
        time.sleep(60)  # check every minute

def backup_loop():
    while True:
        try:
            backup_projects_and_notify_owner()
        except Exception as e:
            logging.error(f"backup_loop error: {e}")
        time.sleep(600)  # every 10 minutes

def start_services():
    # 1) Web + background loops
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()

    # 2) Restore projects from last backup & restart them (before polling)
    try:
        restored = restore_processes_after_restart()
        if restored:
            logging.info(f"♻️ Restored {restored} project(s) from last backup and relaunched.")
    except Exception as e:
        logging.error(f"restore on boot error: {e}")

    # 3) Start Telegram bot
    logging.info("🤖 Telegram bot is starting...")
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)
    start_services()
