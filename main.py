# =====================================================
# MAIN RUNNER – GOD MADARA (FIXED & STABLE)
# Telegram Bot + VCF Bot + Access System + Flask
# =====================================================

import os
import threading
from flask import Flask
from telegram.ext import ApplicationBuilder

# Import modules
import vcf_bot
import access_system

# =====================================================
# ENVIRONMENT VARIABLES (REQUIRED)
# =====================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")
PORT = int(os.environ.get("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN missing")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL missing")
if not OWNER_ID:
    raise RuntimeError("❌ OWNER_ID missing")

# =====================================================
# FLASK APP (RENDER KEEP-ALIVE)
# =====================================================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running"

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# Start Flask in background thread
threading.Thread(target=run_flask, daemon=True).start()

# =====================================================
# TELEGRAM APPLICATION
# =====================================================
application = ApplicationBuilder().token(BOT_TOKEN).build()

# =====================================================
# INITIALIZE DATABASE (POSTGRES)
# =====================================================
access_system.init_db()

# =====================================================
# INJECT ACCESS CHECK INTO VCF BOT
# =====================================================
application.bot_data["access_check"] = access_system.check_access

# =====================================================
# REGISTER HANDLERS
# =====================================================
# 1️⃣ ORIGINAL VCF BOT
vcf_bot.register_handlers(application)

# 2️⃣ ACCESS SYSTEM (ADMIN + KEY)
access_system.register_handlers(application)

# =====================================================
# RUN BOT
# =====================================================
print("🚀 GOD MADARA BOT STARTED")
application.run_polling()
