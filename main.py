"""
⚡ GOD MADARA HOSTING BOT ⚡
FINAL PUBLIC VERSION (Light Theme + Mobile Login)
Environment Variables Required:
BOT_TOKEN, CHANNEL_A, CHANNEL_B, RENDER_EXTERNAL_HOSTNAME, WEB_SECRET_KEY
"""

import os, time, zipfile, pathlib, subprocess, threading, shutil, logging, json, random, string, sys
from datetime import datetime
from functools import wraps
from flask import Flask, request, session, redirect, render_template, jsonify, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

# --- CONFIG ---
BOT_TOKEN = os.environ.get('BOT_TOKEN','YOUR_BOT_TOKEN_HERE')
BASE_DIR = pathlib.Path.cwd() / 'projects'
BACKUP_DIR = pathlib.Path.cwd() / 'backups'
META_FILE = pathlib.Path.cwd() / 'users.json'
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME','your-render-app.onrender.com')
REQUIRED_CHANNELS = [os.environ.get('CHANNEL_A','@channela'), os.environ.get('CHANNEL_B','@channelb')]
BACKUPS_KEEP = 10

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('madara_final')

BASE_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

if META_FILE.exists():
    with open(META_FILE,'r') as f:
        users = json.load(f)
else:
    users = {}

process_table = {}

def save_meta():
    with open(META_FILE,'w') as f:
        json.dump(users, f, indent=2)

def randpass(n=10):
    return ''.join(random.choice(string.ascii_letters+string.digits) for _ in range(n))

def user_dir(uid):
    p = BASE_DIR / str(uid)
    p.mkdir(parents=True, exist_ok=True)
    return p

def project_dir(uid, proj):
    p = user_dir(uid) / proj
    p.mkdir(parents=True, exist_ok=True)
    return p

def detect_main_file(udir):
    for name in ('main.py','app.py'):
        if (udir/name).exists():
            return name
    for p in udir.glob('*.py'):
        return p.name
    return None

# --- FLASK APP (Web Editor) ---
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('WEB_SECRET_KEY','change_me')

def login_required(f):
    @wraps(f)
    def inner(uid, *args, **kwargs):
        if 'uid' not in session: return redirect('/login')
        if str(session.get('uid')) != str(uid): return "Not allowed", 403
        return f(uid, *args, **kwargs)
    return inner

@app.route('/login', methods=['GET','POST'])
def login_page():
    error=None
    if request.method=='POST':
        uid = request.form.get('uid'); pwd = request.form.get('pwd')
        if uid in users:
            for p,meta in users[uid].get('projects',{}).items():
                if meta.get('web_password')==pwd:
                    session['uid']=uid; return redirect(url_for('editor_list', uid=uid))
        error='Invalid credentials'
    return render_template('login_mobile.html', error=error, header="⚡ GOD MADARA HOSTING BOT ⚡")

@app.route('/editor/<uid>')
@login_required
def editor_list(uid):
    projs = users.get(str(uid), {}).get('projects', {})
    return render_template('editor_list.html', uid=uid, projs=projs, host=RENDER_HOST, header="⚡ GOD MADARA HOSTING BOT ⚡")

@app.route('/editor/<uid>/project/<proj>')
@login_required
def editor(uid, proj):
    uproj = project_dir(uid, proj)
    files = [str(p.relative_to(uproj)) for p in uproj.glob('**/*') if p.is_file()]
    return render_template('editor.html', uid=uid, proj=proj, files=files, host=RENDER_HOST, header="⚡ GOD MADARA HOSTING BOT ⚡")

@app.route('/editor/api/file/<uid>/<proj>', methods=['GET','POST','DELETE'])
@login_required
def api_file(uid, proj):
    uproj = project_dir(uid, proj)
    if request.method=='GET':
        path = request.args.get('path'); fp = uproj / path
        if not fp.exists(): return "Not found", 404
        return fp.read_text(errors='ignore')
    if request.method=='POST':
        data = request.get_json(); path = data.get('path'); content = data.get('content','')
        fp = uproj / path; fp.parent.mkdir(parents=True, exist_ok=True); fp.write_text(content)
        users[str(uid)]['projects'][proj]['restart_request'] = True; save_meta()
        return jsonify({'status':'ok'})
    if request.method=='DELETE':
        data = request.get_json(); path = data.get('path'); fp = uproj / path
        if fp.exists(): fp.unlink()
        return jsonify({'status':'ok'})

# --- TELEGRAM HANDLERS ---
NEW_NAME = range(1)

async def require_channels(app_obj, user_id):
    ok=True
    for ch in REQUIRED_CHANNELS:
        try:
            mem = await app_obj.bot.get_chat_member(chat_id=ch, user_id=int(user_id))
            if mem.status in ('left','kicked'):
                ok=False
        except Exception:
            ok=False
    return ok

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    ok = await require_channels(context.application, uid)
    if not ok:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton('Join Channel A', url=f'https://t.me/{REQUIRED_CHANNELS[0].lstrip("@")}')],
            [InlineKeyboardButton('Join Channel B', url=f'https://t.me/{REQUIRED_CHANNELS[1].lstrip("@")}')],
            [InlineKeyboardButton('✅ I Joined', callback_data='joined')]
        ])
        await update.message.reply_text('Please join required channels to use the bot.', reply_markup=kb); return
    users.setdefault(uid, {}); users[uid].setdefault('projects', {})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('🆕 New Project', callback_data='newproject')],
        [InlineKeyboardButton('📂 My Projects', callback_data='myprojects')],
        [InlineKeyboardButton('⚙️ Manage Files', callback_data='managefiles')],
        [InlineKeyboardButton('🚀 Deployment', callback_data='deployment')]
    ])
    await update.message.reply_text('✅ Access Granted! Welcome to ⚡ GOD MADARA HOSTING BOT ⚡\nChoose an option below 👇', reply_markup=kb)

# “I Joined” button fix
async def joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = str(q.from_user.id)
    ok = await require_channels(context.application, uid)
    if not ok:
        await q.edit_message_text("❗ Still not joined both channels. Join both and click 'I Joined' again.",
                                  reply_markup=InlineKeyboardMarkup([
                                      [InlineKeyboardButton('Join Channel A', url=f'https://t.me/{REQUIRED_CHANNELS[0].lstrip("@")}')],
                                      [InlineKeyboardButton('Join Channel B', url=f'https://t.me/{REQUIRED_CHANNELS[1].lstrip("@")}')],
                                      [InlineKeyboardButton('✅ I Joined', callback_data='joined')]
                                  ])); return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('🆕 New Project', callback_data='newproject')],
        [InlineKeyboardButton('📂 My Projects', callback_data='myprojects')],
        [InlineKeyboardButton('⚙️ Manage Files', callback_data='managefiles')],
        [InlineKeyboardButton('🚀 Deployment', callback_data='deployment')]
    ])
    await q.edit_message_text('✅ Access Granted! Welcome to ⚡ GOD MADARA HOSTING BOT ⚡', reply_markup=kb)

# --- PROJECT CREATION ---
async def newproject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Enter a name for your new project:")
    return NEW_NAME

async def receive_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip(); uid = str(update.effective_user.id)
    users.setdefault(uid, {}).setdefault('projects', {})
    users[uid]['projects'][name] = {'created_at': time.time(), 'running': False, 'web_password': randpass(10)}
    users[uid]['creating'] = name; save_meta()
    await update.message.reply_text(f'Project {name} created. Now send your .py or .zip file.')
    return ConversationHandler.END

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc: Document = update.message.document; uid = str(update.effective_user.id)
    proj = users.get(uid, {}).get('creating')
    if not proj: return await update.message.reply_text('Use /newproject first.')
    uproj = project_dir(uid, proj); dest = uproj / doc.file_name
    msg = await update.message.reply_text("📥 Uploading...")
    await doc.get_file().download_to_drive(str(dest))
    if dest.suffix == '.zip':
        with zipfile.ZipFile(dest,'r') as zf: zf.extractall(uproj); dest.unlink()
    users[uid].pop('creating', None); save_meta()
    url = f'https://{RENDER_HOST}/editor/{uid}/project/{proj}'
    pwd = users[uid]['projects'][proj]['web_password']
    await msg.edit_text(f"✅ Uploaded!\nWeb Editor: {url}\nUID: {uid}\nPassword: {pwd}")

# --- BACKUP LOOP ---
def backup_loop():
    while True:
        for uid, meta in list(users.items()):
            for proj in meta.get('projects',{}):
                backup_project(uid, proj)
        time.sleep(3600)

def backup_project(uid, proj):
    uproj = project_dir(uid, proj)
    if not uproj.exists(): return
    outdir = BACKUP_DIR / str(uid); outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    z = outdir / f'{proj}_{ts}.zip'
    with zipfile.ZipFile(z,'w') as zf:
        for root,_,files in os.walk(uproj):
            for f in files: fp = pathlib.Path(root)/f; zf.write(fp, arcname=str(fp.relative_to(uproj)))
    files = sorted(outdir.glob(f'{proj}_*.zip'))
    if len(files)>BACKUPS_KEEP:
        for old in files[:-BACKUPS_KEEP]: old.unlink()

# --- MAIN ---
def main():
    threading.Thread(target=backup_loop, daemon=True).start()
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    conv = ConversationHandler(entry_points=[CallbackQueryHandler(newproject_start, pattern='^newproject$')],
                               states={NEW_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_project_name)]},
                               fallbacks=[])
    app_bot.add_handler(CommandHandler('start', start_cmd))
    app_bot.add_handler(CallbackQueryHandler(joined_callback, pattern='^joined$'))
    app_bot.add_handler(conv)
    app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000))), daemon=True).start()
    import asyncio; asyncio.run(app_bot.run_polling())

if __name__ == '__main__':
    main()
