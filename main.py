import os
import re
import threading
from datetime import datetime
from flask import Flask, request, render_template_string
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# === Configuration ===
OWNER_ID = 7640327597
ALLOWED_USERS = [7440046924,7669357884,7640327597,5849097477,2134530726,8128934569,7950732287,5989680310]
BOT_START_TIME = datetime.utcnow()

# === Tracking ===
logs = []
active_users = set()

# === Telegram Bot Setup ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
app = Application.builder().token(BOT_TOKEN).build()

async def start(update, context):
    uid = update.effective_user.id
    uname = update.effective_user.username or "Unknown"
    if uid not in ALLOWED_USERS:
        await update.message.reply_text("Unauthorized. Contact the bot owner.")
        return

    now = datetime.utcnow()
    uptime = now - BOT_START_TIME
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes = remainder // 60

    active_users.add((uid, uname))
    logs.append(f"[START] {uname} ({uid}) at {now.strftime('%H:%M:%S')} UTC")

    await update.message.reply_text(
        f"""
🤖 Bot is running!
⏱️ Uptime: {hours}h {minutes}m
👤 User: @{uname} (ID: {uid})
🕒 Server Time: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC
        """
    )

app.add_handler(CommandHandler("start", start))

# === Flask App ===
flask_app = Flask(__name__)

@flask_app.route('/')
def dashboard():
    uptime = datetime.utcnow() - BOT_START_TIME
    minutes = uptime.seconds // 60
    hours = minutes // 60
    minutes = minutes % 60
    recent_users = "<br>".join([f"<span style='color:green'>🟢 @{u[1]} (ID: {u[0]})</span>" for u in list(active_users)[-10:]])
    return render_template_string("""
        <html><head><title>VCF Bot Dashboard</title></head><body style="font-family: Arial; padding:20px">
        <h2>📊 <b>VCF Bot Dashboard</b></h2>
        <p><b>✅ Status:</b> Bot is Running</p>
        <p><b>⏰ Uptime:</b> {{ hours }}h {{ minutes }}m</p>
        <p><b>👥 Authorized Users:</b> {{ total_users }}</p>
        <p><b>🧑‍💻 Recent Active Users:</b><br>{{ users|safe }}</p>
        </body></html>
    """, hours=hours, minutes=minutes, total_users=len(ALLOWED_USERS), users=recent_users or "<i>No activity yet</i>")

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
        <a href='/logs?owner_id={{ owner_id }}'>📜 View Logs</a>
    """, owner_id=OWNER_ID)

# === Run Flask + Bot Together ===
def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    app.run_polling()
    
