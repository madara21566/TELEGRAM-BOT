import NIKALLLLLLL
import os
import io
import threading
import sqlite3
import datetime
import traceback
from typing import Optional, List, Tuple

from flask import (
    Flask, render_template_string, request, redirect, session, jsonify, send_file, url_for
)
from werkzeug.security import generate_password_hash, check_password_hash

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Bot, InputFile

# ====== Import your VCF/bot command logic ======
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, set_country_code, set_group_number,
    make_vcf_command, merge_command, done_merge,
    handle_document, handle_text, OWNER_ID
, ALLOWED_USERS, reset_settings, my_settings)

# ================== ENV / CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
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
            user_id TEXT,
            username TEXT,
            action  TEXT,
            timestamp TEXT
        )''')
        # bot access list
        c.execute('''CREATE TABLE IF NOT EXISTS access (
            user_id   TEXT,
            username  TEXT,
            type      TEXT,
            expires_at TEXT
        )''')
        # admin users
        c.execute('''CREATE TABLE IF NOT EXISTS admins (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )''')
        # broadcast history
        c.execute('''CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin TEXT,
            kind TEXT,
            content TEXT,
            created_at TEXT
        )''')
        conn.commit()

        # bootstrap owner admin
        c.execute("SELECT COUNT(*) FROM admins")
        if (c.fetchone() or [0])[0] == 0:
            c.execute(
                "INSERT INTO admins (username, password_hash, role) VALUES (?, ?, ?)",
                ("owner", generate_password_hash(ADMIN_PASSWORD), "owner")
            )
            conn.commit()

def log_action(user_id: int, username: Optional[str], action: str):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
                  (str(user_id), username or 'N/A', action, now))
        conn.commit()

def is_authorized_in_db(user_id: int) -> bool:
    now = datetime.datetime.now()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # clear expired temporary access
        c.execute("""
            DELETE FROM access
            WHERE type='temporary'
              AND expires_at IS NOT NULL
              AND datetime(expires_at) < datetime(?)
        """, (now.strftime("%Y-%m-%d %H:%M:%S"),))
        c.execute("SELECT 1 FROM access WHERE user_id=?", (str(user_id),))
        row = c.fetchone()
        return bool(row)

def parse_duration(duration_str: str) -> Optional[datetime.datetime]:
    try:
        n = int(duration_str[:-1])
        unit = duration_str[-1]
        if unit == "m": return datetime.datetime.now() + datetime.timedelta(minutes=n)
        if unit == "h": return datetime.datetime.now() + datetime.timedelta(hours=n)
        if unit == "d": return datetime.datetime.now() + datetime.timedelta(days=n)
    except Exception:
        pass
    return None

# ================== TELEGRAM BOT ==================
application = Application.builder().token(BOT_TOKEN).build()
tg_bot = Bot(BOT_TOKEN)

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
    return user_id in NIKALLLLLLL.ALLOWED_USERS or is_authorized_in_db(user_id)

def protected(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        if not is_authorized(user.id):
            await update.message.reply_text("❌ You don't have access to use this bot.")
            return
        log_action(user.id, user.username, command_name)
        return await handler_func(update, context)
    return wrapper

application.add_handler(CommandHandler("start",          protected(start, "start")))
application.add_handler(CommandHandler('mysettings',    protected(my_settings, 'mysettings')))
application.add_handler(CommandHandler('reset',         protected(reset_settings, 'reset')))
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

# ================== FLASK APP ==================
start_time = datetime.datetime.now()
flask_app = Flask(__name__)
flask_app.secret_key = SECRET_KEY

# ✅ Uptime helper
def format_uptime(start_time):
    delta = datetime.datetime.now() - start_time
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
    else:
        return f"{hours:02}:{minutes:02}:{seconds:02}"

# ✅ Broadcast helper (background thread)
def send_broadcast(audience, kind, text, file):
    for uid in audience:
        try:
            if kind == 'text':
                tg_bot.send_message(chat_id=uid, text=text)
            elif kind == 'photo' and file:
                file.stream.seek(0)
                tg_bot.send_photo(chat_id=uid, photo=InputFile(file.stream, filename=file.filename), caption=text or None)
            elif kind == 'document' and file:
                file.stream.seek(0)
                tg_bot.send_document(chat_id=uid, document=InputFile(file.stream, filename=file.filename), caption=text or None)
        except Exception:
            pass
            # ================== FLASK ROUTES ==================

# Dashboard
@flask_app.route("/")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    uptime = format_uptime(start_time)
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM logs")
        total_actions = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
        total_users = c.fetchone()[0]
    return render_template_string("""
    <h1>📊 Bot Dashboard</h1>
    <p><b>Uptime:</b> {{uptime}}</p>
    <p><b>Total Users:</b> {{users}}</p>
    <p><b>Total Actions:</b> {{actions}}</p>
    <p><a href='/broadcast'>📢 Broadcast</a> | <a href='/access'>🔑 Access Panel</a> | <a href='/logout'>🚪 Logout</a></p>
    """, uptime=uptime, users=total_users, actions=total_actions)

# Login
@flask_app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username")
        pw = request.form.get("password")
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT password_hash FROM admins WHERE username=?", (uname,))
            row = c.fetchone()
            if row and check_password_hash(row[0], pw):
                session["logged_in"] = True
                session["username"] = uname
                return redirect(url_for("dashboard"))
        return "❌ Invalid credentials"
    return """
    <form method='post'>
      <input name='username' placeholder='Username'><br>
      <input type='password' name='password' placeholder='Password'><br>
      <button type='submit'>Login</button>
    </form>
    """

@flask_app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Broadcast page
@flask_app.route("/broadcast", methods=["GET","POST"])
def broadcast():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    if request.method == "POST":
        text = request.form.get("text")
        kind = request.form.get("kind")
        file = request.files.get("file")
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT DISTINCT user_id FROM logs")
            audience = [row[0] for row in c.fetchall()]
        # background thread
        threading.Thread(target=send_broadcast, args=(audience, kind, text, file), daemon=True).start()
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO broadcasts (admin, kind, content, created_at) VALUES (?, ?, ?, ?)",
                      (session.get("username"), kind, text or "", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        return "✅ Broadcast started!"
    return """
    <h2>📢 Broadcast</h2>
    <form method='post' enctype='multipart/form-data'>
      <textarea name='text' placeholder='Message text'></textarea><br>
      <select name='kind'>
        <option value='text'>Text</option>
        <option value='photo'>Photo</option>
        <option value='document'>Document</option>
      </select><br>
      <input type='file' name='file'><br>
      <button type='submit'>Send</button>
    </form>
    """

# Access panel
@flask_app.route("/access", methods=["GET","POST"])
def access_panel():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    if request.method == "POST":
        uid = request.form.get("user_id")
        uname = request.form.get("username")
        atype = request.form.get("type")
        duration = request.form.get("duration")
        expires_at = None
        if atype == "temporary":
            expires_at = parse_duration(duration)
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO access (user_id, username, type, expires_at) VALUES (?, ?, ?, ?)",
                      (str(uid), uname, atype, expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else None))
            conn.commit()
        return "✅ Access granted!"
    return """
    <h2>🔑 Access Panel</h2>
    <form method='post'>
      <input name='user_id' placeholder='User ID'><br>
      <input name='username' placeholder='Username'><br>
      <select name='type'>
        <option value='permanent'>Permanent</option>
        <option value='temporary'>Temporary</option>
      </select><br>
      <input name='duration' placeholder='(e.g. 1d, 12h)'><br>
      <button type='submit'>Grant Access</button>
    </form>
    """

# Webhook for Telegram
@flask_app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    application.update_queue.put_nowait(update)
    return "ok"

# ================== MAIN ==================
if __name__ == "__main__":
    init_db()
    print("✅ Bot & Web server starting...")
    flask_app.run(host="0.0.0.0", port=APP_PORT)
        
