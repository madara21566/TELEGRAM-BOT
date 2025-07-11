import os
import re
import threading
import time
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template_string, send_file
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# === Configuration ===
OWNER_ID = 7640327597  # Replace with your Telegram ID
ALLOWED_USERS = [7440046924,7669357884,7640327597,5849097477,2134530726,8128934569,7950732287,5989680310]
BOT_START_TIME = datetime.utcnow()

# === Globals ===
logs = []
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100
default_start_index = 1
default_vcf_start_number = 1
merge_data = {}

# === VCF Utilities ===
def generate_vcf(numbers, filename, contact_name, start_index):
    vcf_data = ""
    for i, num in enumerate(numbers, start=start_index):
        name = f"{contact_name}{str(i).zfill(3)}"
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{num}\nEND:VCARD\n"
    with open(filename, "w") as f:
        f.write(vcf_data)
    return filename

def extract_numbers_from_txt(path):
    numbers = set()
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            nums = re.findall(r'\d{7,}', line)
            numbers.update(nums)
    return list(numbers)

# === Telegram Bot Setup ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
app = Application.builder().token(BOT_TOKEN).build()

# === Telegram Commands ===
async def start(update, context):
    uid = update.effective_user.id
    if uid not in ALLOWED_USERS:
        await update.message.reply_text("Unauthorized. Contact the bot owner.")
        return

    uptime = datetime.utcnow() - BOT_START_TIME
    logs.append(f"[START] {uid} - {update.effective_user.username}")
    await update.message.reply_text(f"🤖 Bot is running!\nUptime: {uptime.seconds//60} mins")

async def makevcf(update, context):
    uid = update.effective_user.id
    if uid not in ALLOWED_USERS: return
    if len(context.args) != 2: return await update.message.reply_text("Use: /makevcf Name 9876543210")
    name, number = context.args
    if not number.isdigit(): return await update.message.reply_text("Invalid number.")
    filename = f"{name}.vcf"
    with open(filename, "w") as f:
        f.write(f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{number}\nEND:VCARD\n")
    await update.message.reply_document(document=open(filename, "rb"))
    os.remove(filename)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("makevcf", makevcf))

# === Flask Web Interface ===
flask_app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@flask_app.route('/')
def home():
    return render_template_string("""
    <h2>✅ Telegram VCF Bot is Running!</h2>
    <a href='/upload'>📤 Upload & Convert</a> |
    <a href='/stats'>📊 Stats</a> |
    <a href='/panel?owner_id={{ owner_id }}'>⚙️ Admin</a>
    """, owner_id=OWNER_ID)

@flask_app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files['file']
        contact_prefix = request.form.get('prefix', 'Contact')
        start_index = int(request.form.get('start', '1'))
        if file and file.filename.endswith(('.txt', '.vcf')):
            path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(path)
            numbers = extract_numbers_from_txt(path)
            vcf_file = generate_vcf(numbers, path + '.vcf', contact_prefix, start_index)
            return send_file(vcf_file, as_attachment=True)
    return '''
    <h3>📤 Upload TXT/VCF to Convert</h3>
    <form method="post" enctype="multipart/form-data">
        <input type="file" name="file" required><br><br>
        Contact Name Prefix: <input name="prefix" value="Contact"><br>
        Start Index: <input name="start" value="1"><br><br>
        <input type="submit" value="Convert to VCF">
    </form>
    '''

@flask_app.route('/stats')
def stats():
    uptime = datetime.utcnow() - BOT_START_TIME
    return f"<h3>📊 Bot Stats</h3>Total Users: {len(ALLOWED_USERS)}<br>Uptime: {uptime.seconds//60} mins"

@flask_app.route('/logs')
def show_logs():
    owner_id = request.args.get('owner_id')
    if str(owner_id) != str(OWNER_ID): return "Unauthorized"
    return "<h3>📜 Recent Logs</h3><pre>" + '\n'.join(logs[-30:]) + "</pre>"

@flask_app.route('/panel')
def panel():
    owner_id = request.args.get('owner_id')
    if str(owner_id) != str(OWNER_ID): return "Unauthorized"
    return render_template_string("""
        <h2>⚙️ Admin Panel</h2>
        <a href='/logs?owner_id={{ owner_id }}'>📜 View Logs</a><br>
        <form method='post' action='/cleanup?owner_id={{ owner_id }}'>
            <button type='submit'>🧹 Cleanup Uploaded Files</button>
        </form>
    """, owner_id=OWNER_ID)

@flask_app.route('/cleanup', methods=['POST'])
def cleanup():
    owner_id = request.args.get('owner_id')
    if str(owner_id) != str(OWNER_ID): return "Unauthorized"
    for f in os.listdir(UPLOAD_FOLDER):
        os.remove(os.path.join(UPLOAD_FOLDER, f))
    return "✅ Cleanup done."

# === Run Flask + Bot Together ===
def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    app.run_polling()
    
