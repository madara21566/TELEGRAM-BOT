# ============================================
# GOD MADARA – FINAL VCF BOT (ADMIN FIXED)
# ============================================

import os, re, json, threading, traceback
from datetime import datetime, timedelta
import pandas as pd
from flask import Flask
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "7640327597"))
PORT = int(os.environ.get("PORT", "10000"))

USER_FILE = "users.json"
KEY_FILE = "keys.json"

# ================= FLASK =================
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "VCF BOT RUNNING OK", 200

def run_flask():
    app_flask.run(host="0.0.0.0", port=PORT)

threading.Thread(target=run_flask, daemon=True).start()

# ================= JSON =================
def load(file, default):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(default, f)
    with open(file) as f:
        return json.load(f)

def save(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# ================= AUTH =================
def is_authorized(uid):
    users = load(USER_FILE, {"users": {}})["users"]
    u = users.get(str(uid))
    if not u or u.get("blocked"):
        return False
    if u["expire_at"] == "never":
        return True
    if datetime.fromisoformat(u["expire_at"]) < datetime.utcnow():
        u["premium"] = False
        save(USER_FILE, {"users": users})
        return False
    return u.get("premium", False)

# ================= VCF CORE =================
def generate_vcf(numbers, fname="Contacts", cname="Contact"):
    vcf = ""
    for i, n in enumerate(numbers, 1):
        vcf += (
            "BEGIN:VCARD\nVERSION:3.0\n"
            f"FN:{cname}{str(i).zfill(3)}\n"
            f"TEL;TYPE=CELL:{n}\n"
            "END:VCARD\n"
        )
    path = f"{fname}.vcf"
    with open(path, "w") as f:
        f.write(vcf)
    return path

def extract_numbers(text):
    return list(dict.fromkeys(re.findall(r"\d{7,}", text)))

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_authorized(uid):
        kb = [[InlineKeyboardButton("🔑 Redeem Your Key", callback_data="redeem")]]
        await update.message.reply_text(
            "❌ Access denied\n\n"
            "📂💾 VCF Bot Access\n"
            "DM me anytime\n\n"
            "📩 @MADARAXHEREE\n\n"
            "⚡ TXT ⇄ VCF | 🔒 Trusted",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    await update.message.reply_text(
        "✅ Premium Access\n\n"
        "📂 Send numbers / TXT / VCF"
    )

# ================= REDEEM =================
redeem_wait = set()

async def redeem_btn(update: Update, context):
    redeem_wait.add(update.callback_query.from_user.id)
    await update.callback_query.message.reply_text("✍️ Send your key now")

async def redeem_text(update: Update, context):
    uid = update.effective_user.id
    if uid not in redeem_wait:
        return

    key = update.message.text.strip()
    keys = load(KEY_FILE, {"keys": {}})
    if key not in keys["keys"] or keys["keys"][key]["used"]:
        await update.message.reply_text("❌ Invalid or used key")
        return

    exp = keys["keys"][key]["expire_at"]
    users = load(USER_FILE, {"users": {}})
    users["users"][str(uid)] = {
        "premium": True,
        "blocked": False,
        "expire_at": exp
    }

    keys["keys"][key]["used"] = True
    save(KEY_FILE, keys)
    save(USER_FILE, users)
    redeem_wait.remove(uid)

    await update.message.reply_text("✅ Access Granted 🚀")

# ================= ADMIN PANEL =================
admin_state = {}

async def admin(update: Update, context):
    if update.effective_user.id != OWNER_ID:
        return

    kb = [
        [InlineKeyboardButton("🔑 Generate Key", callback_data="genkey")],
        [InlineKeyboardButton("📋 User List", callback_data="users")],
        [InlineKeyboardButton("⏳ Expired Users", callback_data="expired")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
        [
            InlineKeyboardButton("🚫 Block User", callback_data="block"),
            InlineKeyboardButton("✅ Unblock User", callback_data="unblock")
        ],
        [InlineKeyboardButton("➖ Remove Premium", callback_data="remove")]
    ]
    await update.message.reply_text("🛡 ADMIN PANEL", reply_markup=InlineKeyboardMarkup(kb))

# ================= KEY =================
def parse_duration(t):
    if t == "permanent":
        return "never"
    n = int(re.findall(r"\d+", t)[0])
    if "h" in t:
        return (datetime.utcnow() + timedelta(hours=n)).isoformat()
    if "d" in t:
        return (datetime.utcnow() + timedelta(days=n)).isoformat()
    if "m" in t:
        return (datetime.utcnow() + timedelta(days=30*n)).isoformat()

async def genkey_cb(update: Update, context):
    admin_state[OWNER_ID] = "genkey"
    await update.callback_query.message.reply_text(
        "⏳ Send duration: 1h / 1d / 1m / 5m / permanent"
    )

async def admin_text(update: Update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if OWNER_ID not in admin_state:
        return

    mode = admin_state.pop(OWNER_ID)
    txt = update.message.text.lower()

    if mode == "genkey":
        exp = parse_duration(txt)
        key = "MADARA-" + os.urandom(4).hex().upper()
        keys = load(KEY_FILE, {"keys": {}})
        keys["keys"][key] = {"expire_at": exp, "used": False}
        save(KEY_FILE, keys)
        await update.message.reply_text(f"🔑 KEY GENERATED\n\n{key}")

# ================= LISTS =================
async def users_cb(update: Update, context):
    users = load(USER_FILE, {"users": {}})["users"]
    msg = "📋 USERS\n\n"
    for u, d in users.items():
        msg += f"{u} | {d['expire_at']}\n"
    await update.callback_query.message.reply_text(msg or "No users")

async def expired_cb(update: Update, context):
    users = load(USER_FILE, {"users": {}})["users"]
    msg = "⏳ EXPIRED\n\n"
    for u, d in users.items():
        if d["expire_at"] != "never" and datetime.fromisoformat(d["expire_at"]) < datetime.utcnow():
            msg += f"{u}\n"
    await update.callback_query.message.reply_text(msg or "None")

# ================= VCF HANDLER =================
async def handle_text(update: Update, context):
    if not is_authorized(update.effective_user.id):
        return
    nums = extract_numbers(update.message.text)
    if not nums:
        return
    vcf = generate_vcf(nums)
    await update.message.reply_document(open(vcf, "rb"))
    os.remove(vcf)

# ================= MAIN =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(CallbackQueryHandler(redeem_btn, pattern="redeem"))
app.add_handler(CallbackQueryHandler(genkey_cb, pattern="genkey"))
app.add_handler(CallbackQueryHandler(users_cb, pattern="users"))
app.add_handler(CallbackQueryHandler(expired_cb, pattern="expired"))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_text))
app.add_handler(MessageHandler(filters.TEXT & filters.User(OWNER_ID), admin_text))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

print("🚀 GOD MADARA FINAL BOT RUNNING")
app.run_polling()
