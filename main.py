# main.py
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

# ====== CONFIG ======
BOT_TOKEN = os.getenv('BOT_TOKEN')
try:
    ADMIN_ID = int(os.getenv('ADMIN_ID', '123456789'))
except Exception:
    ADMIN_ID = 123456789
WEB_PASSWORD = os.getenv('WEB_PASSWORD', 'admin123')
DB_PATH = 'bot.db'
BACKUP_DIR = 'backups'
PROJECTS_DIR = 'user_projects'
os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# ====== GLOBALS ======
bot_locked = False
banned_users = set()

# ====== FLASK APP ======
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecret')

# ====== DATABASE INITIALIZATION ======
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # users table
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
    # projects table
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        path TEXT,
        pid INTEGER,
        start_time TEXT,
        status TEXT,
        run_command TEXT DEFAULT 'python main.py'
    )''')
    # admins table
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )''')
    # ensure admin exists
    c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
    conn.commit()
    conn.close()

init_db()

# ====== HELPERS ======
def now_iso():
    return datetime.now().isoformat()

def create_backup():
    try:
        backup_path = os.path.join(BACKUP_DIR, f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')
        with zipfile.ZipFile(backup_path, 'w') as zipf:
            if os.path.exists(DB_PATH):
                zipf.write(DB_PATH)
            for root, dirs, files in os.walk(PROJECTS_DIR):
                for file in files:
                    zipf.write(os.path.join(root, file))
        return backup_path
    except Exception as e:
        print("Backup error:", e)
        return None

def auto_backup():
    while True:
        try:
            time.sleep(3600)
            create_backup()
        except Exception as e:
            print("Auto-backup loop error:", e)
            time.sleep(60)

threading.Thread(target=auto_backup, daemon=True).start()

def is_admin(uid):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT 1 FROM admins WHERE user_id=?', (uid,))
        r = c.fetchone()
        conn.close()
        return bool(r)
    except Exception:
        return False

def add_admin(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (uid,))
    conn.commit()
    conn.close()

def remove_admin(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM admins WHERE user_id=?', (uid,))
    conn.commit()
    conn.close()

def generate_fm_credentials(uid):
    fm_id = secrets.token_hex(8)
    fm_pw = secrets.token_hex(8)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET fm_id=?, fm_password=? WHERE user_id=?', (fm_id, fm_pw, uid))
    conn.commit()
    conn.close()
    return fm_id, fm_pw

def ensure_user_exists(uid, username=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)',
              (uid, username, now_iso()))
    conn.commit()
    conn.close()

def get_user_projects(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name, path, status, pid FROM projects WHERE user_id=?', (uid,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_project_by_id(pid_or_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # try by id first
    c.execute('SELECT id, user_id, name, path, pid, status, run_command FROM projects WHERE id=?', (pid_or_id,))
    r = c.fetchone()
    if r:
        conn.close()
        return r
    # then by pid
    c.execute('SELECT id, user_id, name, path, pid, status, run_command FROM projects WHERE pid=?', (pid_or_id,))
    r = c.fetchone()
    conn.close()
    return r

def start_project(uid, project_path, project_name, run_cmd='python main.py'):
    if bot_locked or uid in banned_users:
        return False
    try:
        # Make sure path exists
        if not os.path.exists(project_path):
            os.makedirs(project_path, exist_ok=True)
        # start process
        proc = subprocess.Popen(run_cmd.split(), cwd=project_path,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        start_time = now_iso()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO projects (user_id, name, path, pid, start_time, status, run_command) VALUES (?,?,?,?,?,?,?)',
                  (uid, project_name, project_path, proc.pid, start_time, 'running', run_cmd))
        conn.commit()
        conn.close()
        threading.Thread(target=monitor_project, args=(uid, proc.pid, project_name), daemon=True).start()
        return True
    except Exception as e:
        print("Start project error:", e)
        return False

def stop_project(pid):
    try:
        os.kill(pid, 9)
    except Exception:
        try:
            # Windows fallback
            subprocess.run(['taskkill', '/F', '/PID', str(pid)])
        except Exception:
            pass
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE projects SET status=? WHERE pid=?', ('stopped', pid))
    conn.commit()
    conn.close()

def monitor_project(uid, pid, name):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT is_premium FROM users WHERE user_id=?', (uid,))
        row = c.fetchone()
        conn.close()
        is_premium = bool(row and row[0])
        if not is_premium:
            # free tier = 12 hours
            time.sleep(12 * 3600)
            # double-check if process still running
            try:
                os.kill(pid, 0)
                # still running -> stop
                stop_project(pid)
                try:
                    application.bot.send_message(chat_id=uid, text=f"Your project '{name}' has stopped (free tier 12-hour limit). Upgrade for 24/7.")
                except Exception:
                    pass
            except Exception:
                # process not running
                pass
    except Exception as e:
        print("Monitor project error:", e)

def install_requirements(path):
    req_path = os.path.join(path, 'requirements.txt')
    if os.path.exists(req_path):
        try:
            subprocess.run(['pip', 'install', '-r', req_path], check=True)
            return True
        except Exception as e:
            print("Install req error:", e)
            return False
    return False

def clean_old_files(days=30):
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    for root, dirs, files in os.walk(PROJECTS_DIR):
        for f in files:
            fp = os.path.join(root, f)
            try:
                if datetime.fromtimestamp(os.path.getmtime(fp)) < cutoff:
                    os.remove(fp)
                    removed += 1
            except Exception:
                pass
    return removed

def get_system_info():
    try:
        return {
            'os': os.name,
            'cpu_percent': psutil.cpu_percent(),
            'ram_percent': psutil.virtual_memory().percent,
            'disk_total_gb': psutil.disk_usage('/').total / 1e9,
            'disk_used_percent': psutil.disk_usage('/').percent,
            'cpu_count': psutil.cpu_count(),
            'uptime_seconds': time.time() - psutil.boot_time()
        }
    except Exception as e:
        print("System info error:", e)
        return {}

# ====== TELEGRAM HANDLERS ======
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user_exists(uid, update.effective_user.username)
    if uid in banned_users or bot_locked:
        await update.message.reply_text("Bot is locked or you are banned.")
        return
    kb = [
        [InlineKeyboardButton("My Projects", callback_data='my_projects')],
        [InlineKeyboardButton("New Project", callback_data='new_project')],
        [InlineKeyboardButton("Admin Panel", callback_data='admin_panel') if is_admin(uid) else InlineKeyboardButton("Buy Premium", callback_data='premium_buy')]
    ]
    await update.message.reply_text("Welcome! Choose an action:", reply_markup=InlineKeyboardMarkup(kb))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("You are not admin.")
        return
    kb = [
        [InlineKeyboardButton("User Stats", callback_data='user_stats')],
        [InlineKeyboardButton("File Stats", callback_data='file_stats')],
        [InlineKeyboardButton("Running Statuses", callback_data='running_statuses')],
        [InlineKeyboardButton("Add Premium", callback_data='add_premium')],
        [InlineKeyboardButton("Remove Premium", callback_data='remove_premium')],
        [InlineKeyboardButton("Add Admin", callback_data='add_admin')],
        [InlineKeyboardButton("Remove Admin", callback_data='remove_admin')],
        [InlineKeyboardButton("Ban User", callback_data='ban_user')],
        [InlineKeyboardButton("Unban User", callback_data='unban_user')],
        [InlineKeyboardButton("System Info", callback_data='system_info')],
        [InlineKeyboardButton("Lock Bot", callback_data='lock_bot')],
        [InlineKeyboardButton("Unlock Bot", callback_data='unlock_bot')],
        [InlineKeyboardButton("Broadcast", callback_data='broadcast')],
        [InlineKeyboardButton("Clean Old Files", callback_data='clean_files')],
        [InlineKeyboardButton("Backup", callback_data='backup')],
        [InlineKeyboardButton("View Logs", callback_data='view_logs')],
        [InlineKeyboardButton("Restart Bot", callback_data='restart_bot')]
    ]
    await update.message.reply_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(kb))

# Re-create function name used in other places
async def show_admin_panel_by_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await admin_panel(update, context)

# Callback (button) handler -- many duplicated branches preserved
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    # Quick admin-only guard for specific keys
    admin_only_keys = {
        'user_stats', 'file_stats', 'running_statuses', 'add_premium', 'remove_premium',
        'add_admin', 'remove_admin', 'ban_user', 'unban_user', 'system_info',
        'lock_bot', 'unlock_bot', 'broadcast', 'clean_files', 'backup', 'view_logs', 'restart_bot'
    }
    if data in admin_only_keys and not is_admin(uid):
        await query.edit_message_text("Access denied.")
        return

    # --- user-facing / general ---
    if data == 'my_projects':
        projects = get_user_projects(uid)
        if not projects:
            kb = [[InlineKeyboardButton("New Project", callback_data='new_project')]]
            await query.edit_message_text("No projects yet. Create one:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            kb = []
            for p in projects:
                pid, name, path, status, os_pid = p[0], p[1], p[2], p[3], p[4]
                kb.append([InlineKeyboardButton(f"{name} ({status})", callback_data=f'manage_{pid}')])
            kb.append([InlineKeyboardButton("New Project", callback_data='new_project')])
            await query.edit_message_text("Your Projects:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data == 'new_project':
        await query.edit_message_text("Send the project name:")
        context.user_data['awaiting_name'] = True
        return

    if data == 'premium_buy':
        await query.edit_message_text("Contact owner for premium. Contact via admin account.")
        return

    # --- manage project (preserve original repetitive branches) ---
    if data.startswith('manage_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        # Build management keyboard (duplicate-like original)
        kb = [
            [InlineKeyboardButton("Launch File Manager", callback_data=f'fm_{project_id}')],
            [InlineKeyboardButton("Deployment", callback_data=f'deploy_{project_id}')],
            [InlineKeyboardButton("Delete Project", callback_data=f'delete_{project_id}')],
            [InlineKeyboardButton("Back", callback_data='my_projects')]
        ]
        await query.edit_message_text("Manage project:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # fm_ open file manager credentials
    if data.startswith('fm_'):
        # data may be fm_<project_id> or fm_userid
        try:
            ident = int(data.split('_', 1)[1])
        except Exception:
            ident = uid
        fm_id, fm_pw = generate_fm_credentials(uid)
        link = f"https://your-render-app.onrender.com/filemanager/{uid}"
        await query.edit_message_text(f"File Manager Link: {link}\nID: {fm_id}\nPassword: {fm_pw}")
        return

    # deploy options (duplicate blocks for original likeness)
    if data.startswith('deploy_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        kb = [
            [InlineKeyboardButton("Start", callback_data=f'start_{project_id}')],
            [InlineKeyboardButton("Stop", callback_data=f'stop_{project_id}')],
            [InlineKeyboardButton("Restart", callback_data=f'restart_{project_id}')],
            [InlineKeyboardButton("Logs", callback_data=f'logs_{project_id}')],
            [InlineKeyboardButton("Status", callback_data=f'status_{project_id}')],
            [InlineKeyboardButton("Usages", callback_data=f'usages_{project_id}')],
            [InlineKeyboardButton("Install Requirements", callback_data=f'install_req_{project_id}')],
            [InlineKeyboardButton("Edit Run Commands", callback_data=f'edit_cmd_{project_id}')],
            [InlineKeyboardButton("Back", callback_data=f'manage_{project_id}')]
        ]
        await query.edit_message_text("Deployment Options:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # start_ duplicate block
    if data.startswith('start_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT path, name, run_command FROM projects WHERE id=?', (project_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            await query.edit_message_text("Project not found.")
            return
        path, name, cmd = row
        started = start_project(uid, path, name, cmd)
        if started:
            await query.edit_message_text("Project started!")
        else:
            await query.edit_message_text("Failed to start.")
        return

    # stop_ duplicate block
    if data.startswith('stop_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT pid FROM projects WHERE id=?', (project_id,))
        row = c.fetchone()
        conn.close()
        if not row or not row[0]:
            await query.edit_message_text("No running process found.")
            return
        pid = row[0]
        stop_project(pid)
        await query.edit_message_text("Project stopped.")
        return

    # restart_ duplicate block
    if data.startswith('restart_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        # stop then start
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT pid, path, name, run_command FROM projects WHERE id=?', (project_id,))
        row = c.fetchone()
        conn.close()
        if row:
            pid, path, name, cmd = row[0], row[1], row[2], row[3]
            if pid:
                stop_project(pid)
            ok = start_project(uid, path, name, cmd)
            if ok:
                await query.edit_message_text("Project restarted.")
            else:
                await query.edit_message_text("Failed to restart.")
        else:
            await query.edit_message_text("Project not found.")
        return

    # logs_ duplicate block
    if data.startswith('logs_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        # if we had logs stored, would fetch; placeholder:
        await query.edit_message_text("Logs: [stdout/stderr not captured in this build].")
        return

    # status_ duplicate block
    if data.startswith('status_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT status FROM projects WHERE id=?', (project_id,))
        r = c.fetchone()
        conn.close()
        status = r[0] if r else "unknown"
        await query.edit_message_text(f"Status: {status}")
        return

    # usages_ duplicate block
    if data.startswith('usages_'):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        await query.edit_message_text(f"CPU: {cpu}%, RAM: {ram}%")
        return

    # install_req_ duplicate block
    if data.startswith('install_req_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT path FROM projects WHERE id=?', (project_id,))
        r = c.fetchone()
        conn.close()
        if not r:
            await query.edit_message_text("Project not found.")
            return
        path = r[0]
        ok = install_requirements(path)
        if ok:
            await query.edit_message_text("Requirements installed.")
        else:
            await query.edit_message_text("Failed to install requirements / requirements.txt missing.")
        return

    # edit_cmd_ duplicate block
    if data.startswith('edit_cmd_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        context.user_data['editing_cmd'] = project_id
        await query.edit_message_text("Send new run command (e.g., python app.py):")
        return

    # delete_ duplicate block (keeps original structure)
    if data.startswith('delete_'):
        try:
            project_id = int(data.split('_', 1)[1])
        except Exception:
            await query.edit_message_text("Invalid project id.")
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT path FROM projects WHERE id=?', (project_id,))
        r = c.fetchone()
        if r:
            path = r[0]
            # delete folder
            try:
                if os.path.exists(path):
                    shutil.rmtree(path)
            except Exception:
                pass
        c.execute('DELETE FROM projects WHERE id=?', (project_id,))
        conn.commit()
        conn.close()
        await query.edit_message_text("Project deleted.")
        return

    # --- Admin actions preserved with duplicates ---
    if data == 'user_stats':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*), SUM(is_premium), SUM(banned) FROM users')
        row = c.fetchone()
        conn.close()
        total = row[0] or 0
        premium = row[1] or 0
        banned = row[2] or 0
        await query.edit_message_text(f"Total Users: {total}\nPremium: {premium}\nBanned: {banned}")
        return

    if data == 'file_stats':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM projects')
        tot = c.fetchone()[0]
        conn.close()
        await query.edit_message_text(f"Total Projects: {tot}")
        return

    if data == 'running_statuses':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT name, status, pid FROM projects WHERE status="running"')
        rows = c.fetchall()
        conn.close()
        if not rows:
            await query.edit_message_text("No running projects.")
        else:
            text = "\n".join([f"{name}: {status} (PID: {pid})" for name, status, pid in rows])
            await query.edit_message_text(text)
        return

    if data == 'add_premium':
        context.user_data['awaiting_premium_add'] = True
        await query.edit_message_text("Send user ID to add premium:")
        return

    if data == 'remove_premium':
        context.user_data['awaiting_premium_remove'] = True
        await query.edit_message_text("Send user ID to remove premium:")
        return

    if data == 'add_admin':
        context.user_data['awaiting_admin_add'] = True
        await query.edit_message_text("Send user ID to add as admin:")
        return

    if data == 'remove_admin':
        context.user_data['awaiting_admin_remove'] = True
        await query.edit_message_text("Send user ID to remove from admins:")
        return

    if data == 'ban_user':
        context.user_data['awaiting_ban'] = True
        await query.edit_message_text("Send user ID to ban:")
        return

    if data == 'unban_user':
        context.user_data['awaiting_unban'] = True
        await query.edit_message_text("Send user ID to unban:")
        return

    if data == 'system_info':
        info = get_system_info()
        text = "\n".join([f"{k}: {v}" for k, v in info.items()])
        await query.edit_message_text(text)
        return

    if data == 'lock_bot':
        global bot_locked
        bot_locked = True
        await query.edit_message_text("Bot locked.")
        return

    if data == 'unlock_bot':
        bot_locked = False
        await query.edit_message_text("Bot unlocked.")
        return

    if data == 'broadcast':
        context.user_data['awaiting_broadcast'] = True
        await query.edit_message_text("Send the broadcast message:")
        return

    if data == 'clean_files':
        removed = clean_old_files(days=30)
        await query.edit_message_text(f"Cleaned {removed} files older than 30 days.")
        return

    if data == 'backup':
        path = create_backup()
        if path:
            await query.edit_message_text(f"Backup created: {path}")
        else:
            await query.edit_message_text("Backup failed.")
        return

    if data == 'view_logs':
        await query.edit_message_text("Logs: [Not implemented: attach log viewer separately]")
        return

    if data == 'restart_bot':
        await query.edit_message_text("Restarting bot...")
        create_backup()
        os._exit(0)
        return

    # fallback
    await query.edit_message_text("Unknown command or action.")

# ===== Message handler (long and preserves original structure) =====
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # handle both text messages and documents
    uid = update.effective_user.id
    text = update.message.text if update.message and update.message.text else None
    ensure_user_exists(uid, update.effective_user.username)

    # Editing run command handling (duplicate in original)
    if 'editing_cmd' in context.user_data and text:
        project_id = context.user_data.get('editing_cmd')
        try:
            project_id = int(project_id)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('UPDATE projects SET run_command=? WHERE id=?', (text, project_id))
            conn.commit()
            conn.close()
            await update.message.reply_text("Run command updated.")
        except Exception as e:
            await update.message.reply_text(f"Error updating run command: {e}")
        context.user_data.pop('editing_cmd', None)
        return

    # awaiting_premium_add
    if context.user_data.get('awaiting_premium_add') and text:
        try:
            uid_to = int(text.strip())
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('UPDATE users SET is_premium=1 WHERE user_id=?', (uid_to,))
            conn.commit()
            conn.close()
            await update.message.reply_text("Premium added.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        context.user_data['awaiting_premium_add'] = False
        return

    # awaiting_premium_remove
    if context.user_data.get('awaiting_premium_remove') and text:
        try:
            uid_to = int(text.strip())
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('UPDATE users SET is_premium=0 WHERE user_id=?', (uid_to,))
            conn.commit()
            conn.close()
            await update.message.reply_text("Premium removed.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        context.user_data['awaiting_premium_remove'] = False
        return

    # awaiting_admin_add
    if context.user_data.get('awaiting_admin_add') and text:
        try:
            uid_to = int(text.strip())
            add_admin(uid_to)
            await update.message.reply_text("Admin added.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        context.user_data['awaiting_admin_add'] = False
        return

    # awaiting_admin_remove
    if context.user_data.get('awaiting_admin_remove') and text:
        try:
            uid_to = int(text.strip())
            remove_admin(uid_to)
            await update.message.reply_text("Admin removed.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        context.user_data['awaiting_admin_remove'] = False
        return

    # awaiting_ban
    if context.user_data.get('awaiting_ban') and text:
        try:
            uid_to = int(text.strip())
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('UPDATE users SET banned=1 WHERE user_id=?', (uid_to,))
            conn.commit()
            conn.close()
            banned_users.add(uid_to)
            await update.message.reply_text("User banned.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        context.user_data['awaiting_ban'] = False
        return

    # awaiting_unban
    if context.user_data.get('awaiting_unban') and text:
        try:
            uid_to = int(text.strip())
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('UPDATE users SET banned=0 WHERE user_id=?', (uid_to,))
            conn.commit()
            conn.close()
            banned_users.discard(uid_to)
            await update.message.reply_text("User unbanned.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        context.user_data['awaiting_unban'] = False
        return

    # awaiting_broadcast
    if context.user_data.get('awaiting_broadcast') and text:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT user_id FROM users WHERE banned=0')
            users = [r[0] for r in c.fetchall()]
            conn.close()
            sent = 0
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u, text=text)
                    sent += 1
                except Exception:
                    pass
            await update.message.reply_text(f"Broadcast sent to {sent} users.")
        except Exception as e:
            await update.message.reply_text(f"Broadcast error: {e}")
        context.user_data['awaiting_broadcast'] = False
        return

    # awaiting_name -> expecting project name
    if context.user_data.get('awaiting_name') and text:
        project_name = text.strip()
        context.user_data['project_name'] = project_name
        context.user_data['awaiting_name'] = False
        await update.message.reply_text("Send files (single files or ZIP) for the project now.")
        context.user_data['awaiting_files'] = True
        return

    # awaiting_files -> handle documents
    if context.user_data.get('awaiting_files'):
        # if message contains document(s)
        if update.message.document:
            files = [update.message.document]
        else:
            files = []
            if update.message and hasattr(update.message, 'document') and update.message.document:
                files.append(update.message.document)
        if not files:
            await update.message.reply_text("No documents found in message. Please send files or ZIP.")
            return
        proj_name = context.user_data.get('project_name', f'project_{int(time.time())}')
        user_dir = os.path.join(PROJECTS_DIR, str(uid))
        proj_dir = os.path.join(user_dir, proj_name)
        os.makedirs(proj_dir, exist_ok=True)
        saved_files = []
        for f in files:
            fname = f.file_name
            path = os.path.join(proj_dir, fname)
            try:
                await f.download_to_drive(path)
                saved_files.append(path)
                # unzip if zip
                if fname.lower().endswith('.zip'):
                    try:
                        with zipfile.ZipFile(path, 'r') as z:
                            z.extractall(proj_dir)
                        os.remove(path)
                    except Exception as e:
                        print("Unzip error:", e)
            except Exception as e:
                print("Download file error:", e)
        # register project in DB with path but no pid yet
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO projects (user_id, name, path, start_time, status) VALUES (?,?,?,?,?)',
                  (uid, proj_name, proj_dir, now_iso(), 'stopped'))
        conn.commit()
        conn.close()
        await update.message.reply_text("Files uploaded and project created. Use Manage -> Deployment to run.")
        context.user_data['awaiting_files'] = False
        return

    # If message contains a document but not in awaiting_files — maybe user just uploaded something
    if update.message.document:
        # Save into a general folder
        user_dir = os.path.join(PROJECTS_DIR, str(uid))
        os.makedirs(user_dir, exist_ok=True)
        f = update.message.document
        try:
            path = os.path.join(user_dir, f.file_name)
            await f.download_to_drive(path)
            await update.message.reply_text("File saved to your folder.")
        except Exception as e:
            await update.message.reply_text(f"Error saving file: {e}")
        return

    # Generic text responses or commands not using callback buttons
    if text:
        if text.lower().strip() == 'help':
            await update.message.reply_text("Available commands:\n/start\n/admin\nUse buttons to interact.")
            return
        # allow quick start via text: "start project <name>"
        if text.lower().startswith('start project '):
            pname = text[14:].strip()
            user_dir = os.path.join(PROJECTS_DIR, str(uid))
            proj_dir = os.path.join(user_dir, pname)
            if os.path.exists(proj_dir):
                ok = start_project(uid, proj_dir, pname)
                if ok:
                    await update.message.reply_text("Project started.")
                else:
                    await update.message.reply_text("Failed to start project.")
            else:
                await update.message.reply_text("Project folder not found.")
            return

    # fallback
    await update.message.reply_text("Command not recognized. Use /start or /admin.")

# ===== FLASK ROUTES (FILEMANAGER + ADMIN DASHBOARD) =====
@app.route('/filemanager/<int:user_id>', methods=['GET', 'POST'])
def filemanager(user_id):
    if request.method == 'POST':
        fm_id = request.form.get('fm_id')
        fm_password = request.form.get('fm_password')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT fm_id, fm_password FROM users WHERE user_id=?', (user_id,))
        row = c.fetchone()
        conn.close()
        if row and row[0] == fm_id and row[1] == fm_password:
            session['fm_logged_in'] = user_id
            return redirect(url_for('fm_dashboard', user_id=user_id))
        flash('Invalid credentials')
    return render_template('fm_login.html')

@app.route('/fm_dashboard/<int:user_id>')
def fm_dashboard(user_id):
    if 'fm_logged_in' not in session or session['fm_logged_in'] != user_id:
        return redirect(url_for('filemanager', user_id=user_id))
    user_dir = os.path.join(PROJECTS_DIR, str(user_id))
    files = []
    if os.path.exists(user_dir):
        for root, dirs, fs in os.walk(user_dir):
            for f in fs:
                rel = os.path.relpath(os.path.join(root, f), user_dir)
                files.append(rel)
    return render_template('fm_dashboard.html', files=files, user_id=user_id)

@app.route('/download/<int:user_id>/<path:filename>')
def download_file(user_id, filename):
    if 'fm_logged_in' not in session or session['fm_logged_in'] != user_id:
        return redirect(url_for('filemanager', user_id=user_id))
    user_dir = os.path.join(PROJECTS_DIR, str(user_id))
    safe_path = os.path.normpath(os.path.join(user_dir, filename))
    if not safe_path.startswith(os.path.abspath(user_dir)):
        return "Invalid file path", 400
    if not os.path.exists(safe_path):
        return "File not found", 404
    return send_from_directory(user_dir, filename, as_attachment=True)

@app.route('/logout')
def logout():
    session.pop('fm_logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def login():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def do_login():
    pw = request.form.get('password')
    if pw == WEB_PASSWORD:
        session['logged_in'] = True
        return redirect(url_for('dashboard'))
    flash('Invalid password')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    sys = get_system_info()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM projects WHERE status="running"')
    running = c.fetchone()[0]
    conn.close()
    return render_template('dashboard.html',
                           cpu=sys.get('cpu_percent', 0),
                           ram=sys.get('ram_percent', 0),
                           storage=sys.get('disk_used_percent', 0),
                           uptime=sys.get('uptime_seconds', 0),
                           users=users, projects=running)

# Additional admin routes that mimic Telegram admin features (optional)
@app.route('/create_backup')
def web_create_backup():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    path = create_backup()
    if path:
        return f"Backup created: {path}"
    return "Backup failed", 500

@app.route('/clean_files')
def web_clean_files():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    removed = clean_old_files(days=30)
    return f"Removed {removed} old files."

# ===== BOT & FLASK STARTUP =====
# Build application (telegram)
application = Application.builder().token(BOT_TOKEN).build()

# add handlers (many duplicates to reflect original long script)
application.add_handler(CommandHandler("start", start_handler))
application.add_handler(CommandHandler("admin", admin_panel))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(MessageHandler(filters.Document.ALL, message_handler))

def run_bot():
    application.run_polling()

if __name__ == '__main__':
    # start bot in background thread and run flask
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
