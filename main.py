import NIKALLLLLLL
import os
import io
import threading
import sqlite3
import datetime
import traceback
from typing import Optional, List, Tuple

# ===== UPTIME FIX =====
start_time = datetime.datetime.now()

def format_uptime():
    delta = datetime.datetime.now() - start_time
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
    else:
        return f"{hours:02}:{minutes:02}:{seconds:02}"

from flask import (
    Flask, render_template_string, request, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Bot, InputFile

# ====== Import your VCF/bot command logic ======
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, set_country_code, set_group_number,
    make_vcf_command, merge_command, done_merge,
    handle_document, handle_text, OWNER_ID,
    ALLOWED_USERS, reset_settings, my_settings
)

# ================== ENV / CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SECRET_KEY = os.environ.get("FLASK_SECRET", "super-secret-key")
APP_PORT = int(os.environ.get("PORT", "8080"))

DB_FILE = "bot_stats.db"
ERROR_LOG = "bot_errors.log"

# ================== DB SETUP ==================
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # activity logs
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            user_id INTEGER,
            username TEXT,
            action  TEXT,
            timestamp TEXT
        )''')
        conn.commit()

def log_action(user_id: int, username: Optional[str], action: str):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
                  (user_id, username or 'N/A', action, now))
        conn.commit()

# ================== TELEGRAM BOT ==================
application = Application.builder().token(BOT_TOKEN).build()
tg_bot = Bot(BOT_TOKEN)

# error handler -> file + DM owner
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.utcnow()} - {error_text}\n\n")
    except Exception:
        pass
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

def is_authorized(user_id: int) -> bool:
    return user_id in NIKALLLLLLL.ALLOWED_USERS

def protected(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        if not is_authorized(user.id):
            await update.message.reply_text("❌ You don't have access to use this bot.")
            return
        log_action(user.id, user.username, command_name)
        return await handler_func(update, context)
    return wrapper

# register handlers
application.add_handler(CommandHandler("start",          protected(start, "start")))
application.add_handler(CommandHandler("mysettings",    protected(my_settings, "mysettings")))
application.add_handler(CommandHandler("reset",         protected(reset_settings, "reset")))
application.add_handler(CommandHandler("setfilename",   protected(set_filename, "setfilename")))
application.add_handler(CommandHandler("setcontactname",protected(set_contact_name, "setcontactname")))
application.add_handler(CommandHandler("setlimit",      protected(set_limit, "setlimit")))
application.add_handler(CommandHandler("setstart",      protected(set_start, "setstart")))
application.add_handler(CommandHandler("setvcfstart",   protected(set_vcf_start, "setvcfstart")))
application.add_handler(CommandHandler("setcountrycode",protected(set_country_code, "setcountrycode")))
application.add_handler(CommandHandler("setgroup",      protected(set_group_number, "setgroup")))
application.add_handler(CommandHandler("makevcf",       protected(make_vcf_command, "makevcf")))
application.add_handler(CommandHandler("merge",         protected(merge_command, "merge")))
application.add_handler(CommandHandler("done",          protected(done_merge, "done")))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_error_handler(error_handler)

# ================== FLASK APP (PUBLIC DASHBOARD) ==================
flask_app = Flask(__name__)
flask_app.secret_key = SECRET_KEY

def chart_data_last_7_days() -> Tuple[List[str], List[int], List[int]]:
    today = datetime.datetime.now().date()
    days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
    labels = [d.strftime('%d %b') for d in days]

    daily_users = {d.strftime('%Y-%m-%d'): set() for d in days}
    daily_files = {d.strftime('%Y-%m-%d'): 0 for d in days}

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT user_id, action, date(timestamp)
            FROM logs
            WHERE date(timestamp) >= date(?)
        """, ((today - datetime.timedelta(days=6)).strftime('%Y-%m-%d'),))
        for uid, action, dt in c.fetchall():
            if dt in daily_users: daily_users[dt].add(uid)
            if dt in daily_files and action == 'makevcf': daily_files[dt] += 1

    users_counts = [len(daily_users[d.strftime('%Y-%m-%d')]) for d in days]
    files_counts = [daily_files[d.strftime('%Y-%m-%d')] for d in days]
    return labels, users_counts, files_counts

def hourly_distribution_today() -> Tuple[List[str], List[int]]:
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    buckets = {f"{h:02d}:00": 0 for h in range(24)}
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT strftime('%H:00', timestamp) AS hh, COUNT(*)
            FROM logs
            WHERE date(timestamp) = date(?)
            GROUP BY 1
        """, (today,))
        for hh, cnt in c.fetchall():
            if hh in buckets: buckets[hh] = cnt
    labels = list(buckets.keys())
    values = [buckets[k] for k in labels]
    return labels, values

# ---------- Public Dashboard ----------
@flask_app.route('/')
def dashboard():
    uptime = format_uptime()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
        total_users = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs WHERE action='makevcf'")
        total_files = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs")
        total_actions = c.fetchone()[0] or 0
        c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC LIMIT 50")
        logs = c.fetchall()

    return render_template_string("""
    <!doctype html>
    <html lang="en"><head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Bot Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
    body{background:#0b0f14;color:#e5e7eb}
    .card{border:none;border-radius:1rem;box-shadow:0 10px 30px rgba(0,0,0,.25)}
    .table thead th{position:sticky;top:0;background:#0f172a}
    </style>
    </head>
    <body>
    <div class="container py-4">
      <h3 class="fw-bold">🤖 Telegram Bot Dashboard</h3>
      <div class="row g-3 mb-3">
        <div class="col-md-3"><div class="card p-3 bg-primary text-white"><div>👥 Users</div><div class="fs-3 fw-bold">{{users}}</div></div></div>
        <div class="col-md-3"><div class="card p-3 bg-success text-white"><div>📁 Files</div><div class="fs-3 fw-bold">{{files}}</div></div></div>
        <div class="col-md-3"><div class="card p-3 bg-info text-white"><div>⚡ Actions</div><div class="fs-3 fw-bold">{{actions}}</div></div></div>
        <div class="col-md-3"><div class="card p-3 bg-warning"><div>⏱ Uptime</div><div class="fs-3 fw-bold" id="uptime">{{uptime}}</div></div></div>
      </div>
    </div>
    </body></html>
    """, uptime=uptime, users=total_users, files=total_files, actions=total_actions, logs=logs)

# ---------- Chart APIs ----------
@flask_app.route('/api/chart-data')
def api_chart():
    labels, daily_users, daily_files = chart_data_last_7_days()
    return jsonify({"labels": labels, "daily_users": daily_users, "daily_files": daily_files})

@flask_app.route('/api/hourly-data')
def api_hourly():
    labels, values = hourly_distribution_today()
    return jsonify({"labels": labels, "values": values})

@flask_app.route('/api/errors-tail')
def api_errors_tail():
    lines = []
    try:
        if os.path.exists(ERROR_LOG):
            with open(ERROR_LOG, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-12:]
    except Exception as e:
        lines = [f"(error reading log: {e})"]
    return jsonify(lines)

# ================== RUN ==================
def run_flask():
    try:
        flask_app.run(host='0.0.0.0', port=APP_PORT)
    except Exception as e:
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.utcnow()} - Flask Error: {e}\n")
        except Exception:
            pass
        try:
            tg_bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Flask Crash Alert ⚠️\n\n{str(e)}")
        except Exception:
            pass

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    application.run_polling()
    
