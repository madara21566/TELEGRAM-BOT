# =====================================================
# MAIN RUNNER – GOD MADARA VCF BOT (FINAL)
# Telegram + VCF + Access System + Flask (Render 24/7)
# =====================================================

import os
import threading
from flask import Flask
from telegram.ext import ApplicationBuilder

import vcf_bot
import access_system

# =====================================================
# REQUIRED ENV VARIABLES
# =====================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")
PORT = int(os.environ.get("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not set")
if not OWNER_ID:
    raise RuntimeError("❌ OWNER_ID not set")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set")

OWNER_ID = int(OWNER_ID)

# =====================================================
# FLASK APP (KEEP ALIVE FOR RENDER)
# =====================================================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running"

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# Flask background thread
threading.Thread(target=run_flask, daemon=True).start()

# =====================================================
# TELEGRAM APPLICATION
# =====================================================
application = ApplicationBuilder().token(BOT_TOKEN).build()

# =====================================================
# INIT DATABASE
# =====================================================
access_system.init_db()

# =====================================================
# SHARED BOT DATA (HOOKS)
# =====================================================
application.bot_data["access_check"] = access_system.check_access
application.bot_data["OWNER_ID"] = OWNER_ID

# =====================================================
# REGISTER HANDLERS
# =====================================================
vcf_bot.register_handlers(application)
access_system.register_handlers(application)

# =====================================================
# RUN BOT
# =====================================================
print("🚀 GOD MADARA VCF BOT STARTED")
application.run_polling()
