# ============================================
# GOD MADARA VCF BOT – FINAL WORKING VERSION
# ============================================

import os, json, re, time, sys, threading, traceback
import datetime
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ================= ENV =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "7640327597"))
PORT = int(os.environ.get("PORT", "10000"))

USER_FILE = "users.json"
KEY_FILE = "keys.json"

# ================= FLASK =================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "VCF BOT RUNNING", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

threading.Thread(target=run_flask, daemon=True).start()

# ================= JSON =================
def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(default, f)
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# ================= AUTH =================
def is_authorized(uid):
    data = load_json(USER_FILE, {"users": {}})
    u = data["users"].get(str(uid))
    if not u or u.get("blocked"):
        return False

    if u["expire_at"] == "never":
        return True

    if datetime.datetime.fromisoformat(u["expire_at"]) < datetime.datetime.utcnow():
        u["premium"] = False
        save_json(USER_FILE, data)
        return False

    return u.get("premium", False)

# ================= IMPORT VCF BOT =================
import NIKALLLLLLL

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not is_authorized(uid):
        kb = [[InlineKeyboardButton("🔑 Redeem Your Key", callback_data="redeem")]]
        await update.message.reply_text(
            "❌ Access denied\n\n"
            "📂💾 VCF Bot Access\n"
            "Want my VCF Converter Bot?\n"
            "Just DM me anytime — I’ll reply fast!\n\n"
            "📩 @MADARAXHEREE\n\n"
            "⚡ Convert TXT ⇄ VCF | 🔒 Trusted",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    await NIKALLLLLLL.start(update, context)

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
    keys = load_json(KEY_FILE, {"keys": {}})

    if key not in keys["keys"] or keys["keys"][key]["used"]:
        await update.message.reply_text("❌ Invalid or used key")
        return

    expire = keys["keys"][key]["expire_at"]
    users = load_json(USER_FILE, {"users": {}})

    users["users"][str(uid)] = {
        "premium": True,
        "blocked": False,
        "expire_at": expire
    }

    keys["keys"][key]["used"] = True
    save_json(KEY_FILE, keys)
    save_json(USER_FILE, users)

    redeem_wait.remove(uid)
    await update.message.reply_text("✅ Premium Activated Successfully")

# ================= ADMIN PANEL =================
admin_state = {}

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    await update.message.reply_text(
        "🛡 ADMIN PANEL",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ================= KEY GEN =================
def parse_duration(t):
    if t == "permanent":
        return "never"
    n = int(re.findall(r"\d+", t)[0])
    if "h" in t:
        return (datetime.datetime.utcnow() + datetime.timedelta(hours=n)).isoformat()
    if "d" in t:
        return (datetime.datetime.utcnow() + datetime.timedelta(days=n)).isoformat()
    if "m" in t:
        return (datetime.datetime.utcnow() + datetime.timedelta(days=n*30)).isoformat()

async def genkey_cb(update: Update, context):
    admin_state[update.callback_query.from_user.id] = "genkey"
    await update.callback_query.message.reply_text(
        "⏳ Send duration:\n1h | 1d | 1m | 5m | permanent"
    )

async def admin_text(update: Update, context):
    uid = update.effective_user.id
    if uid not in admin_state:
        return

    mode = admin_state[uid]
    text = update.message.text.lower()

    if mode == "genkey":
        expire = parse_duration(text)
        key = "MADARA-" + os.urandom(4).hex().upper()
        data = load_json(KEY_FILE, {"keys": {}})
        data["keys"][key] = {"expire_at": expire, "used": False}
        save_json(KEY_FILE, data)
        await update.message.reply_text(f"🔑 KEY GENERATED\n\n{key}")

    admin_state.pop(uid)

# ================= CALLBACK ACTIONS =================
async def users_cb(update: Update, context):
    users = load_json(USER_FILE, {"users": {}})["users"]
    msg = "📋 USERS\n\n"
    for uid, d in users.items():
        msg += f"{uid} | {d['expire_at']}\n"
    await update.callback_query.message.reply_text(msg or "No users")

async def expired_cb(update: Update, context):
    users = load_json(USER_FILE, {"users": {}})["users"]
    msg = "⏳ EXPIRED USERS\n\n"
    now = datetime.datetime.utcnow()
    for uid, d in users.items():
        if d["expire_at"] != "never" and datetime.datetime.fromisoformat(d["expire_at"]) < now:
            msg += f"{uid}\n"
    await update.callback_query.message.reply_text(msg or "None")

# ================= BOT =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(CallbackQueryHandler(redeem_btn, pattern="redeem"))
app.add_handler(CallbackQueryHandler(genkey_cb, pattern="genkey"))
app.add_handler(CallbackQueryHandler(users_cb, pattern="users"))
app.add_handler(CallbackQueryHandler(expired_cb, pattern="expired"))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_key))
app.add_handler(MessageHandler(filters.TEXT & filters.User(OWNER_ID), admin_text))

# Forward VCF handlers (unchanged)
app.add_handler(CommandHandler("setfilename", NIKALLLLLLL.set_filename))
app.add_handler(CommandHandler("setcontactname", NIKALLLLLLL.set_contact_name))
app.add_handler(CommandHandler("setlimit", NIKALLLLLLL.set_limit))
app.add_handler(CommandHandler("setstart", NIKALLLLLLL.set_start))
app.add_handler(CommandHandler("setvcfstart", NIKALLLLLLL.set_vcf_start))
app.add_handler(CommandHandler("setcountrycode", NIKALLLLLLL.set_country_code))
app.add_handler(CommandHandler("setgroup", NIKALLLLLLL.set_group_number))
app.add_handler(CommandHandler("merge", NIKALLLLLLL.merge_command))
app.add_handler(CommandHandler("done", NIKALLLLLLL.done_merge))
app.add_handler(CommandHandler("txt2vcf", NIKALLLLLLL.txt2vcf))
app.add_handler(CommandHandler("vcf2txt", NIKALLLLLLL.vcf2txt))
app.add_handler(MessageHandler(filters.Document.ALL, NIKALLLLLLL.handle_document))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, NIKALLLLLLL.handle_text))

print("🚀 GOD MADARA VCF BOT RUNNING (FINAL)")
app.run_polling()
