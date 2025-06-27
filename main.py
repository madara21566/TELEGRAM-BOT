from flask import Flask
import asyncio
import threading
from bot_runner import run_bot

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot + Website both running!"

def start_bot():
    asyncio.run(run_bot())

threading.Thread(target=start_bot, daemon=True).start()

# Flask will run through Gunicorn
