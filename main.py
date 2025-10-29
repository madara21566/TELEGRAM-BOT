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

# Config
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
WEB_PASSWORD = os.getenv('WEB_PASSWORD', 'admin123')
DB_PATH = 'bot.db'
BACKUP_DIR = 'backups'
PROJECTS_DIR = 'user_projects'
os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Global vars
bot_locked = False
banned_users = set()

# Flask App
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecret')

# SQLite DB Setup
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

# Helper: Backup
def create_backup():
    backup_path = os.path.join(BACKUP_DIR, f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')
    with zipfile.ZipFile(backup_path, 'w') as zipf:
        zipf.write(DB_PATH)
        for root, dirs, files in os.walk(PROJECTS_DIR):
            for file in files:
                zipf.write(os.path.join(root, file))
    return backup_path

# Auto backup every hour
def auto_backup():
    while True:
        time.sleep(3600)
        create_backup()

threading.Thread(target=auto_backup, daemon=True).start()

# Helper: Check admin
def is_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id FROM admins WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

# Helper: Start project
def start_project(user_id, project_path, project_name, run_command='python main.py'):
    if bot_locked or user_id in banned_users:
        return False
    try:
        process = subprocess.Popen(run_command.split(), cwd=project_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        start_time = datetime.now().isoformat()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO projects (user_id, name, path, pid, start_time, status, run_command) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (user_id, project_name, project_path, process.pid, start_time, 'running', run_command))
        conn.commit()
        conn.close()
        threading.Thread(target=monitor_project, args=(user_id, process.pid, project_name)).start()
        return True
    except Exception as e:
        return False

# Helper: Monitor project
def monitor_project(user_id, pid, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT is_premium FROM users WHERE user_id = ?', (user_id,))
    is_premium = c.fetchone()[0]
    conn.close()
    if not is_premium:
        time.sleep(12 * 3600)
        stop_project(pid)
        application.bot.send_message(chat_id=user_id, text=f"Your project '{name}' has stopped (free tier limit). Upgrade to premium for 24/7.")

# Helper: Stop project
def stop_project(pid):
    try:
        os.kill(pid, 9)
    except:
        pass
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE projects SET status = ? WHERE pid = ?', ('stopped', pid))
    conn.commit()
    conn.close()

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users or bot_locked:
        await update.message.reply_text("Bot is locked or you are banned.")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)',
              (user_id, update.effective_user.username, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    keyboard = [
        [InlineKeyboardButton("My Projects", callback_data='my_projects')],
        [InlineKeyboardButton("Premium Buy", callback_data='premium_buy')]
    ]
    await update.message.reply_text("Choose an action:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    keyboard = [
        [InlineKeyboardButton("User Stats", callback_data='user_stats')],
        [InlineKeyboardButton("File Stats", callback_data='file_stats')],
        [InlineKeyboardButton("Running Statuses", callback_data='running_statuses')],
        [InlineKeyboardButton("Add Premium User", callback_data='add_premium')],
        [InlineKeyboardButton("Remove Premium User", callback_data='remove_premium')],
        [InlineKeyboardButton("Add Admin", callback_data='add_admin')],
        [InlineKeyboardButton("Remove Admin", callback_data='remove_admin')],
        [InlineKeyboardButton("Ban User", callback_data='ban_user')],
        [InlineKeyboardButton("Unban User", callback_data='unban_user')],
        [InlineKeyboardButton("Bot Analysis", callback_data='bot_analysis')],
        [InlineKeyboardButton("System Info", callback_data='system_info')],
        [InlineKeyboardButton("Lock Bot", callback_data='lock_bot')],
        [InlineKeyboardButton("Unlock Bot", callback_data='unlock_bot')],
        [InlineKeyboardButton("Broadcast", callback_data='broadcast')],
        [InlineKeyboardButton("Clean Old Files", callback_data='clean_files')],
        [InlineKeyboardButton("Backup", callback_data='backup')],
        [InlineKeyboardButton("View DP", callback_data='view_dp')],
        [InlineKeyboardButton("View Logs", callback_data='view_logs')],
        [InlineKeyboardButton("Restart Bot", callback_data='restart_bot')]
    ]
    await update.message.reply_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id) and query.data in ['user_stats', 'file_stats', 'running_statuses', 'add_premium', 'remove_premium', 'add_admin', 'remove_admin', 'ban_user', 'unban_user', 'bot_analysis', 'system_info', 'lock_bot', 'unlock_bot', 'broadcast', 'clean_files', 'backup', 'view_dp', 'view_logs', 'restart_bot']:
        await query.edit_message_text("Access denied.")
        return
    data = query.data

    if data == 'my_projects':
        keyboard = [
            [InlineKeyboardButton("New Project", callback_data='new_project')],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text("My Projects:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == 'premium_buy':
        await query.edit_message_text(f"Contact owner for premium: @{ADMIN_ID}")
    elif data == 'new_project':
        await query.edit_message_text("Enter project name:")
        context.user_data['awaiting_name'] = True
    elif data == 'back':
        await start(update, context)
    elif data.startswith('manage_'):
        project_id = int(data.split('_')[1])
        keyboard = [
            [InlineKeyboardButton("Launch File Manager", callback_data=f'fm_{project_id}')],
            [InlineKeyboardButton("Deployment", callback_data=f'deploy_{project_id}')],
            [InlineKeyboardButton("Delete Project", callback_data=f'delete_{project_id}')],
            [InlineKeyboardButton("Back", callback_data='my_projects')]
        ]
        await query.edit_message_text("Manage project:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith('fm_'):
        project_id = int(data.split('_')[1])
        fm_id, fm_password = generate_fm_credentials(user_id)
        link = f"https://your-render-app.onrender.com/filemanager/{user_id}"
        await query.edit_message_text(f"File Manager Link: {link}\nID: {fm_id}\nPassword: {fm_password}")
    elif data.startswith('deploy_'):
        project_id = int(data.split('_')[1])
        keyboard = [
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
        await query.edit_message_text("Deployment Options:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith('start_'):
        project_id = int(data.split('_')[1])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT path, name, run_command FROM projects WHERE id = ?', (project_id,))
        path, name, cmd = c.fetchone()
        conn.close()
        if start_project(user_id, path, name, cmd):
            await query.edit_message_text("Project started!")
        else:
            await query.edit_message_text("Failed to start.")
    elif data.startswith('stop_'):
        project_id = int(data.split('_')[1])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT pid FROM projects WHERE id = ?', (project_id,))
        pid = c.fetchone()[0]
        stop_project(pid)
        conn.close()
        await query.edit_message_text("Project stopped.")
    elif data.startswith('logs_'):
        project_id = int(data.split('_')[1])
        await query.edit_message_text("Logs: [stdout/stderr here]")
    elif data.startswith('status_'):
        project_id = int(data.split('_')[1])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT status FROM projects WHERE id = ?', (project_id,))
        status = c.fetchone()[0]
        conn.close()
        await query.edit_message_text(f"Status: {status}")
    elif data.startswith('usages_'):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        await query.edit_message_text(f"CPU: {cpu}%, RAM: {ram}%")
    elif data.startswith('install_req_'):
        project_id = int(data.split('_')[1])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT path FROM projects WHERE id = ?', (project_id,))
        path = c.fetchone()[0]
        conn.close()
        req_path = os.path.join(path, 'requirements.txt')
        if os.path.exists(req_path):
            subprocess.run(['pip', 'install', '-r', req_path])
            await query.edit_message_text("Requirements installed!")
        else:
            await query.edit_message_text("No requirements.txt found.")
    elif data.startswith('edit_cmd_'):
        project_id = int(data.split('_')[1])
        await query.edit_message_text("Enter new run command (e.g., python app.py):")
        context.user_data['editing_cmd'] = project_id
    elif data == 'user_stats':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*), SUM(is_premium), SUM(banned) FROM users')
        total, premium, banned = c.fetchone()
        conn.close()
        await query.edit_message_text(f"Total Users: {total}\nPremium: {premium}\nBanned: {banned}")
    elif data == 'file_stats':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM projects')
        projects = c.fetchone()[0]
        conn.close()
        await query.edit_message_text(f"Total Projects: {projects}")
    elif data == 'running_statuses':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT name, status, pid FROM projects WHERE status = "running"')
        running = c.fetchall()
        conn.close()
        text = "\n".join([f"{name}: {status} (PID: {pid})" for name, status, pid in running])
        await query.edit_message_text(f"Running Projects:\n{text}")
    elif data == 'add_premium':
        await query.edit_message_text("Enter user ID to add premium:")
        context.user_data['awaiting_premium_add'] = True
    elif data == 'remove_premium':
        await query.edit_message_text("Enter user ID to remove premium:")
        context.user_data['awaiting_premium_remove'] = True
    elif data == 'add_admin':
        await query.edit_message_text("Enter user ID to add admin:")
        context.user_data['awaiting_admin_add'] = True
    elif data == 'remove_admin':
        await query.edit_message_text("Enter user ID to remove admin:")
        context.user_data['awaiting_admin_remove'] = True
    elif data == 'ban_user':
        await query.edit_message_text("Enter user ID to ban:")
        context.user_data['awaiting_ban'] = True
    elif data == 'unban_user':
        await query.edit_message_text("Enter user ID to unban:")
        context.user_data['awaiting_unban'] = True
    elif data == 'bot_analysis':
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        await query.edit_message_text(f"CPU: {cpu}%\nRAM: {ram}%")
    elif data == 'system_info':
        info = f"OS: {os.name}\nCPU Cores: {psutil.cpu_count()}\nDisk: {psutil.disk_usage('/').total / 1e9:.2f} GB"
        await query.edit_message_text(info)
    elif data == 'lock_bot':
        global bot_locked
        bot_locked = True
        await query.edit_message_text("Bot locked.")
    elif data == 'unlock_bot':
        bot_locked = False
        await query.edit_message_text("Bot unlocked.")
    elif data == 'broadcast':
        await query.edit_message_text("Enter message to broadcast:")
        context.user_data['awaiting_broadcast'] = True
    elif data == 'clean_files':
        cutoff = datetime.now() - timedelta(days=30)
        for root, dirs, files in os.walk(PROJECTS_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                if datetime.fromtimestamp(os.path.getmtime(file_path)) < cutoff:
                    os.remove(file_path)
        await query.edit_message_text("Old files cleaned.")
    elif data == 'backup':
        backup_path = create_backup()
        await query.edit_message_text(f"Backup created: {backup_path}")
    elif data == 'view_dp':
        await query.edit_message_text("Enter user ID to view DP:")
        context.user_data['awaiting_dp'] = True
    elif data == 'view_logs':
        await query.edit_message_text("Logs: [Error logs here]")
    elif data == 'restart_bot':
        create_backup()
        await query.edit_message_text("Restart
