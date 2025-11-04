import os
import json
import logging
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ")  # <- replace with your real token if needed
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
BASE_URL = os.getenv("BASE_URL", "https://your-app.onrender.com")

# -------------------------------
# Flask web import
# -------------------------------
from web.app import app as flask_app

# -------------------------------
# Logging configuration
# -------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logging.getLogger("aiogram").setLevel(logging.ERROR)

# -------------------------------
# Data folder auto creation
# -------------------------------
os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"):
    with open("data/state.json", "w") as f:
        json.dump({}, f)
logging.info("✅ Data folders verified.")

# -------------------------------
# Initialize bot & dispatcher
# -------------------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# -------------------------------
# Import handlers
# -------------------------------
from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers

# -------------------------------
# Register all handlers
# -------------------------------
register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)

# -------------------------------
# Flask thread (web dashboard)
# -------------------------------
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🌐 Starting Flask web server on port {port}")
    flask_app.run(host="0.0.0.0", port=port)

# -------------------------------
# Start bot + web in parallel
# -------------------------------
def start_services():
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    logging.info("🤖 Telegram bot is starting...")
    executor.start_polling(dp, skip_updates=True)

# -------------------------------
# Start everything
# -------------------------------
if __name__ == "__main__":
    print("\n===============================================")
    print("🚀 MADARA HOSTING BOT v7.5 (Render-Stable)")
    print("✅ Telegram Bot + Flask Web Panel starting...")
    print("===============================================\n")
    start_services()
