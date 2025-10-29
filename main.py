import os, uuid
from pathlib import Path
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from common.db import SessionLocal, init_db
from common.models import Base, User

DATA_DIR = Path('/app/data')
PROJECTS_DIR = DATA_DIR / 'projects'
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
DEPLOYER_API = os.getenv('DEPLOYER_API', 'http://deployer:5000')

init_db(Base)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [
            InlineKeyboardButton('Upload ZIP', callback_data='help_upload'),
            InlineKeyboardButton('My Projects', callback_data='my_projects')
        ],
        [InlineKeyboardButton('Help', callback_data='help')]
    ]
    await update.message.reply_text('Welcome! Use inline buttons below. Send a .zip to upload.', reply_markup=InlineKeyboardMarkup(kb))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Send a ZIP containing Dockerfile or start.sh/main.py. Use inline buttons to navigate.')

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == 'help_upload':
        await q.edit_message_text('Just send a .zip file to this chat. I will deploy it for you.')
    elif q.data == 'my_projects':
        sess = SessionLocal()
        tg = str(q.from_user.id)
        user = sess.query(User).filter_by(telegram_id=tg).first()
        if not user:
            await q.edit_message_text('No projects yet.')
            sess.close(); return
        projs = user.projects
        lines = []
        for p in projs:
            lines.append(f"{p.id} - {p.status}")
        await q.edit_message_text('Your projects:\n' + ('\n'.join(lines) if lines else 'No projects'))
        sess.close()
    else:
        await q.edit_message_text('Unknown action')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith('.zip'):
        await update.message.reply_text('Please upload a .zip file.')
        return
    uid = str(uuid.uuid4())[:8]
    proj_dir = PROJECTS_DIR / uid
    proj_dir.mkdir(parents=True, exist_ok=True)
    file_path = proj_dir / doc.file_name

    await update.message.reply_text(f'Receiving project... id={uid}')
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(custom_path=str(file_path))

    # ensure user exists in DB
    sess = SessionLocal()
    tg = str(update.message.from_user.id)
    user = sess.query(User).filter_by(telegram_id=tg).first()
    if not user:
        # create with placeholder email
        from werkzeug.security import generate_password_hash
        user = User(email=f"{tg}@telegram.local", telegram_id=tg, password_hash=generate_password_hash(tg), plan='free')
        sess.add(user); sess.commit()
    user_id = user.id
    sess.close()

    payload = {"project_id": uid, "zip_name": doc.file_name, "user_id": user_id}
    try:
        resp = requests.post(f"{DEPLOYER_API}/deploy", json=payload, timeout=60)
    except Exception as e:
        await update.message.reply_text(f'Deployer unreachable: {e}')
        return
    if resp.ok:
        data = resp.json()
        kb = [[InlineKeyboardButton('Status', callback_data=f'status_{uid}'), InlineKeyboardButton('Logs', callback_data=f'logs_{uid}')]]
        await update.message.reply_text(f'Deployed! id={uid}\nUse inline buttons below.', reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(f'Deploy failed: {resp.text}')

async def inline_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data.startswith('status_'):
        pid = data.split('_',1)[1]
        try:
            r = requests.get(f"{DEPLOYER_API}/status/{pid}")
            text = r.text
        except Exception as e:
            text = f'Error: {e}'
        await q.edit_message_text(f'Status for {pid}:\n' + text)
    elif data.startswith('logs_'):
        pid = data.split('_',1)[1]
        try:
            r = requests.get(f"{DEPLOYER_API}/logs/{pid}")
            text = r.text[:3900]
        except Exception as e:
            text = f'Error: {e}'
        await q.edit_message_text(f'Logs for {pid}:\n' + text)

def main():
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        raise RuntimeError('TELEGRAM_TOKEN not set')
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CallbackQueryHandler(inline_status_handler, pattern='^(status_|logs_)'))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    print('Bot started')
    app.run_polling()

if __name__ == '__main__':
    main()
