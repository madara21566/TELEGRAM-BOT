import asyncio
import subprocess
from threading import Thread

from flask import Flask
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiogram.filters import Command

# ---------------- CONFIG ----------------
MONITOR_BOT_TOKEN = "7727685861:AAEY6C4UYOALqsBOJprIz8WrLBAGrDHx_vc"
MAIN_BOT_TOKEN = "7869581039:AAF1qMiFYSABgPG21T8N4OFK-2rbh21uNBI"
TELEGRAM_CHAT_ID = 7640327597
CHECK_INTERVAL = 30  # seconds
CUSTOM_OFFLINE_MESSAGE = "⚠️ Main Bot is Offline! Running recovery script..."
RECOVERY_SCRIPT = "main_bot.py"
# ---------------------------------------

bot = Bot(token=MONITOR_BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

monitoring_task = None
monitoring_loop = None

app = Flask(__name__)

# ---------------- HELPER FUNCTIONS ----------------
async def is_main_bot_online():
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getMe"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                return data.get("ok", False)
    except Exception as e:
        print("Error checking main bot:", e)
        return False

async def monitor_main_bot(chat_id: int):
    already_alerted = False
    while True:
        online = await is_main_bot_online()
        if online:
            if already_alerted:
                await bot.send_message(chat_id=chat_id, text="✅ Main Bot is back online!")
                print("Main Bot is back online ✅")
                already_alerted = False
        else:
            print("Main Bot Offline ❌")
            if not already_alerted:
                try:
                    await bot.send_message(chat_id=chat_id, text=CUSTOM_OFFLINE_MESSAGE)
                    subprocess.Popen(["python3", RECOVERY_SCRIPT])
                    print("Recovery script started...")
                    already_alerted = True
                except Exception as e:
                    await bot.send_message(chat_id=chat_id, text=f"❌ Failed to send alert or run script:\n{e}")
        await asyncio.sleep(CHECK_INTERVAL)

# ---------------- TELEGRAM COMMANDS ----------------
@dp.message(Command(commands=["start_monitor"]))
async def start_monitoring(message: types.Message):
    global monitoring_task, monitoring_loop
    if monitoring_task is None or monitoring_task.done():
        monitoring_task = monitoring_loop.create_task(monitor_main_bot(message.chat.id))
        await message.reply("🟢 Monitoring started!")
    else:
        await message.reply("⚠️ Already monitoring!")

@dp.message(Command(commands=["stop_monitor"]))
async def stop_monitoring(message: types.Message):
    global monitoring_task
    if monitoring_task and not monitoring_task.done():
        monitoring_task.cancel()
        monitoring_task = None
        await message.reply("🔴 Monitoring stopped!")
    else:
        await message.reply("⚠️ Monitoring is not running.")

@dp.message(Command(commands=["status"]))
async def status(message: types.Message):
    online = await is_main_bot_online()
    status_text = "✅ Main Bot is Online" if online else "❌ Main Bot is Offline"
    await message.reply(status_text)

# ---------------- FLASK ROUTE FOR 24/7 ----------------
@app.route("/")
def home():
    return "Monitoring Bot is running 24/7 ✅"

# ---------------- RUN TELEGRAM BOT IN THREAD ----------------
def run_telegram_bot():
    global monitoring_loop
    monitoring_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(monitoring_loop)
    monitoring_loop.run_until_complete(dp.start_polling(bot))

# ---------------- MAIN ----------------
if __name__ == "__main__":
    # Run Telegram bot in a separate thread
    Thread(target=run_telegram_bot).start()
    
    # Run Flask app (keeps bot alive 24/7 on hosting platforms)
    app.run(host="0.0.0.0", port=8000)
