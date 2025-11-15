import os, logging, threading, time, asyncio
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
BASE_URL = os.getenv('BASE_URL', '')
PORT = int(os.getenv('PORT', '10000'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logging.getLogger('aiogram').setLevel(logging.ERROR)

os.makedirs('data/users', exist_ok=True)
os.makedirs('data/backups', exist_ok=True)
if not os.path.exists('data/state.json'):
    open('data/state.json', 'w').write('{}')

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

def run_flask():
    flask_app.run(host='0.0.0.0', port=PORT)

def expire_checker():
    while True:
        try:
            # free users 12h limit
            check_expired()
        except Exception as e:
            logging.error('expire error: %s', e)
        time.sleep(60)

async def _send_backup(path):
    try:
        await bot.send_document(
            OWNER_ID,
            open(path, 'rb'),
            caption='Auto backup (last 10 minutes state)'
        )
    except Exception as e:
        logging.error('send backup error: %s', e)

def backup_loop():
    # periodic: every 10 minutes
    while True:
        try:
            path = backup_projects()
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(_send_backup(path), loop)
        except Exception as e:
            logging.error('backup error: %s', e)
        time.sleep(600)

def start_services():
    # auto-restore from latest backup if exists
    try:
        last = backup_latest_path()
        if last:
            restore_from_zip(last)
            logging.info("Restored from latest backup at startup.")
    except Exception as e:
        logging.error("restore error: %s", e)

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()

    try:
        ensure_restart_on_boot()
    except Exception as e:
        logging.error("ensure_restart_on_boot error: %s", e)

    executor.start_polling(dp, skip_updates=True)

if __name__ == '__main__':
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)
    start_services()
