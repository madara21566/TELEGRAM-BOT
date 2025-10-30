import os
import json
import sqlite3
import subprocess
import threading
import time
import psutil
import zipfile
import secrets
import shutil
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, flash, send_from_directory, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ===== CONFIG =====
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '123456789'))
WEB_PASSWORD = os.getenv('WEB_PASSWORD', 'admin123')
DB_PATH = 'bot.db'
BACKUP_DIR = 'backups'
PROJECTS_DIR = 'user_projects'

os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

bot_locked = False
banned_users = set()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecret')

# ===== DATABASE =====
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        is_premium INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        created_at TEXT,
        fm_id TEXT,
        fm_password TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        name TEXT,
        path TEXT,
        pid INTEGER,
        start_time TEXT,
        status TEXT,
        run_command TEXT DEFAULT 'python main.py'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )''')
    c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
    conn.commit()
    conn.close()
init_db()

# ===== HELPERS =====
def create_backup():
    backup_path = os.path.join(BACKUP_DIR, f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')
    with zipfile.ZipFile(backup_path, 'w') as z:
        z.write(DB_PATH)
        for root, _, files in os.walk(PROJECTS_DIR):
            for f in files:
                z.write(os.path.join(root, f))
    return backup_path

def auto_backup():
    while True:
        time.sleep(3600)
        create_backup()
threading.Thread(target=auto_backup, daemon=True).start()

def is_admin(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM admins WHERE user_id=?', (uid,))
    r = c.fetchone()
    conn.close()
    return bool(r)

def generate_fm_credentials(uid):
    fm_id = secrets.token_hex(8)
    fm_pw = secrets.token_hex(8)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET fm_id=?, fm_password=? WHERE user_id=?', (fm_id, fm_pw, uid))
    conn.commit(); conn.close()
    return fm_id, fm_pw

def get_user_projects(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id,name,path,status FROM projects WHERE user_id=?', (uid,))
    data = c.fetchall()
    conn.close()
    return data

def start_project(uid, project_path, project_name, run_cmd='python main.py'):
    if bot_locked or uid in banned_users:
        return False
    try:
        proc = subprocess.Popen(run_cmd.split(), cwd=project_path,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        start_time = datetime.now().isoformat()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO projects (user_id,name,path,pid,start_time,status,run_command)'
                  ' VALUES (?,?,?,?,?,?,?)',
                  (uid, project_name, project_path, proc.pid, start_time, 'running', run_cmd))
        conn.commit(); conn.close()
        threading.Thread(target=monitor_project, args=(uid, proc.pid, project_name), daemon=True).start()
        return True
    except Exception as e:
        print("Start error:", e)
        return False

def stop_project(pid):
    try:
        os.kill(pid, 9)
    except Exception:
        pass
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE projects SET status=? WHERE pid=?', ('stopped', pid))
    conn.commit(); conn.close()

def monitor_project(uid, pid, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT is_premium FROM users WHERE user_id=?', (uid,))
    row = c.fetchone(); conn.close()
    if not row or not row[0]:
        time.sleep(12 * 3600)
        stop_project(pid)
        application.bot.send_message(chat_id=uid,
            text=f"Your project '{name}' stopped (12-hour free limit). Upgrade for 24/7.")

# ===== TELEGRAM HANDLERS (start/admin) =====
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in banned_users or bot_locked:
        await update.message.reply_text("Bot locked or you are banned.")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id,username,created_at)'
              ' VALUES (?,?,?)',
              (uid, update.effective_user.username, datetime.now().isoformat()))
    conn.commit(); conn.close()
    kb = [
        [InlineKeyboardButton("My Projects", callback_data='my_projects')],
        [InlineKeyboardButton("Buy Premium", callback_data='premium_buy')]
    ]
    await update.message.reply_text("Choose an action:",
                                    reply_markup=InlineKeyboardMarkup(kb))

async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    kb = [
        [InlineKeyboardButton("User Stats", callback_data='user_stats')],
        [InlineKeyboardButton("File Stats", callback_data='file_stats')],
        [InlineKeyboardButton("Running Statuses", callback_data='running_statuses')],
        [InlineKeyboardButton("Add Premium", callback_data='add_premium')],
        [InlineKeyboardButton("Remove Premium", callback_data='remove_premium')],
        [InlineKeyboardButton("Ban User", callback_data='ban_user')],
        [InlineKeyboardButton("Unban User", callback_data='unban_user')],
        [InlineKeyboardButton("Lock Bot", callback_data='lock_bot')],
        [InlineKeyboardButton("Unlock Bot", callback_data='unlock_bot')],
        [InlineKeyboardButton("Broadcast", callback_data='broadcast')],
        [InlineKeyboardButton("Backup", callback_data='backup')],
        [InlineKeyboardButton("Restart Bot", callback_data='restart_bot')]
    ]
    await update.message.reply_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(kb))
# ===== TELEGRAM CALLBACK HANDLER =====
async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    # Admin-only protection
    admin_only = [
        'user_stats','file_stats','running_statuses','add_premium','remove_premium',
        'ban_user','unban_user','lock_bot','unlock_bot','broadcast','backup','restart_bot'
    ]
    if data in admin_only and not is_admin(uid):
        await q.edit_message_text("Access denied.")
        return

    # --- User options ---
    if data == 'my_projects':
        kb = [
            [InlineKeyboardButton("New Project", callback_data='new_project')],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await q.edit_message_text("My Projects:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'premium_buy':
        await q.edit_message_text("Contact owner for Premium access.")

    elif data == 'new_project':
        await q.edit_message_text("Enter project name:")
        ctx.user_data['awaiting_name'] = True

    elif data == 'back':
        await start(update, ctx)

    # --- Admin options ---
    elif data == 'user_stats':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*),SUM(is_premium),SUM(banned) FROM users')
        t, p, b = c.fetchone()
        conn.close()
        await q.edit_message_text(f"Total: {t}\nPremium: {p}\nBanned: {b}")

    elif data == 'file_stats':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM projects')
        pr = c.fetchone()[0]
        conn.close()
        await q.edit_message_text(f"Total Projects: {pr}")

    elif data == 'running_statuses':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT name,status,pid FROM projects WHERE status="running"')
        rows = c.fetchall(); conn.close()
        txt = "\n".join([f"{n}: {s} (PID {p})" for n,s,p in rows]) or "No running projects."
        await q.edit_message_text(txt)

    elif data == 'add_premium':
        await q.edit_message_text("Send user ID to add Premium:")
        ctx.user_data['awaiting_premium_add'] = True

    elif data == 'remove_premium':
        await q.edit_message_text("Send user ID to remove Premium:")
        ctx.user_data['awaiting_premium_remove'] = True

    elif data == 'ban_user':
        await q.edit_message_text("Send user ID to ban:")
        ctx.user_data['awaiting_ban'] = True

    elif data == 'unban_user':
        await q.edit_message_text("Send user ID to unban:")
        ctx.user_data['awaiting_unban'] = True

    elif data == 'lock_bot':
        global bot_locked
        bot_locked = True
        await q.edit_message_text("Bot locked.")

    elif data == 'unlock_bot':
        bot_locked = False
        await q.edit_message_text("Bot unlocked.")

    elif data == 'broadcast':
        await q.edit_message_text("Send broadcast message:")
        ctx.user_data['awaiting_broadcast'] = True

    elif data == 'backup':
        path = create_backup()
        await q.edit_message_text(f"Backup created: {path}")

    elif data == 'restart_bot':
        await q.edit_message_text("Restarting bot…")
        create_backup()
        os._exit(0)

# ===== MESSAGE HANDLER =====
async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message.text if update.message else ""

    # --- Create project flow ---
    if ctx.user_data.get('awaiting_name'):
        ctx.user_data['project_name'] = msg
        ctx.user_data['awaiting_name'] = False
        await update.message.reply_text("Send ZIP or files for your project:")
        ctx.user_data['awaiting_files'] = True
        return

    elif ctx.user_data.get('awaiting_files'):
        if update.message.document:
            files = [update.message.document]
            user_dir = os.path.join(PROJECTS_DIR, str(uid))
            proj_dir = os.path.join(user_dir, ctx.user_data['project_name'])
            os.makedirs(proj_dir, exist_ok=True)
            for f in files:
                path = os.path.join(proj_dir, f.file_name)
                await f.download_to_drive(path)
                if f.file_name.endswith('.zip'):
                    with zipfile.ZipFile(path, 'r') as z:
                        z.extractall(proj_dir)
                    os.remove(path)
            await update.message.reply_text("✅ Files uploaded successfully!")
            kb = [
                [InlineKeyboardButton("Launch File Manager", callback_data=f'fm_{uid}')],
                [InlineKeyboardButton("Deployment", callback_data=f'deploy_{uid}')],
                [InlineKeyboardButton("Back", callback_data='my_projects')]
            ]
            await update.message.reply_text("Project ready:", reply_markup=InlineKeyboardMarkup(kb))
            ctx.user_data['awaiting_files'] = False
            return

    # --- Premium/Admin updates ---
    if ctx.user_data.get('awaiting_premium_add'):
        try:
            id_ = int(msg)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('UPDATE users SET is_premium=1 WHERE user_id=?', (id_,))
            conn.commit(); conn.close()
            await update.message.reply_text("✅ Premium added.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        ctx.user_data['awaiting_premium_add'] = False

    elif ctx.user_data.get('awaiting_premium_remove'):
        id_ = int(msg)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('UPDATE users SET is_premium=0 WHERE user_id=?', (id_,))
        conn.commit(); conn.close()
        await update.message.reply_text("✅ Premium removed.")
        ctx.user_data['awaiting_premium_remove'] = False

    elif ctx.user_data.get('awaiting_ban'):
        id_ = int(msg)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('UPDATE users SET banned=1 WHERE user_id=?', (id_,))
        conn.commit(); conn.close()
        banned_users.add(id_)
        await update.message.reply_text("🚫 User banned.")
        ctx.user_data['awaiting_ban'] = False

    elif ctx.user_data.get('awaiting_unban'):
        id_ = int(msg)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('UPDATE users SET banned=0 WHERE user_id=?', (id_,))
        conn.commit(); conn.close()
        banned_users.discard(id_)
        await update.message.reply_text("✅ User unbanned.")
        ctx.user_data['awaiting_unban'] = False

    elif ctx.user_data.get('awaiting_broadcast'):
        text = msg
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT user_id FROM users WHERE banned=0')
        users = [r[0] for r in c.fetchall()]
        conn.close()
        for u in users:
            try:
                await ctx.bot.send_message(chat_id=u, text=text)
            except:
                pass
        await update.message.reply_text("📢 Broadcast sent.")
        ctx.user_data['awaiting_broadcast'] = False
  # ===== FLASK FILE MANAGER ROUTES =====
@app.route('/filemanager/<int:user_id>', methods=['GET', 'POST'])
def filemanager(user_id):
    if request.method == 'POST':
        fm_id = request.form.get('fm_id')
        fm_password = request.form.get('fm_password')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT fm_id, fm_password FROM users WHERE user_id=?', (user_id,))
        row = c.fetchone(); conn.close()
        if row and row[0] == fm_id and row[1] == fm_password:
            session['fm_logged_in'] = user_id
            return redirect(url_for('fm_dashboard', user_id=user_id))
        flash("Invalid credentials.")
    return render_template('fm_login.html')

@app.route('/fm_dashboard/<int:user_id>')
def fm_dashboard(user_id):
    if 'fm_logged_in' not in session or session['fm_logged_in'] != user_id:
        return redirect(url_for('filemanager', user_id=user_id))
    user_dir = os.path.join(PROJECTS_DIR, str(user_id))
    files = os.listdir(user_dir) if os.path.exists(user_dir) else []
    return render_template('fm_dashboard.html', files=files, user_id=user_id)

@app.route('/download/<int:user_id>/<filename>')
def download_file(user_id, filename):
    if 'fm_logged_in' not in session or session['fm_logged_in'] != user_id:
        return redirect(url_for('filemanager', user_id=user_id))
    user_dir = os.path.join(PROJECTS_DIR, str(user_id))
    return send_from_directory(user_dir, filename)

@app.route('/logout')
def logout():
    session.pop('fm_logged_in', None)
    return redirect('/')

# ===== FLASK ADMIN DASHBOARD =====
@app.route('/')
def login():
    if 'logged_in' in session:
        return redirect('/dashboard')
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def do_login():
    pw = request.form.get('password')
    if pw == WEB_PASSWORD:
        session['logged_in'] = True
        return redirect('/dashboard')
    flash("Invalid password.")
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'logged_in' not in session:
        return redirect('/')
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    storage = psutil.disk_usage('/').percent
    uptime = time.time() - psutil.boot_time()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM projects WHERE status="running"')
    running = c.fetchone()[0]
    conn.close()
    return render_template('dashboard.html',
                           cpu=cpu, ram=ram, storage=storage,
                           uptime=uptime, users=users, projects=running)

# ===== START BOT + FLASK =====
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("admin", admin_panel))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(MessageHandler(filters.Document.ALL, message_handler))

def run_bot():
    application.run_polling()

if __name__ == '__main__':
    # Run both Flask and Telegram bot in separate threads
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
  
