import os
import json
import logging
import threading
import time

from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "")
PORT = int(os.getenv("PORT", "10000"))

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logging.getLogger("aiogram").setLevel(logging.ERROR)

# Ensure required folders exist
os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"):
    open("data/state.json", "w").write("{}")

# Flask Web App
from web.app import app as flask_app

# Telegram Bot
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Import Handlers
from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers

# Runtime Monitor (Free Limit / Premium 24x7)
from utils.monitor import check_expired, restore_processes_after_restart


# Start Flask Web Server
def run_flask():
    logging.info(f"🌐 Flask Web File Manager running on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)


# Background Monitor Loop
def monitor_loop():
    while True:
        try:
            check_expired()
        except Exception as e:
            logging.error(f"[Monitor Error] {e}")
        time.sleep(60)  # check every 1 minute


# Launch Services
def start_services():
    # Start Flask UI
    threading.Thread(target=run_flask, daemon=True).start()

    # Auto Restore Running Scripts After Restart (24/7 Premium)
    threading.Thread(target=restore_processes_after_restart, daemon=True).start()

    # Start Runtime Limit Monitor
    threading.Thread(target=monitor_loop, daemon=True).start()

    logging.info("🤖 Telegram Bot Online.")
    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    # Register all bot handlers
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)

    # Start bot & web server
    start_services()
