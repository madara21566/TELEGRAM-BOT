import os, json, logging, threading
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID","0"))
BASE_URL = os.getenv("BASE_URL","")
PORT = int(os.getenv("PORT","10000"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("aiogram").setLevel(logging.ERROR)
os.makedirs("data/users", exist_ok=True); os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"): open("data/state.json","w").write("{}")
from web.app import app as flask_app
bot = Bot(token=BOT_TOKEN); dp = Dispatcher(bot)
from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers
def run_flask():
    logging.info(f"🌐 Starting Flask web server on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)
def start_services():
    threading.Thread(target=run_flask, daemon=True).start()
    logging.info("🤖 Telegram bot is starting...")
    executor.start_polling(dp, skip_updates=True)
if __name__ == "__main__":
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)
    start_services()
