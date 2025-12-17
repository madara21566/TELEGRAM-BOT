# ============================================
# GOD MADARA VCF BOT – ADMIN PANEL + KEY SYSTEM
# (USES ORIGINAL NIKALLLLLLL VCF LOGIC)
# ============================================

import os, re, json, time, sys, threading, traceback, datetime, sqlite3
from typing import Optional
from flask import Flask, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ============== IMPORT ORIGINAL VCF BOT ==============
import NIKALLLLLLL   # ⚠️ YOUR ORIGINAL VCF SCRIPT (UNCHANGED)

# ============== CONFIG ==============
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "7640327597"))
PORT = int(os.environ.get("PORT", "8080"))

USER_FILE = "users.json"
KEY_FILE = "keys.json"

START_TIME = datetime.datetime.now()

# ============== FLASK (RENDER KEEP ALIVE) ==============
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "GOD MADARA VCF BOT RUNNING", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

threading.Thread(target=run_flask, daemon=True).start()

# ============== JSON HELPERS ==============
def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(default, f)
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# ============== AUTH SYSTEM ==============
def is_authorized(user_id: int) -> bool:
    data = load_json(USER_FILE, {"users": {}})
    u = data["users"].get(str(user_id))

    if not u or u.get("blocked"):
        return False

    if u["expire_at"] == "never":
        return True

    if datetime.datetime.fromisoformat(u["expire_at"]) < datetime.datetime.utcnow():
        u["premium"] = False
        save_json(USER_FILE, data)
        return False

    return u.get("premium", False)

# ============== START COMMAND ==============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not is_authorized(uid):
        kb = [[InlineKeyboardButton("🔑 Redeem Your Key", callback_data="redeem_btn")]]
        await update.message.reply_text(
            "❌ Access denied\n\n"
            "📂💾 VCF Bot Access\n"
            "Want my VCF Converter Bot?\n"
            "Just DM me anytime — I’ll reply fast!\n\n"
            "📩 @MADARAXHEREE\n\n"
            "⚡ Convert TXT ⇄ VCF instantly | 🔒 Trusted",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    await NIKALLLLLLL.start(update, context)

# ============== REDEEM FLOW ==============
redeem_wait = set()

async def redeem_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    redeem_wait.add(update.callback_query.from_user.id)
    await update.callback_query.message.reply_text("✍️ Send your key now")

async def redeem_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in redeem_wait:
        return

    key = update.message.text.strip()
    keys = load_json(KEY_FILE, {"keys": {}})
    users = load_json(USER_FILE, {"users": {}})

    if key not in keys["keys"] or keys["keys"][key]["used"]:
        await update.message.reply_text("❌ Invalid or used key")
        return

    exp = keys["keys"][key]["expire_at"]
    users["users"][str(uid)] = {
        "premium": True,
        "blocked": False,
        "expire_at": exp
    }

    keys["keys"][key]["used"] = True
    save_json(KEY_FILE, keys)
    save_json(USER_FILE, users)
    redeem_wait.remove(uid)

    await update.message.reply_text("✅ Access Granted! All VCF features unlocked 🚀")

# ============== ADMIN PANEL ==============
admin_wait = {}

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    kb = [
        [InlineKeyboardButton("🔑 Generate Key", callback_data="genkey")],
        [InlineKeyboardButton("📋 User List", callback_data="users")],
        [InlineKeyboardButton("⏳ Expired Users", callback_data="expired")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
        [InlineKeyboardButton("🚫 Block User", callback_data="block"),
         InlineKeyboardButton("✅ Unblock User", callback_data="unblock")],
        [InlineKeyboardButton("➖ Remove Premium", callback_data="remove")]
    ]

    await update.message.reply_text("🛡 ADMIN PANEL", reply_markup=InlineKeyboardMarkup(kb))

# ============== KEY GENERATION ==============
def parse_duration(t):
    if t == "permanent":
        return "never"
    n = int(re.findall(r"\d+", t)[0])
    if "h" in t:
        return (datetime.datetime.utcnow() + datetime.timedelta(hours=n)).isoformat()
    if "d" in t:
        return (datetime.datetime.utcnow() + datetime.timedelta(days=n)).isoformat()
    if "m" in t:
        return (datetime.datetime.utcnow() + datetime.timedelta(days=30*n)).isoformat()

async def genkey_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_wait[update.callback_query.from_user.id] = "genkey"
    await update.callback_query.message.reply_text(
        "⏳ Send duration:\n1h | 1d | 1m | 5m | permanent"
    )

async def admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in admin_wait:
        return

    mode = admin_wait[uid]
    txt = update.message.text.lower()

    if mode == "genkey":
        exp = parse_duration(txt)
        key = "MADARA-" + os.urandom(4).hex().upper()
        data = load_json(KEY_FILE, {"keys": {}})
        data["keys"][key] = {"expire_at": exp, "used": False}
        save_json(KEY_FILE, data)
        await update.message.reply_text(f"🔑 KEY GENERATED\n\n{key}\nValidity: {txt}")

    admin_wait.pop(uid)

# ============== TELEGRAM APP ==============
app = Application.builder().token(BOT_TOKEN).build()

# Core
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_panel))

# Redeem
app.add_handler(CallbackQueryHandler(redeem_btn, pattern="redeem_btn"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_key))

# Admin
app.add_handler(CallbackQueryHandler(genkey_cb, pattern="genkey"))
app.add_handler(MessageHandler(filters.TEXT & filters.User(OWNER_ID), admin_input))

# 🔥 ORIGINAL VCF HANDLERS (UNCHANGED)
app.add_handler(CommandHandler("setfilename", NIKALLLLLLL.set_filename))
app.add_handler(CommandHandler("setcontactname", NIKALLLLLLL.set_contact_name))
app.add_handler(CommandHandler("setlimit", NIKALLLLLLL.set_limit))
app.add_handler(CommandHandler("setstart", NIKALLLLLLL.set_start))
app.add_handler(CommandHandler("setvcfstart", NIKALLLLLLL.set_vcf_start))
app.add_handler(CommandHandler("setcountrycode", NIKALLLLLLL.set_country_code))
app.add_handler(CommandHandler("setgroup", NIKALLLLLLL.set_group_number))
app.add_handler(CommandHandler("makevcf", NIKALLLLLLL.make_vcf_command))
app.add_handler(CommandHandler("merge", NIKALLLLLLL.merge_command))
app.add_handler(CommandHandler("done", NIKALLLLLLL.done_merge))
app.add_handler(CommandHandler("txt2vcf", NIKALLLLLLL.txt2vcf))
app.add_handler(CommandHandler("vcf2txt", NIKALLLLLLL.vcf2txt))
app.add_handler(CommandHandler("reset", NIKALLLLLLL.reset_settings))
app.add_handler(CommandHandler("mysettings", NIKALLLLLLL.my_settings))
app.add_handler(MessageHandler(filters.Document.ALL, NIKALLLLLLL.handle_document))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, NIKALLLLLLL.handle_text))
app.add_error_handler(NIKALLLLLLL.error_handler)

print("🚀 GOD MADARA VCF BOT RUNNING 24/7")
app.run_polling()
