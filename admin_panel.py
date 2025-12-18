# =========================
# PART 2: ADMIN PANEL
# =========================

from datetime import datetime
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import ContextTypes

from database_and_access import (
    OWNER_ID,
    db,
    generate_key
)

# ---------- ADMIN PANEL UI ----------
async def show_admin_panel(update):
    keyboard = [
        [InlineKeyboardButton("🔑 Generate Key", callback_data="admin_genkey")],
        [InlineKeyboardButton("📋 Key List", callback_data="admin_keylist")],
        [InlineKeyboardButton("⏳ Expired Keys", callback_data="admin_expired")],
        [InlineKeyboardButton("👤 Users List", callback_data="admin_users")],
        [InlineKeyboardButton("🚫 Block User", callback_data="admin_block")],
        [InlineKeyboardButton("✅ Unblock User", callback_data="admin_unblock")],
        [InlineKeyboardButton("❌ Remove Premium", callback_data="admin_remove")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")]
    ]

    await update.callback_query.message.reply_text(
        "👑 **Admin Panel**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ---------- GENERATE KEY ----------
async def admin_genkey_btn(update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if update.effective_user.id != OWNER_ID:
        return

    context.user_data["admin_genkey"] = True
    await update.callback_query.message.reply_text(
        "🕒 Send duration:\n"
        "`1min` `1hour` `1month` `2months` `1year` `permanent`",
        parse_mode="Markdown"
    )


async def admin_genkey_text(update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("admin_genkey"):
        return

    duration = update.message.text.strip().lower()
    key, exp = generate_key(duration)

    if not key:
        await update.message.reply_text("❌ Invalid duration format")
        return

    context.user_data["admin_genkey"] = False

    msg = f"✅ **Key Generated**\n\n🔑 `{key}`\n"
    msg += "⏳ Permanent" if exp is None else f"⏳ Valid till: `{exp}`"

    await update.message.reply_text(msg, parse_mode="Markdown")


# ---------- KEY LIST ----------
async def admin_key_list(update):
    await update.callback_query.answer()
    if update.effective_user.id != OWNER_ID:
        return

    con = db()
    cur = con.cursor()
    cur.execute("""
    SELECT key, duration, expires_at, used_by
    FROM keys
    ORDER BY created_at DESC
    LIMIT 20
    """)
    rows = cur.fetchall()
    con.close()

    if not rows:
        await update.callback_query.message.reply_text("No keys found.")
        return

    text = "📋 **Last 20 Keys**\n\n"
    for k, d, exp, used in rows:
        text += f"🔑 `{k}`\n"
        text += f"⏳ {d}\n"
        text += f"👤 Used by: {used if used else '—'}\n"
        text += f"📆 Exp: {exp if exp else 'Permanent'}\n\n"

    await update.callback_query.message.reply_text(text, parse_mode="Markdown")


# ---------- EXPIRED KEYS ----------
async def admin_expired_keys(update):
    await update.callback_query.answer()
    if update.effective_user.id != OWNER_ID:
        return

    con = db()
    cur = con.cursor()
    cur.execute("""
    SELECT key, used_by, expires_at
    FROM keys
    WHERE expires_at IS NOT NULL
      AND expires_at < %s
    """, (datetime.utcnow(),))
    rows = cur.fetchall()
    con.close()

    if not rows:
        await update.callback_query.message.reply_text("No expired keys.")
        return

    text = "⏳ **Expired Keys**\n\n"
    for k, u, e in rows:
        text += f"🔑 `{k}`\n👤 {u}\n📆 {e}\n\n"

    await update.callback_query.message.reply_text(text, parse_mode="Markdown")


# ---------- USERS LIST ----------
async def admin_users_list(update):
    await update.callback_query.answer()
    if update.effective_user.id != OWNER_ID:
        return

    con = db()
    cur = con.cursor()
    cur.execute("""
    SELECT user_id, username, premium_until, is_blocked
    FROM users
    ORDER BY joined_at DESC
    LIMIT 30
    """)
    rows = cur.fetchall()
    con.close()

    text = "👤 **Users (last 30)**\n\n"
    for uid, uname, prem, block in rows:
        text += f"🆔 {uid}\n"
        text += f"👤 @{uname}\n"
        text += f"⭐ {'Permanent' if prem is None else prem}\n"
        text += f"🚫 {'Blocked' if block else 'Active'}\n\n"

    await update.callback_query.message.reply_text(text, parse_mode="Markdown")


# ---------- BLOCK / UNBLOCK ----------
async def admin_block_prompt(update, context):
    await update.callback_query.answer()
    context.user_data["admin_block"] = True
    await update.callback_query.message.reply_text(
        "🚫 Send USER ID to block"
    )


async def admin_unblock_prompt(update, context):
    await update.callback_query.answer()
    context.user_data["admin_unblock"] = True
    await update.callback_query.message.reply_text(
        "✅ Send USER ID to unblock"
    )


async def admin_block_text(update, context):
    txt = update.message.text.strip()

    if context.user_data.get("admin_block"):
        field = "TRUE"
        context.user_data["admin_block"] = False
    elif context.user_data.get("admin_unblock"):
        field = "FALSE"
        context.user_data["admin_unblock"] = False
    else:
        return

    con = db()
    cur = con.cursor()
    cur.execute(
        f"UPDATE users SET is_blocked={field} WHERE user_id=%s",
        (int(txt),)
    )
    con.commit()
    con.close()

    await update.message.reply_text("✅ Updated successfully")


# ---------- REMOVE PREMIUM ----------
async def admin_remove_prompt(update, context):
    await update.callback_query.answer()
    context.user_data["admin_remove"] = True
    await update.callback_query.message.reply_text(
        "❌ Send USER ID to remove premium"
    )


async def admin_remove_text(update, context):
    if not context.user_data.get("admin_remove"):
        return

    uid = int(update.message.text.strip())
    con = db()
    cur = con.cursor()
    cur.execute("""
    UPDATE users
    SET premium_until = NULL,
        redeemed_key = NULL
    WHERE user_id = %s
    """, (uid,))
    con.commit()
    con.close()

    context.user_data["admin_remove"] = False
    await update.message.reply_text("❌ Premium removed")


# ---------- BROADCAST ----------
async def admin_broadcast_prompt(update, context):
    await update.callback_query.answer()
    context.user_data["admin_broadcast"] = True
    await update.callback_query.message.reply_text(
        "📢 Send text or photo with caption to broadcast"
    )


async def admin_broadcast_send(update, context):
    if not context.user_data.get("admin_broadcast"):
        return

    con = db()
    cur = con.cursor()
    cur.execute("SELECT user_id FROM users WHERE is_blocked = FALSE")
    users = [u[0] for u in cur.fetchall()]
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

    context.user_data["admin_broadcast"] = False
    await update.message.reply_text("✅ Broadcast sent")
