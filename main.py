# Final GOD MADARA main.py (FINAL)
# NOTE: set environment variables before running: BOT_TOKEN, CHANNEL_A, CHANNEL_B, RENDER_EXTERNAL_HOSTNAME, WEB_SECRET_KEY
import os, time, zipfile, pathlib, subprocess, threading, shutil, logging, json, random, string
from datetime import datetime
from flask import Flask, request, session, redirect, render_template, jsonify, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

BOT_TOKEN = os.environ.get('BOT_TOKEN','YOUR_BOT_TOKEN_HERE')
BASE_DIR = pathlib.Path.cwd() / 'projects'
BACKUP_DIR = pathlib.Path.cwd() / 'backups'
META_FILE = pathlib.Path.cwd() / 'users.json'
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME','your-render-app.onrender.com')
REQUIRED_CHANNELS = [os.environ.get('CHANNEL_A','@channela'), os.environ.get('CHANNEL_B','@channelb')]

BASE_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
if META_FILE.exists():
    with open(META_FILE,'r') as f:
        users = json.load(f)
else:
    users = {}

def save_meta():
    with open(META_FILE,'w') as f:
        json.dump(users, f, indent=2)

def randpass(n=12):
    import random, string
    return ''.join(random.choice(string.ascii_letters+string.digits) for _ in range(n))

def user_dir(uid):
    p = BASE_DIR / str(uid); p.mkdir(parents=True, exist_ok=True); return p
def project_dir(uid, proj):
    p = user_dir(uid) / proj; p.mkdir(parents=True, exist_ok=True); return p

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('WEB_SECRET_KEY','change_me')

@app.route('/login', methods=['GET','POST'])
def login_page():
    error=None
    if request.method=='POST':
        uid = request.form.get('uid'); pwd = request.form.get('pwd')
        if uid in users:
            for p,meta in users[uid].get('projects',{}).items():
                if meta.get('web_password')==pwd:
                    session['uid']=uid; return redirect(url_for('editor_list', uid=uid))
        error='Invalid'
    return render_template('login.html', error=error)

@app.route('/editor/<uid>')
def editor_list(uid):
    if 'uid' not in session or session['uid']!=str(uid): return redirect('/login')
    projs = users.get(str(uid), {}).get('projects', {})
    return render_template('editor_list.html', uid=uid, projs=projs)

@app.route('/editor/<uid>/project/<proj>')
def editor(uid, proj):
    if 'uid' not in session or session['uid']!=str(uid): return redirect('/login')
    uproj = project_dir(uid, proj)
    files = [str(p.relative_to(uproj)) for p in uproj.glob('**/*') if p.is_file()]
    return render_template('editor.html', uid=uid, proj=proj, files=files)

@app.route('/editor/api/files/<uid>/<proj>')
def api_files(uid, proj):
    if 'uid' not in session or session['uid']!=str(uid): return redirect('/login')
    uproj = project_dir(uid, proj)
    files = [str(p.relative_to(uproj)) for p in uproj.glob('**/*') if p.is_file()]
    return jsonify({'files': files})

@app.route('/editor/api/file/<uid>/<proj>', methods=['GET','POST','DELETE'])
def api_file(uid, proj):
    if 'uid' not in session or session['uid']!=str(uid): return redirect('/login')
    uproj = project_dir(uid, proj)
    if request.method=='GET':
        path = request.args.get('path'); fp = uproj / path
        if not fp.exists(): return "Not found", 404
        return fp.read_text(errors='ignore')
    if request.method=='POST':
        data = request.get_json(); path = data.get('path'); content = data.get('content','')
        fp = uproj/path; fp.parent.mkdir(parents=True, exist_ok=True); fp.write_text(content)
        users.setdefault(str(uid), {}).setdefault('projects', {}).setdefault(proj, {})['restart_request']=True; save_meta()
        return jsonify({'status':'ok'})
    if request.method=='DELETE':
        data = request.get_json(); path = data.get('path'); fp = uproj / path
        if fp.exists(): fp.unlink(); return jsonify({'status':'ok'})
    return jsonify({'status':'ok'})

NEW_NAME = range(1)
async def require_channels(app_obj, user_id):
    ok=True
    for ch in REQUIRED_CHANNELS:
        try:
            mem = await app_obj.bot.get_chat_member(chat_id=ch, user_id=int(user_id))
            if mem.status in ('left','kicked'): ok=False
        except Exception: ok=False
    return ok

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    ok = await require_channels(context.application, uid)
    if not ok:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton('Join A', url=f'https://t.me/{REQUIRED_CHANNELS[0].lstrip("@")}')]])
        await update.message.reply_text('Please join channels first.', reply_markup=kb); return
    users.setdefault(uid, {}); users[uid].setdefault('projects', {})
    kb = InlineKeyboardMarkup([[InlineKeyboardButton('▶ New Project', callback_data='newproject')]])
    await update.message.reply_text('Welcome! Use New Project.', reply_markup=kb)

async def newproject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer(); await update.callback_query.edit_message_text('Enter project name:')
    else:
        await update.message.reply_text('Enter project name:')
    return NEW_NAME

async def receive_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip(); uid = str(update.effective_user.id)
    users.setdefault(uid, {}).setdefault('projects', {})
    if name in users[uid]['projects']:
        await update.message.reply_text('Project exists.'); return ConversationHandler.END
    users[uid]['projects'][name] = {'name':name, 'created_at': time.time(), 'running': False, 'web_password': randpass(12)}
    users[uid]['creating'] = name; save_meta()
    await update.message.reply_text(f'Project {name} created. Now send your .py/.js/.zip as Document.')
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id); users.get(uid, {}).pop('creating', None); save_meta(); await update.message.reply_text('Cancelled.'); return ConversationHandler.END

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc: Document = update.message.document; uid = str(update.effective_user.id)
    if not doc: await update.message.reply_text('Send a document'); return
    proj = users.get(uid, {}).get('creating')
    if not proj: await update.message.reply_text('Use /newproject first'); return
    uproj = project_dir(uid, proj); dest = uproj / (doc.file_name or 'uploaded')
    status = await update.message.reply_text(f"📤 Preparing upload...\n▒░░░░░░░ 0%")
    try:
        await status.edit_text("📥 Downloading...\n▓▓░░░░░░ 30%")
        await doc.get_file().download_to_drive(str(dest))
        await status.edit_text("💾 Saving...\n▓▓▓▓▓▓░░ 60%")
        time.sleep(0.5)
        if str(dest).lower().endswith('.zip'):
            await status.edit_text("📦 Extracting...\n▓▓▓▓▓▓▓▓ 85%")
            with zipfile.ZipFile(str(dest),'r') as zf: zf.extractall(path=str(uproj)); dest.unlink()
        await status.edit_text("✅ Finalizing...\n▓▓▓▓▓▓▓▓▓ 100%")
        users[uid].setdefault('projects', {})[proj]['running']=False; users[uid].pop('creating', None); save_meta()
        # show manage menu text
        url = f'https://{RENDER_HOST}/editor/{uid}/project/{proj}'; web_pass = users[uid]['projects'][proj]['web_password']
        await update.message.reply_text(f'Project ready! Web Editor: {url}\nUID: {uid}\nPassword: {web_pass}', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🌐 Manage Files', callback_data=f'manage|{proj}|{uid}')]]))
    except Exception as e:
        await status.edit_text(f"❌ Upload failed: {e}"); return

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); data = q.data
    if data == 'newproject': return await newproject_start(update, context)
    parts = data.split('|'); action = parts[0]
    if action == 'manage':
        proj = parts[1]; uid = parts[2]; uproj = project_dir(uid, proj)
        files = '\n'.join([str(p.relative_to(uproj)) for p in uproj.glob('**/*') if p.is_file()]) or 'No files'
        text = f'Files for {proj}:\n{files}\nOpen web editor to edit.'
        kb = InlineKeyboardMarkup([[InlineKeyboardButton('🖥️ Open Web Editor', url=f'https://{RENDER_HOST}/editor/{uid}/project/{proj}')],[InlineKeyboardButton('🔙 Back', callback_data='back_main')]])
        await q.edit_message_text(text, reply_markup=kb); return

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Use /newproject to create a project.')

def backup_loop():
    while True:
        try:
            for uid,meta in list(users.items()):
                for proj in meta.get('projects',{}).keys():
                    uproj = project_dir(uid, proj)
                    if uproj.exists():
                        outdir = BACKUP_DIR / str(uid); outdir.mkdir(parents=True, exist_ok=True)
                        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S'); z = outdir / f'{proj}_{ts}.zip'
                        with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as zf:
                            for root, dirs, files in os.walk(str(uproj)):
                                for f in files:
                                    fp = pathlib.Path(root)/f; rel = fp.relative_to(uproj); zf.write(fp, arcname=str(rel))
            time.sleep(3600)
        except Exception as e:
            print('backup error', e); time.sleep(60)

def main():
    t = threading.Thread(target=backup_loop, daemon=True); t.start()
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler('newproject', newproject_start), CallbackQueryHandler(newproject_start, pattern='^newproject$')], states={NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_project_name)]}, fallbacks=[CommandHandler('cancel', cancel)])
    app_bot.add_handler(CommandHandler('start', start_cmd)); app_bot.add_handler(conv); app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_document)); app_bot.add_handler(CallbackQueryHandler(callback_handler)); app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    fthread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000))), daemon=True); fthread.start()
    import asyncio; asyncio.run(app_bot.run_polling())

if __name__ == '__main__': main()
