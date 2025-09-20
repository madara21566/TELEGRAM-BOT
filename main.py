import os
import threading
import sqlite3
import datetime
import time
import psutil
import platform
from flask import Flask, render_template_string, request, redirect, session, send_file, jsonify
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Import from NIKALLLLLLL.py
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, set_country_code, set_group_number,
    make_vcf_command, merge_command, done_merge,
    handle_document, handle_text, OWNER_ID, ALLOWED_USERS,
    reset_settings, my_settings, txt2vcf, vcf2txt,
    button_handler   # ✅ inline menu callback
)

# Flask app for dashboard
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "supersecretkey")

# Bot token
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ================= Flask Routes =================

@app.route("/")
def index():
    return render_template_string("""
    <h2>🤖 VCF Bot Dashboard</h2>
    <p>Bot is running with inline menu system ✅</p>
    <ul>
        <li><a href="/status">Bot Status</a></li>
        <li><a href="/logs">View Logs</a></li>
    </ul>
    """)

@app.route("/status")
def status():
    uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
    return jsonify({
        "platform": platform.system(),
        "uptime": str(uptime),
        "cpu_percent": psutil.cpu_percent(),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage('/').percent
    })

@app.route("/logs")
def logs():
    if os.path.exists("bot_errors.log"):
        with open("bot_errors.log", "r") as f:
            return "<pre>" + f.read() + "</pre>"
    return "No logs yet."

# ================= Bot Runner =================

def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setfilename", set_filename))
    application.add_handler(CommandHandler("setcontactname", set_contact_name))
    application.add_handler(CommandHandler("setlimit", set_limit))
    application.add_handler(CommandHandler("setstart", set_start))
    application.add_handler(CommandHandler("setvcfstart", set_vcf_start))
    application.add_handler(CommandHandler("setcountrycode", set_country_code))
    application.add_handler(CommandHandler("setgroup", set_group_number))
    application.add_handler(CommandHandler("reset", reset_settings))
    application.add_handler(CommandHandler("mysettings", my_settings))
    application.add_handler(CommandHandler("makevcf", make_vcf_command))
    application.add_handler(CommandHandler("merge", merge_command))
    application.add_handler(CommandHandler("done", done_merge))
    application.add_handler(CommandHandler("txt2vcf", txt2vcf))
    application.add_handler(CommandHandler("vcf2txt", vcf2txt))

    # ✅ Inline menu handler
    application.add_handler(CallbackQueryHandler(button_handler))

    # File / text handlers
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Bot is running with inline menu...")
    application.run_polling()

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 Flask dashboard running on port {port}")
    app.run(host="0.0.0.0", port=port)

# ================= Main =================

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    run_flask()
