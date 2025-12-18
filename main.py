import os
import re
import uuid
import psycopg2
import traceback
from datetime import datetime, timedelta

import pandas as pd
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
OWNER_ID = 7640327597

# ================= DB =================
def db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        premium_until TIMESTAMP,
        redeemed_key TEXT,
        is_blocked BOOLEAN DEFAULT FALSE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS keys (
        key TEXT PRIMARY KEY,
        duration TEXT,
        created_at TIMESTAMP,
        expires_at TIMESTAMP,
        used_by BIGINT,
        used_at TIMESTAMP
    )
    """)

    con.commit()
    con.close()

# ================= ACCESS =================
def has_access(user_id):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT premium_until, is_blocked FROM users WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    con.close()

    if not row:
        return False
    premium_until, blocked = row
    if blocked:
        return False
    if premium_until is None:
        return True  # permanent
    return premium_until > datetime.utcnow()

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    con = db()
    cur = con.cursor()
    cur.execute("""
    INSERT INTO users (user_id, username)
    VALUES (%s,%s)
    ON CONFLICT (user_id) DO NOTHING
    """, (user.id, user.username))
    con.commit()
    con.close()

    if not has_access(user.id):
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

    buttons = []
    if user.id == OWNER_ID:
        buttons.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin")])

    await update.message.reply_text(
        "☠️ Welcome to VCF Bot ☠️\n\nSend numbers or files.",
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
    )

# ================= REDEEM =================
async def redeem_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["redeem"] = True
    await update.callback_query.message.reply_text("🔑 Send your premium key")

async def redeem_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("redeem"):
        return

    key = update.message.text.strip()
    user = update.effective_user

    con = db()
    cur = con.cursor()
    cur.execute("SELECT duration, expires_at, used_by FROM keys WHERE key=%s", (key,))
    row = cur.fetchone()

    if not row or row[2] is not None:
        await update.message.reply_text("❌ Invalid or used key")
        con.close()
        return

    duration, exp, _ = row
    if exp and exp < datetime.utcnow():
        await update.message.reply_text("❌ Key expired")
        con.close()
        return

    cur.execute("""
    UPDATE keys SET used_by=%s, used_at=%s WHERE key=%s
    """, (user.id, datetime.utcnow(), key))

    cur.execute("""
    UPDATE users SET premium_until=%s, redeemed_key=%s
    WHERE user_id=%s
    """, (exp, key, user.id))

    con.commit()
    con.close()

    context.user_data["redeem"] = False
    await update.message.reply_text("✅ Premium Activated")

# ================= ADMIN PANEL =================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if update.effective_user.id != OWNER_ID:
        return

    kb = [
        [InlineKeyboardButton("🔑 Generate Key", callback_data="genkey")],
        [InlineKeyboardButton("📋 Key List", callback_data="keylist")],
        [InlineKeyboardButton("⏳ Expired Keys", callback_data="expired")],
        [InlineKeyboardButton("👤 Users List", callback_data="users")],
        [InlineKeyboardButton("🚫 Block User", callback_data="block")],
        [InlineKeyboardButton("✅ Unblock User", callback_data="unblock")],
        [InlineKeyboardButton("❌ Remove Premium", callback_data="remove")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")]
    ]
    await update.callback_query.message.reply_text(
        "👑 Admin Panel",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ================= KEY GEN =================
async def genkey_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["genkey"] = True
    await update.callback_query.message.reply_text(
        "🕒 Enter duration:\n1min | 1hour | 1month | 2months | 1year | permanent"
    )

async def genkey_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("genkey"):
        return

    txt = update.message.text.lower()
    now = datetime.utcnow()

    if txt == "permanent":
        exp = None
    else:
        m = re.match(r"(\d+)(min|hour|month|months|year)", txt)
        if not m:
            await update.message.reply_text("❌ Invalid format")
            return
        n, t = int(m.group(1)), m.group(2)
        delta = {
            "min": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "month": timedelta(days=30*n),
            "months": timedelta(days=30*n),
            "year": timedelta(days=365*n)
        }[t]
        exp = now + delta

    key = "MADARA-" + uuid.uuid4().hex[:8].upper()

    con = db()
    cur = con.cursor()
    cur.execute("""
    INSERT INTO keys VALUES (%s,%s,%s,%s,NULL,NULL)
    """, (key, txt, now, exp))
    con.commit()
    con.close()

    context.user_data["genkey"] = False
    await update.message.reply_text(f"✅ Key Generated\n\n🔑 {key}\n⏳ {txt}")

# ================= BROADCAST =================
async def broadcast_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["broadcast"] = True
    await update.callback_query.message.reply_text("📢 Send text or photo with caption")

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("broadcast"):
        return

    con = db()
    cur = con.cursor()
    cur.execute("SELECT user_id FROM users WHERE is_blocked=FALSE")
    users = [i[0] for i in cur.fetchall()]
    con.close()

    for uid in users:
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    uid,
                    update.message.photo[-1].file_id,
                    caption=update.message.caption
                )
            else:
                await context.bot.send_message(uid, update.message.text)
        except:
            pass

    context.user_data["broadcast"] = False
    await update.message.reply_text("✅ Broadcast sent")

# ================= MAIN =================
if __name__ == "__main__":
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(redeem_btn, pattern="redeem"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="admin"))
    app.add_handler(CallbackQueryHandler(genkey_btn, pattern="genkey"))
    app.add_handler(CallbackQueryHandler(broadcast_btn, pattern="broadcast"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_key))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, genkey_text))
    app.add_handler(MessageHandler(filters.ALL, broadcast_send))

    print("🚀 Bot running")
    app.run_polling()
