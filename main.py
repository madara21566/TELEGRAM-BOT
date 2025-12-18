import os, re, random, string, threading, psycopg2
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    ContextTypes, CallbackQueryHandler, filters
)

# ✅ CONFIG
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 7640327597  # Aapka Owner ID
DATABASE_URL = os.environ.get("DATABASE_URL")

# ✅ FLASK (For Render 24/7)
web = Flask(__name__)
@web.route('/')
def home(): return "Bot is Online"

def run_web():
    web.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

# ✅ DB CONNECTION
def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, expiry TIMESTAMP, status TEXT DEFAULT 'free')")
    cur.execute("CREATE TABLE IF NOT EXISTS keys (key_str TEXT PRIMARY KEY, duration_min INT)")
    cur.execute("CREATE TABLE IF NOT EXISTS blocked (user_id BIGINT PRIMARY KEY)")
    conn.commit(); cur.close(); conn.close()

# ✅ HELPERS
def is_premium(user_id):
    if user_id == OWNER_ID: return True
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT user_id FROM blocked WHERE user_id = %s", (user_id,))
    if cur.fetchone(): return False
    cur.execute("SELECT expiry FROM users WHERE user_id = %s AND status = 'premium'", (user_id,))
    res = cur.fetchone()
    conn.close()
    return True if res and res[0] > datetime.utcnow() else False

# ✅ COMMANDS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u_id = update.effective_user.id
    if is_premium(u_id):
        await update.message.reply_text("✅ Welcome! Aapke paas Full Access hai.\nFile bhejiye conversion ke liye.")
    else:
        btn = [[InlineKeyboardButton("Redeem Your Key 🔑", callback_data="redeem")]]
        await update.message.reply_text("❌ **Access Denied!**\n\nIs bot ko use karne ke liye owner se key lein.", 
                                        reply_markup=InlineKeyboardMarkup(btn))
    
    # Owner ke liye alag se admin button (Sirf owner ko dikhega)
    if u_id == OWNER_ID:
        admin_btn = [[InlineKeyboardButton("Open Admin Panel ⚙️", callback_data="admin_main")]]
        await update.message.reply_text("👋 Hello Owner! Aapka panel niche hai:", 
                                        reply_markup=InlineKeyboardMarkup(admin_btn))

# ✅ ADMIN PANEL
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != OWNER_ID: return
    
    btns = [
        [InlineKeyboardButton("Generate Key 🔑", callback_data="gen_key_menu"), InlineKeyboardButton("Key List 📋", callback_data="list_keys")],
        [InlineKeyboardButton("User List 👥", callback_data="list_users"), InlineKeyboardButton("Broadcast 📢", callback_data="broadcast")],
        [InlineKeyboardButton("Block User 🚫", callback_data="block_ui"), InlineKeyboardButton("Unblock User ✅", callback_data="unblock_ui")],
        [InlineKeyboardButton("Add Premium 💎", callback_data="add_prem_ui"), InlineKeyboardButton("Remove Premium 🗑", callback_data="rem_prem_ui")]
    ]
    await query.edit_message_text("🛠 **ADMIN PANEL**", reply_markup=InlineKeyboardMarkup(btns))

# ✅ KEY GENERATION MENU
async def gen_key_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btns = [
        [InlineKeyboardButton("1 Min", callback_data="gk_1"), InlineKeyboardButton("1 Hour", callback_data="gk_60")],
        [InlineKeyboardButton("1 Month", callback_data="gk_43200"), InlineKeyboardButton("1 Year", callback_data="gk_525600")],
        [InlineKeyboardButton("Back", callback_data="admin_main")]
    ]
    await update.callback_query.edit_message_text("Select Duration:", reply_markup=InlineKeyboardMarkup(btns))

# ✅ CALLBACK HANDLER
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    u_id = query.from_user.id
    data = query.data

    if data == "admin_main": await admin_menu(update, context)
    elif data == "gen_key_menu": await gen_key_menu(update, context)
    elif data == "redeem":
        await query.message.reply_text("📩 Sent your key:")
        context.user_data['waiting'] = "redeem"
    
    elif data.startswith("gk_"):
        mins = int(data.split("_")[1])
        key = "VCF-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO keys (key_str, duration_min) VALUES (%s, %s)", (key, mins))
        conn.commit(); conn.close()
        await query.message.reply_text(f"✅ **Key Generated:** `{key}`\nDuration: {mins} minutes")

    elif data == "list_users":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT user_id, expiry FROM users WHERE status = 'premium'")
        users = cur.fetchall()
        msg = "👥 **Premium Users:**\n" + "\n".join([f"ID: `{u[0]}` | Exp: {u[1]}" for u in users])
        await query.message.reply_text(msg or "No premium users.")
        conn.close()

# ✅ TEXT HANDLER (Redeem, Broadcast, Block etc)
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u_id = update.effective_user.id
    text = update.message.text.strip()
    wait_mode = context.user_data.get('waiting')

    if wait_mode == "redeem":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT duration_min FROM keys WHERE key_str = %s", (text,))
        res = cur.fetchone()
        if res:
            exp = datetime.utcnow() + timedelta(minutes=res[0])
            cur.execute("INSERT INTO users (user_id, expiry, status) VALUES (%s, %s, 'premium') ON CONFLICT (user_id) DO UPDATE SET expiry = %s, status = 'premium'", (u_id, exp, exp))
            cur.execute("DELETE FROM keys WHERE key_str = %s", (text,))
            conn.commit()
            await update.message.reply_text(f"🎉 Success! Access granted until {exp}")
        else:
            await update.message.reply_text("❌ Invalid Key!")
        context.user_data['waiting'] = None
        conn.close()

# ✅ MAIN
if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(CallbackQueryHandler(admin_menu, pattern="admin_main"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # Yaha aapke purane file processing handlers bhi aayenge...

    print("🚀 Bot Started with Admin Panel & Keys...")
    app.run_polling()
  
    
