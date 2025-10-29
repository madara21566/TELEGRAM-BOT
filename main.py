"""
⚡ GOD MADARA HOSTING BOT ⚡ - FINAL READY
Inline Telegram hosting bot + Flask web editor.
Set env vars on Render: BOT_TOKEN, CHANNEL_A, CHANNEL_B, RENDER_EXTERNAL_HOSTNAME, WEB_SECRET_KEY
"""

import os, time, zipfile, pathlib, subprocess, threading, shutil, logging, json, random, string
from datetime import datetime
from functools import wraps
from flask import Flask, request, session, redirect, render_template, jsonify, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

BOT_TOKEN = os.environ.get('BOT_TOKEN','YOUR_BOT_TOKEN_HERE')
BASE_DIR = pathlib.Path.cwd() / 'projects'
BACKUP_DIR = pathlib.Path.cwd() / 'backups'
META_FILE = pathlib.Path.cwd() / 'users.json'
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME','your-render-app.onrender.com')
REQUIRED_CHANNELS = [os.environ.get('CHANNEL_A','@channela'), os.environ.get('CHANNEL_B','@channelb')]
BACKUPS_KEEP = 10

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('god_madara_final_ready')

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

def randpass(n=12):
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

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('WEB_SECRET_KEY','change_me')

def login_required(f):
    @wraps(f)
    def inner(uid, *args, **kwargs):
        if 'uid' not in session:
            return redirect('/login')
        if str(session.get('uid')) != str(uid):
            return "Not allowed", 403
        return f(uid, *args, **kwargs)
    inner.__name__ = f.__name__
    return inner

@app.route('/login', methods=['GET','POST'])
def login_page():
    error = None
    if request.method == 'POST':
        uid = request.form.get('uid')
        pwd = request.form.get('pwd')
        if uid in users:
            projs = users[uid].get('projects',{})
            for p,meta in projs.items():
                if meta.get('web_password') == pwd:
                    session['uid'] = uid
                    return redirect(url_for('editor_list', uid=uid))
        error = "Invalid credentials"
    return render_template('login.html', error=error, header="⚡ GOD MADARA HOSTING BOT ⚡")

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

@app.route('/editor/api/files/<uid>/<proj>')
@login_required
def api_files(uid, proj):
    uproj = project_dir(uid, proj)
    files = [str(p.relative_to(uproj)) for p in uproj.glob('**/*') if p.is_file()]
    return jsonify({'files': files})

@app.route('/editor/api/file/<uid>/<proj>', methods=['GET','POST','DELETE'])
@login_required
def api_file(uid, proj):
    uproj = project_dir(uid, proj)
    if request.method == 'GET':
        path = request.args.get('path')
        fp = uproj / path
        if not fp.exists(): return "Not found", 404
        return fp.read_text(errors='ignore')
    if request.method == 'POST':
        data = request.get_json()
        path = data.get('path')
        content = data.get('content','')
        fp = uproj / path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        users.setdefault(str(uid), {}).setdefault('projects', {}).setdefault(proj, {})['restart_request'] = True
        save_meta()
        return jsonify({'status':'ok'})
    if request.method == 'DELETE':
        data = request.get_json()
        path = data.get('path')
        fp = uproj / path
        if fp.exists(): fp.unlink()
        return jsonify({'status':'ok'})

NEW_NAME = range(1)

async def require_channels(app_obj, user_id):
    ok = True
    for ch in REQUIRED_CHANNELS:
        try:
            mem = await app_obj.bot.get_chat_member(chat_id=ch, user_id=int(user_id))
            if mem.status in ('left','kicked'):
                ok = False
        except Exception:
            ok = False
    return ok

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    ok = await require_channels(context.application, uid)
    if not ok:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton('Join Channel A', url=f'https://t.me/{REQUIRED_CHANNELS[0].lstrip("@")}')],[InlineKeyboardButton('Join Channel B', url=f'https://t.me/{REQUIRED_CHANNELS[1].lstrip("@")}')],[InlineKeyboardButton('✅ I Joined', callback_data='joined')]])
        await update.message.reply_text('Please join required channels to use the bot.', reply_markup=kb)
        return
    users.setdefault(uid, {})
    users[uid].setdefault('projects', {})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('🆕 New Project', callback_data='newproject')],
        [InlineKeyboardButton('📂 My Projects', callback_data='myprojects')],
        [InlineKeyboardButton('⚙️ Manage Files', callback_data='managefiles')],
        [InlineKeyboardButton('🚀 Deployment', callback_data='deployment')]
    ])
    await update.message.reply_text('✅ Access Granted! Welcome to ⚡ GOD MADARA HOSTING BOT ⚡\nChoose an option below 👇', reply_markup=kb)

async def newproject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text('Please enter a name for your new project (e.g., my-bot). Send /cancel to abort.')
    else:
        await update.message.reply_text('Please enter a name for your new project (e.g., my-bot). Send /cancel to abort.')
    return NEW_NAME

async def receive_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    uid = str(update.effective_user.id)
    if not name:
        await update.message.reply_text('Invalid name.')
        return ConversationHandler.END
    users.setdefault(uid, {}).setdefault('projects', {})
    if name in users[uid]['projects']:
        await update.message.reply_text('Project exists. Choose another name.')
        return ConversationHandler.END
    users[uid]['projects'][name] = {'name':name, 'created_at': time.time(), 'running': False, 'web_password': randpass(12)}
    users[uid]['creating'] = name
    save_meta()
    await update.message.reply_text(f'Project {name} created. Now send your .py/.js/.zip file as a Document (max 50MB).')
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    users.get(uid, {}).pop('creating', None)
    save_meta()
    await update.message.reply_text('Cancelled.')
    return ConversationHandler.END

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc: Document = update.message.document
    uid = str(update.effective_user.id)
    if not doc:
        await update.message.reply_text('Send a document (.py/.zip/.js).')
        return
    proj = users.get(uid, {}).get('creating')
    if not proj:
        await update.message.reply_text('No project in creation. Use /newproject first.')
        return
    uproj = project_dir(uid, proj)
    dest = uproj / (doc.file_name or 'uploaded')
    status = await update.message.reply_text(f"📤 Preparing upload: {doc.file_name}\n\n▒░░░░░░░░ 0%")
    try:
        await status.edit_text(f"📥 Downloading...\n\n▓▓░░░░░░░ 30%")
        await doc.get_file().download_to_drive(str(dest))
        await status.edit_text(f"💾 Saving...\n\n▓▓▓▓▓░░░░ 60%")
        time.sleep(0.5)
        if str(dest).lower().endswith('.zip'):
            await status.edit_text(f"📦 Extracting ZIP...\n\n▓▓▓▓▓▓▓░ 85%")
            with zipfile.ZipFile(str(dest),'r') as zf:
                zf.extractall(path=str(uproj))
            dest.unlink()
        await status.edit_text(f"✅ Finalizing...\n\n▓▓▓▓▓▓▓▓▓ 100%")
        users[uid].setdefault('projects', {})[proj]['running'] = False
        users[uid].pop('creating', None)
        save_meta()
        await send_manage_menu(update, context, uid, proj)
    except Exception as e:
        await status.edit_text(f"❌ Upload failed: {e}")
        return

def make_manage_keyboard(uid, proj):
    kb = [
        [InlineKeyboardButton('🌐 Manage Files', callback_data=f'manage|{proj}|{uid}'), InlineKeyboardButton('⚙️ Deployment', callback_data=f'deploy|{proj}|{uid}')],
        [InlineKeyboardButton('📨 Install Requirements', callback_data=f'install|{proj}|{uid}'), InlineKeyboardButton('🗑 Delete Project', callback_data=f'delete|{proj}|{uid}')],
        [InlineKeyboardButton('🔙 Back', callback_data='back_main')]
    ]
    return InlineKeyboardMarkup(kb)

def send_manage_menu_sync_text(uid, proj):
    web_pass = users.get(uid, {}).get('projects', {}).get(proj, {}).get('web_password') or randpass(12)
    users.setdefault(uid, {}).setdefault('projects', {}).setdefault(proj, {})['web_password'] = web_pass
    save_meta()
    url = f'https://{RENDER_HOST}/editor/{uid}/project/{proj}'
    return f'✅ Project {proj} setup complete!\nWeb Editor: {url}\nUsername: {uid}\nPassword: {web_pass}\nManage your project below.'

async def send_manage_menu(update_or_query, context, uid, proj):
    text = send_manage_menu_sync_text(uid, proj)
    if hasattr(update_or_query, 'callback_query') and update_or_query.callback_query:
        await update_or_query.callback_query.edit_message_text(text, reply_markup=make_manage_keyboard(uid, proj))
    else:
        await update_or_query.message.reply_text(text, reply_markup=make_manage_keyboard(uid, proj))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data == 'newproject':
        return await newproject_start(update, context)
    if data == 'back_main':
        await q.edit_message_text('Back to main. Use /newproject to create more.')
        return
    parts = data.split('|')
    action = parts[0]
    if action in ('manage','deploy','delete','install','start','stop','restart','logs'):
        proj = parts[1]; uid = parts[2]
        uproj = project_dir(uid, proj)
        if action == 'manage':
            files = '\n'.join([str(p.relative_to(uproj)) for p in uproj.glob('**/*') if p.is_file()]) or 'No files'
            text = f'Files for {proj}:\n{files}\nOpen web editor with the credentials provided earlier to edit/upload/delete files.'
            kb = InlineKeyboardMarkup([[InlineKeyboardButton('🖥️ Open Web Editor', url=f'https://{RENDER_HOST}/editor/{uid}/project/{proj}')],[InlineKeyboardButton('🔙 Back', callback_data=f'back_manage|{proj}|{uid}')]])
            await q.edit_message_text(text, reply_markup=kb)
            return
        if action == 'deploy':
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton('📦 Install Dependencies', callback_data=f'install|{proj}|{uid}'), InlineKeyboardButton('▶️ Start', callback_data=f'start|{proj}|{uid}')],
                [InlineKeyboardButton('⏹ Stop', callback_data=f'stop|{proj}|{uid}'), InlineKeyboardButton('🔁 Restart', callback_data=f'restart|{proj}|{uid}')],
                [InlineKeyboardButton('📜 Logs', callback_data=f'logs|{proj}|{uid}'), InlineKeyboardButton('🔙 Back', callback_data=f'back_manage|{proj}|{uid}')]
            ])
            await q.edit_message_text(f'Deployment menu for {proj}:', reply_markup=kb)
            return
        if action == 'delete':
            try:
                shutil.rmtree(uproj)
            except Exception:
                pass
            users.get(uid, {}).get('projects', {}).pop(proj, None)
            save_meta()
            await q.edit_message_text(f'Project {proj} deleted.')
            return
        if action == 'install':
            req = uproj / 'requirements.txt'
            if not req.exists():
                await q.edit_message_text('No requirements.txt found in project folder.', reply_markup=make_manage_keyboard(uid, proj))
                return
            await q.edit_message_text('Installing dependencies... I will notify you when complete.', reply_markup=make_manage_keyboard(uid, proj))
            def install_thread():
                try:
                    try:
                        context.application.bot.send_message(int(uid), f"📦 Installing dependencies for {proj}...")
                    except Exception:
                        pass
                    subprocess.check_call([shutil.which('pip') or 'pip', 'install', '-r', str(req)])
                    try:
                        context.application.bot.send_message(int(uid), f"✅ Dependencies installed for {proj}. Starting now...")
                    except Exception:
                        pass
                    mainfile = detect_main_file(uproj)
                    if mainfile:
                        lf = open(str(uproj/'run.log'),'ab')
                        proc = subprocess.Popen([sys.executable, mainfile], cwd=str(uproj), stdout=lf, stderr=lf)
                        process_table[f'{uid}:{proj}'] = proc
                        users.setdefault(uid, {}).setdefault('projects', {}).setdefault(proj, {})['running'] = True
                        users[uid]['projects'][proj]['last_started'] = time.time()
                        save_meta()
                        try:
                            context.application.bot.send_message(int(uid), f"▶️ Project {proj} started (pid {proc.pid}).")
                        except Exception:
                            pass
                except Exception as e:
                    try:
                        context.application.bot.send_message(int(uid), f"❌ Failed to install dependencies for {proj}: {e}")
                    except Exception:
                        pass
            threading.Thread(target=install_thread, daemon=True).start()
            return
        if action == 'start':
            mainfile = detect_main_file(uproj)
            if not mainfile:
                await q.edit_message_text('No python file found to run.', reply_markup=make_manage_keyboard(uid, proj))
                return
            lf = open(str(uproj/'run.log'),'ab')
            proc = subprocess.Popen([sys.executable, mainfile], cwd=str(uproj), stdout=lf, stderr=lf)
            process_table[f'{uid}:{proj}'] = proc
            users.setdefault(uid, {}).setdefault('projects', {}).setdefault(proj, {})['running'] = True
            users[uid]['projects'][proj]['last_started'] = time.time()
            save_meta()
            await q.edit_message_text(f'Started {mainfile} (pid {proc.pid})', reply_markup=make_manage_keyboard(uid, proj))
            return
        if action == 'stop':
            key = f'{uid}:{proj}'
            proc = process_table.get(key)
            if not proc:
                await q.edit_message_text('Not running.', reply_markup=make_manage_keyboard(uid, proj))
                return
            try:
                proc.terminate(); proc.wait(timeout=5)
            except Exception:
                pass
            users.setdefault(uid, {}).setdefault('projects', {}).setdefault(proj, {})['running'] = False
            save_meta()
            await q.edit_message_text('Stopped.', reply_markup=make_manage_keyboard(uid, proj))
            return
        if action == 'restart':
            key = f'{uid}:{proj}'
            proc = process_table.get(key)
            try:
                if proc: proc.terminate(); proc.wait(timeout=5)
            except Exception:
                pass
            mainfile = detect_main_file(uproj)
            if not mainfile:
                await q.edit_message_text('No python file found to run.')
                return
            lf = open(str(uproj/'run.log'),'ab')
            proc = subprocess.Popen([sys.executable, mainfile], cwd=str(uproj), stdout=lf, stderr=lf)
            process_table[key] = proc
            users.setdefault(uid, {}).setdefault('projects', {}).setdefault(proj, {})['running'] = True
            users[uid]['projects'][proj]['last_started'] = time.time()
            save_meta()
            await q.edit_message_text(f'Restarted (pid {proc.pid})', reply_markup=make_manage_keyboard(uid, proj))
            return
        if action == 'logs':
            lf = uproj / 'run.log'
            if not lf.exists():
                await q.edit_message_text('No logs yet.', reply_markup=make_manage_keyboard(uid, proj))
                return
            text = lf.read_text(errors='ignore')[-4000:]
            await q.edit_message_text(f'Last logs:\n{text}', reply_markup=make_manage_keyboard(uid, proj))
            return
    if data.startswith('back_manage'):
        parts = data.split('|')
        proj = parts[1]; uid = parts[2]
        await q.edit_message_text('Back to project menu', reply_markup=make_manage_keyboard(uid, proj))
        return

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Use /newproject to create a project or press New Project button.')

def backup_loop():
    while True:
        try:
            for uid,meta in list(users.items()):
                for proj in meta.get('projects',{}).keys():
                    backup_project(uid, proj)
            time.sleep(3600)
        except Exception as e:
            logger.exception('backup loop error: %s', e); time.sleep(60)

def backup_project(uid, proj):
    uproj = project_dir(uid, proj)
    if not uproj.exists(): return None
    outdir = BACKUP_DIR / str(uid)
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    z = outdir / f'{proj}_{ts}.zip'
    with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(str(uproj)):
            for f in files:
                fp = pathlib.Path(root)/f
                rel = fp.relative_to(uproj)
                zf.write(fp, arcname=str(rel))
    files = sorted(outdir.glob(f'{proj}_*.zip'))
    if len(files) > BACKUPS_KEEP:
        for old in files[:-BACKUPS_KEEP]:
            try: old.unlink()
            except: pass
    return z

def restore_on_startup():
    pass

def main():
    t = threading.Thread(target=backup_loop, daemon=True)
    t.start()

    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler('newproject', newproject_start), CallbackQueryHandler(newproject_start, pattern='^newproject$')],
                               states={NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_project_name)]},
                               fallbacks=[CommandHandler('cancel', cancel)])
    app_bot.add_handler(CommandHandler('start', start_cmd))
    app_bot.add_handler(conv)
    app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app_bot.add_handler(CallbackQueryHandler(callback_handler))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    fthread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000))), daemon=True)
    fthread.start()

    import asyncio
    asyncio.run(app_bot.run_polling())

if __name__ == '__main__':
    main()
