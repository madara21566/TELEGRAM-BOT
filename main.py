import os, logging, threading, time
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

from utils.monitor import check_expired
from utils.backup import backup_projects, restore_latest_if_missing
from utils.helpers import load_json
from utils.runner import start_script

def run_flask():
    logging.info(f"🌐 Starting Flask web server on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)

def expire_checker():
    while True:
        try:
            check_expired()
        except Exception as e:
            logging.error(f"expire_checker error: {e}")
        time.sleep(60)

def backup_loop():
    while True:
        try:
            backup_projects()
        except Exception as e:
            logging.error(f"backup_loop error: {e}")
        time.sleep(600)  # every 10 min

def restore_running_after_restart():
    """
    On restart:
    - For each entry previously running:
      - If project folder missing → restore latest backup.
      - Start the script again (respecting premium/free runtime markers already in state).
    """
    time.sleep(2)  # give FS a moment
    st = load_json()
    procs = st.get("procs", {})
    count = 0
    for suid, items in procs.items():
        uid = int(suid)
        for key, meta in list(items.items()):
            proj = key.split(":")[0]
            # restore project files if missing
            try:
                restore_latest_if_missing(suid, proj)
            except Exception:
                pass
            try:
                start_script(uid, proj, None)
                count += 1
            except Exception as e:
                logging.error(f"restore start failed {suid}/{proj}: {e}")
    if count:
        logging.info(f"♻️ Restored and started {count} projects after restart")

def start_services():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()
    threading.Thread(target=restore_running_after_restart, daemon=True).start()
    logging.info("🤖 Telegram bot is starting...")
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)
    start_services()
