# =====================================================
# ACCESS SYSTEM – KEY + ADMIN + POSTGRES (FINAL FIXED)
# GOD MADARA
# =====================================================

import os
import re
import uuid
import psycopg2
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

# ================= CONFIG =================
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
DATABASE_URL = os.environ.get("DATABASE_URL")

# ================= DB CONNECTION =================
def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# ================= INIT DB =================
def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id BIGINT PRIMARY KEY,
            premium BOOLEAN DEFAULT FALSE,
            expiry TIMESTAMP,
            blocked BOOLEAN DEFAULT FALSE
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS keys(
            key TEXT PRIMARY KEY,
            expiry_seconds INTEGER,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)
        conn.commit()

# ================= ACCESS CHECK (FIXED) =================
def check_access(user_id: int) -> bool:
    # 👑 OWNER = ALWAYS ALLOWED (NO KEY, NO EXPIRY, NO BLOCK)
    if user_id == OWNER_ID:
        return True

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT premium, expiry, blocked FROM users WHERE user_id=%s",
            (user_id,)
        )
        row = cur.fetchone()

        if not row:
            return False

        premium, expiry, blocked = row

        if blocked:
            return False

        if not premium:
            return False

        if expiry is None:
            return True

        if datetime.utcnow() > expiry:
            # auto-expire
            cur.execute(
                "UPDATE users SET premium=FALSE WHERE user_id=%s",
                (user_id,)
            )
            conn.commit()
            return False

        return True

# ================= ADMIN PANEL UI =================
def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔑 Generate Key", callback_data="admin_genkey"),
            InlineKeyboardButton("📋 User List", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton("⏳ Expired Users", callback_data="admin_expired"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("🚫 Block User", callback_data="admin_block"),
            InlineKeyboardButton("✅ Unblock User", callback_data="admin_unblock")
        ],
        [
            InlineKeyboardButton("➖ Remove Premium", callback_data="admin_remove")
        ]
    ])

# ================= CALLBACK HANDLER =================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    data = query.data

    # ❌ Non-owner cannot use admin panel
    if uid != OWNER_ID:
        return

    if data == "open_admin":
        await query.message.reply_text(
            "👑 ADMIN PANEL",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_genkey":
        context.user_data["await_admin"] = "genkey"
        await query.message.reply_text(
            "⏳ Send duration:\n1h / 1d / 1m / 5m / permanent"
        )

    elif data in {
        "admin_users", "admin_expired",
        "admin_broadcast", "admin_block",
        "admin_unblock", "admin_remove"
    }:
        context.user_data["await_admin"] = data
        await query.message.reply_text("✏️ Send input now")

# ================= TEXT HANDLER =================
async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # ===== REDEEM KEY (USER SIDE) =====
    if context.user_data.get("await_key"):
        context.user_data.pop("await_key")
        if redeem_key(uid, text):
            await update.message.reply_text("✅ Key redeemed successfully")
        else:
            await update.message.reply_text("❌ Invalid or used key")
        return

    # ===== ADMIN ACTIONS =====
    action = context.user_data.get("await_admin")
    if uid != OWNER_ID or not action:
        return

    context.user_data.pop("await_admin")

    if action == "genkey":
        key = generate_key(text)
        if not key:
            await update.message.reply_text("❌ Invalid duration")
            return
        await update.message.reply_text(
            f"🔑 KEY GENERATED:\n`{key}`",
            parse_mode="Markdown"
        )

    elif action == "admin_users":
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, premium, expiry, blocked FROM users")
            rows = cur.fetchall()

        if not rows:
            await update.message.reply_text("No users found")
            return

        msg = ""
        for u,p,e,b in rows:
            msg += f"{u} | P:{p} | E:{e} | B:{b}\n"
        await update.message.reply_text(msg)

    elif action == "admin_expired":
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT user_id FROM users
            WHERE premium=TRUE AND expiry IS NOT NULL AND expiry < NOW()
            """)
            rows = cur.fetchall()

        if not rows:
            await update.message.reply_text("No expired users")
        else:
            await update.message.reply_text(
                "\n".join(str(r[0]) for r in rows)
            )

    elif action == "admin_broadcast":
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users")
            users = cur.fetchall()

        for u in users:
            try:
                await context.bot.send_message(u[0], text)
            except:
                pass

        await update.message.reply_text("📢 Broadcast sent")

    elif action == "admin_block":
        update_user_flag(text, True)
        await update.message.reply_text("🚫 User blocked")

    elif action == "admin_unblock":
        update_user_flag(text, False)
        await update.message.reply_text("✅ User unblocked")

    elif action == "admin_remove":
        remove_premium(text)
        await update.message.reply_text("➖ Premium removed")

# ================= KEY FUNCTIONS =================
def generate_key(duration: str):
    duration = duration.lower()

    if duration == "permanent":
        expiry_sec = None
    else:
        m = re.match(r"(\d+)([hdm])", duration)
        if not m:
            return None
        val, unit = int(m.group(1)), m.group(2)
        expiry_sec = val * (3600 if unit=="h" else 86400 if unit=="d" else 60)

    key = uuid.uuid4().hex[:12]

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO keys(key, expiry_seconds, used) VALUES(%s,%s,FALSE)",
            (key, expiry_sec)
        )
        conn.commit()

    return key

def redeem_key(user_id: int, key: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT expiry_seconds, used FROM keys WHERE key=%s",
            (key,)
        )
        row = cur.fetchone()

        if not row or row[1]:
            return False

        expiry_sec = row[0]
        expiry = None
        if expiry_sec:
            expiry = datetime.utcnow() + timedelta(seconds=expiry_sec)

        cur.execute("""
        INSERT INTO users(user_id, premium, expiry, blocked)
        VALUES(%s,TRUE,%s,FALSE)
        ON CONFLICT(user_id) DO UPDATE
        SET premium=TRUE, expiry=%s, blocked=FALSE
        """,(user_id, expiry, expiry))

        cur.execute(
            "UPDATE keys SET used=TRUE WHERE key=%s",
            (key,)
        )
        conn.commit()
        return True

def update_user_flag(user_id: str, blocked: bool):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET blocked=%s WHERE user_id=%s",
            (blocked, int(user_id))
        )
        conn.commit()

def remove_premium(user_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET premium=FALSE, expiry=NULL WHERE user_id=%s",
            (int(user_id),)
        )
        conn.commit()

# ================= REGISTER HANDLERS =================
def register_handlers(app):
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text))
