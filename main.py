# =====================================================
# GOD MADARA – FINAL VCF BOT
# VCF + ADMIN PANEL + KEY SYSTEM (RENDER 24/7)
# =====================================================

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

START_TIME = datetime.utcnow()

# ================= FLASK (KEEP ALIVE) =================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "VCF BOT RUNNING", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

threading.Thread(target=run_flask, daemon=True).start()

# ================= JSON HELPERS =================
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
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

user_file_names = {}
user_contact_names = {}
user_limits = {}
user_country_codes = {}
merge_data = {}

def generate_vcf(numbers, filename, cname, country=""):
    vcf = ""
    for i, n in enumerate(numbers, 1):
        num = f"{country}{n}" if country else n
        vcf += (
            "BEGIN:VCARD\n"
            "VERSION:3.0\n"
            f"FN:{cname}{str(i).zfill(3)}\n"
            f"TEL;TYPE=CELL:{num}\n"
            "END:VCARD\n"
        )
    path = f"{filename}.vcf"
    with open(path, "w") as f:
        f.write(vcf)
    return path

def extract_numbers_from_text(text):
    return list(dict.fromkeys(re.findall(r"\d{7,}", text)))

def extract_numbers_from_vcf(path):
    nums = set()
    with open(path, errors="ignore") as f:
        for line in f:
            if line.startswith("TEL"):
                nums.add(re.sub(r"\D", "", line))
    return list(nums)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_authorized(uid):
        kb = [[InlineKeyboardButton("🔑 Redeem Your Key", callback_data="redeem_btn")]]
        await update.message.reply_text(
            "❌ Access denied\n\n"
            "📂💾 VCF Bot Access\n"
            "Want my VCF Converter Bot?\n"
            "DM me anytime!\n\n"
            "📩 @MADARAXHEREE\n\n"
            "⚡ TXT ⇄ VCF | 🔒 Trusted",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    await update.message.reply_text(
        "✅ Premium Access Enabled\n\n"
        "📌 Send TXT / CSV / XLSX / VCF / Numbers\n"
        "📌 /merge to merge VCF files"
    )

# ================= REDEEM =================
redeem_wait = set()

async def redeem_btn(update: Update, context):
    redeem_wait.add(update.callback_query.from_user.id)
    await update.callback_query.message.reply_text("✍️ Send your key now")

async def redeem_key(update: Update, context):
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
    await update.message.reply_text("✅ Access Granted")

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
        [InlineKeyboardButton("🚫 Block User", callback_data="block"),
         InlineKeyboardButton("✅ Unblock User", callback_data="unblock")],
        [InlineKeyboardButton("➖ Remove Premium", callback_data="remove")]
    ]
    await update.message.reply_text("🛡 ADMIN PANEL", reply_markup=InlineKeyboardMarkup(kb))

def parse_duration(t):
    if t == "permanent":
        return "never"
    n = int(re.findall(r"\d+", t)[0])
    if "h" in t: return (datetime.utcnow()+timedelta(hours=n)).isoformat()
    if "d" in t: return (datetime.utcnow()+timedelta(days=n)).isoformat()
    if "m" in t: return (datetime.utcnow()+timedelta(days=30*n)).isoformat()

async def admin_callback(update: Update, context):
    q = update.callback_query
    uid = q.from_user.id
    if uid != OWNER_ID:
        return

    data = q.data
    admin_state[uid] = data

    if data == "genkey":
        await q.message.reply_text("⏳ Send duration: 1h / 1d / 1m / 5m / permanent")

    elif data == "users":
        users = load(USER_FILE, {"users": {}})["users"]
        txt = "\n".join([f"{u} → {d['expire_at']}" for u,d in users.items()]) or "No users"
        await q.message.reply_text(txt)

    elif data == "expired":
        users = load(USER_FILE, {"users": {}})["users"]
        out = []
        for u,d in users.items():
            if d["expire_at"]!="never" and datetime.fromisoformat(d["expire_at"])<datetime.utcnow():
                out.append(u)
        await q.message.reply_text("\n".join(out) or "None")

    elif data == "broadcast":
        await q.message.reply_text("📢 Send broadcast message")

    elif data in ("block","unblock","remove"):
        await q.message.reply_text("✍️ Send user ID")

async def admin_text(update: Update, context):
    uid = update.effective_user.id
    if uid != OWNER_ID or uid not in admin_state:
        return

    action = admin_state.pop(uid)
    txt = update.message.text.strip()

    users = load(USER_FILE, {"users": {}})

    if action == "genkey":
        exp = parse_duration(txt.lower())
        key = "MADARA-" + os.urandom(4).hex().upper()
        keys = load(KEY_FILE, {"keys": {}})
        keys["keys"][key] = {"expire_at": exp, "used": False}
        save(KEY_FILE, keys)
        await update.message.reply_text(f"🔑 KEY:\n{key}")

    elif action == "broadcast":
        for u in users["users"]:
            try:
                await context.bot.send_message(int(u), txt)
            except: pass
        await update.message.reply_text("✅ Broadcast sent")

    elif action in ("block","unblock","remove"):
        if txt not in users["users"]:
            await update.message.reply_text("❌ User not found")
            return
        if action == "block": users["users"][txt]["blocked"] = True
        if action == "unblock": users["users"][txt]["blocked"] = False
        if action == "remove": users["users"][txt]["premium"] = False
        save(USER_FILE, users)
        await update.message.reply_text("✅ Done")

# ================= FILE / TEXT HANDLER =================
async def handle_document(update: Update, context):
    if not is_authorized(update.effective_user.id):
        return
    doc = update.message.document
    path = doc.file_unique_id
    await (await context.bot.get_file(doc.file_id)).download_to_drive(path)

    if doc.file_name.endswith(".vcf"):
        nums = extract_numbers_from_vcf(path)
    else:
        with open(path, errors="ignore") as f:
            nums = extract_numbers_from_text(f.read())
    os.remove(path)

    if not nums:
        await update.message.reply_text("❌ No numbers found")
        return

    fname = user_file_names.get(update.effective_user.id, default_vcf_name)
    cname = user_contact_names.get(update.effective_user.id, default_contact_name)
    country = user_country_codes.get(update.effective_user.id, "")

    vcf = generate_vcf(nums, fname, cname, country)
    await update.message.reply_document(open(vcf, "rb"))
    os.remove(vcf)

async def handle_text(update: Update, context):
    if not is_authorized(update.effective_user.id):
        return
    nums = extract_numbers_from_text(update.message.text)
    if not nums:
        return
    vcf = generate_vcf(nums, default_vcf_name, default_contact_name)
    await update.message.reply_document(open(vcf, "rb"))
    os.remove(vcf)

# ================= ERROR =================
async def error(update, context):
    traceback.print_exception(None, context.error, context.error.__traceback__)

# ================= MAIN =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CallbackQueryHandler(redeem_btn, pattern="redeem_btn"))
app.add_handler(CallbackQueryHandler(admin_callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_key))
app.add_handler(MessageHandler(filters.TEXT & filters.User(OWNER_ID), admin_text))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_error_handler(error)

print("🚀 GOD MADARA VCF BOT RUNNING")
app.run_polling()
