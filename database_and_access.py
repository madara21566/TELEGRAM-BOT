# =========================
# PART 1: DATABASE & ACCESS
# =========================

import os
import re
import uuid
from datetime import datetime, timedelta

import psycopg2
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ---------- CONFIG ----------
DATABASE_URL = os.environ.get("DATABASE_URL")
OWNER_ID = 7640327597


# ---------- DB CONNECTION ----------
def db():
    return psycopg2.connect(DATABASE_URL)


# ---------- INIT DB ----------
def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        premium_until TIMESTAMP,
        redeemed_key TEXT,
        is_blocked BOOLEAN DEFAULT FALSE,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


# ---------- USER UPSERT ----------
def ensure_user(user_id, username):
    con = db()
    cur = con.cursor()
    cur.execute("""
    INSERT INTO users (user_id, username)
    VALUES (%s, %s)
    ON CONFLICT (user_id)
    DO UPDATE SET username = EXCLUDED.username
    """, (user_id, username))
    con.commit()
    con.close()


# ---------- ACCESS CHECK ----------
def has_access(user_id):
    con = db()
    cur = con.cursor()
    cur.execute("""
    SELECT premium_until, is_blocked
    FROM users
    WHERE user_id = %s
    """, (user_id,))
    row = cur.fetchone()
    con.close()

    if not row:
        return False

    premium_until, blocked = row

    if blocked:
        return False

    # permanent access
    if premium_until is None:
        return True

    return premium_until > datetime.utcnow()


# ---------- ACCESS DENIED MESSAGE ----------
async def show_access_denied(update):
    keyboard = [
        [InlineKeyboardButton("🔑 Redeem Your Key", callback_data="redeem")]
    ]

    await update.message.reply_text(
        "❌ Access denied\n\n"
        "📂💾 VCF Bot Access\n"
        "Want my VCF Converter Bot?\n"
        "Just DM me anytime — I’ll reply fast!\n\n"
        "📩 @MADARAXHEREE\n\n"
        "⚡ Convert TXT ⇄ VCF | 🔒 Trusted",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- REDEEM KEY ----------
def redeem_key_for_user(user_id, key_text):
    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT duration, expires_at, used_by
    FROM keys
    WHERE key = %s
    """, (key_text,))
    row = cur.fetchone()

    if not row:
        con.close()
        return False, "❌ Invalid key"

    duration, expires_at, used_by = row

    if used_by is not None:
        con.close()
        return False, "❌ Key already used"

    if expires_at and expires_at < datetime.utcnow():
        con.close()
        return False, "❌ Key expired"

    cur.execute("""
    UPDATE keys
    SET used_by = %s,
        used_at = %s
    WHERE key = %s
    """, (user_id, datetime.utcnow(), key_text))

    cur.execute("""
    UPDATE users
    SET premium_until = %s,
        redeemed_key = %s
    WHERE user_id = %s
    """, (expires_at, key_text, user_id))

    con.commit()
    con.close()

    return True, "✅ Premium Activated"


# ---------- GENERATE KEY ----------
def generate_key(duration_text):
    now = datetime.utcnow()

    if duration_text == "permanent":
        expires_at = None
    else:
        m = re.match(r"(\d+)(min|hour|month|months|year)", duration_text)
        if not m:
            return None, "Invalid duration"

        num = int(m.group(1))
        unit = m.group(2)

        if unit == "min":
            expires_at = now + timedelta(minutes=num)
        elif unit == "hour":
            expires_at = now + timedelta(hours=num)
        elif "month" in unit:
            expires_at = now + timedelta(days=30 * num)
        else:  # year
            expires_at = now + timedelta(days=365 * num)

    key = "MADARA-" + uuid.uuid4().hex[:8].upper()

    con = db()
    cur = con.cursor()
    cur.execute("""
    INSERT INTO keys (key, duration, created_at, expires_at)
    VALUES (%s, %s, %s, %s)
    """, (key, duration_text, now, expires_at))
    con.commit()
    con.close()

    return key, expires_at
