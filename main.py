
import os
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder
import asyncio

WEBHOOK_URL = "https://telegram-bot-bmlu.onrender.com/webhook"
TOKEN = "7727685861:AAE_tR7qsTx-_NlxfwQ-JgqeJDkpvnXEYkg"

flask_app = Flask(__name__)
application = ApplicationBuilder().token(TOKEN).build()

# ---- Original Bot Logic Start ----
import os
import re
import csv
import time
import pandas as pd
from datetime import datetime
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from telegram.helpers import mention_html
from io import StringIO

# Configuration
TELEGRAM_BOT_TOKEN = '7727685861:AAE_tR7qsTx-_NlxfwQ-JgqeJDkpvnXEYkg'
OWNER_ID = 7640327597  # Replace with your actual Telegram user ID

# Default settings
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100
default_start_index = 1
default_vcf_start_number = 1

# Data structures
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
merge_data = {}
user_access = defaultdict(dict)  # {user_id: {'level': int, 'expiry': datetime/None}}
TEMP_USERS = {}
GROUP_ADMINS = set()

# Access levels
ACCESS_LEVELS = {
    'admin': 3,
    'editor': 2,
    'viewer': 1
}

def is_authorized(user_id):
    """Check if user has access to the bot"""
    if user_id == OWNER_ID:
        return True
    if user_id in GROUP_ADMINS:
        return True
    if user_id in TEMP_USERS and TEMP_USERS[user_id] > time.time():
        return True
    if user_id in user_access:
        access = user_access[user_id]
        if access['expiry'] and datetime.now() > access['expiry']:
            del user_access[user_id]
            return False
        return True
    TEMP_USERS.pop(user_id, None)
    return False

def has_access_level(user_id, required_level):
    """Check if user has sufficient access level"""
    if user_id == OWNER_ID:
        return True
    if user_id in GROUP_ADMINS:
        return True
    if user_id in user_access:
        return user_access[user_id]['level'] >= required_level
    return False

def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=1):
    """Generate VCF file from list of numbers"""
    vcf_data = ""
    for i, num in enumerate(numbers, start=start_index):
        name = f"{contact_name}{str(i).zfill(3)}"
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{num}\nEND:VCARD\n"
    with open(f"{filename}.vcf", "w") as f:
        f.write(vcf_data)
    return f"{filename}.vcf"

def extract_numbers_from_vcf(file_path):
    """Extract phone numbers from a VCF file"""
    numbers = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for card in content.split('END:VCARD'):
        if 'TEL' in card:
            tel_lines = [line for line in card.splitlines() if line.startswith('TEL')]
            for line in tel_lines:
                number = line.split(':')[-1].strip()
                number = re.sub(r'[^0-9]', '', number)  # Clean the number
                if number:
                    numbers.add(number)
    return numbers

def extract_numbers_from_txt(file_path):
    """Extract phone numbers from a TXT file"""
    numbers = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Extract all numbers with at least 7 digits (minimum for a phone number)
            line_numbers = re.findall(r'\d{7,}', line)
            numbers.update(line_numbers)
    return numbers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized. Please contact the bot owner.")
        return
    
    help_text = """Welcome to the VCF Bot!

Available Commands:
/setfilename <name> - Set VCF filename prefix
/setcontactname <name> - Set contact name prefix
/setlimit <number> - Limit contacts per VCF
/setstart <number> - Start index for contact numbering
/setvcfstart <number> - VCF file numbering start
/makevcf Name 9876543210 - Create single VCF
/merge output_name - Start merging VCF/TXT files
/done - Complete merge operation
/panel - Owner/Admin control panel

Send a TXT, CSV, XLSX, or VCF file or plain numbers to generate contacts."""
    
    await update.message.reply_text(help_text)

async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set VCF filename prefix"""
    if not has_access_level(update.effective_user.id, 2): return
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"File name set to: {' '.join(context.args)}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set contact name prefix"""
    if not has_access_level(update.effective_user.id, 2): return
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"Contact name prefix set to: {' '.join(context.args)}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set contacts per VCF limit"""
    if not has_access_level(update.effective_user.id, 2): return
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"VCF contact limit set to {context.args[0]}")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set starting index for numbering"""
    if not has_access_level(update.effective_user.id, 2): return
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"Start index set to {context.args[0]}.")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set VCF file numbering start"""
    if not has_access_level(update.effective_user.id, 2): return
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"VCF numbering will start from {context.args[0]}.")

async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create single VCF file"""
    if not has_access_level(update.effective_user.id, 2): return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /makevcf Name 9876543210")
        return
    name, number = context.args
    if not number.isdigit():
        await update.message.reply_text("Invalid phone number.")
        return
    file_name = f"{name}.vcf"
    with open(file_name, "w") as f:
        f.write(f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{number}\nEND:VCARD\n")
    await update.message.reply_document(document=open(file_name, "rb"))
    os.remove(file_name)

async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start merge operation"""
    if not has_access_level(update.effective_user.id, 2): return
    if not context.args:
        await update.message.reply_text("Usage: /merge output_filename")
        return
    
    output_name = context.args[0]
    user_id = update.effective_user.id
    merge_data[user_id] = {
        'output_name': output_name,
        'files': [],
        'numbers': set()
    }
    
    await update.message.reply_text(
        f"Merge session started. Send me VCF or TXT files to merge.\n"
        f"Final file will be saved as: {output_name}.vcf\n"
        "Send /done when finished or /cancel to abort."
    )

async def handle_merge_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process files during merge operation"""
    user_id = update.effective_user.id
    if user_id not in merge_data:
        return
    
    file = update.message.document
    file_ext = file.file_name.split('.')[-1].lower()
    
    if file_ext not in ['vcf', 'txt']:
        await update.message.reply_text("Only VCF and TXT files are supported.")
        return
    
    # Download the file
    path = f"temp_{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    merge_data[user_id]['files'].append(path)
    
    # Process the file
    if file_ext == 'vcf':
        numbers = extract_numbers_from_vcf(path)
    else:  # TXT
        numbers = extract_numbers_from_txt(path)
    
    merge_data[user_id]['numbers'].update(numbers)
    os.remove(path)
    
    await update.message.reply_text(
        f"File processed. Found {len(numbers)} numbers. "
        f"Total unique numbers: {len(merge_data[user_id]['numbers'])}\n"
        "Send more files or /done to finish."
    )

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Complete merge operation"""
    user_id = update.effective_user.id
    if user_id not in merge_data:
        await update.message.reply_text("No active merge session.")
        return
    
    session = merge_data[user_id]
    if not session['numbers']:
        await update.message.reply_text("No numbers found in the files.")
        del merge_data[user_id]
        return
    
    # Generate the merged VCF
    output_path = f"{session['output_name']}.vcf"
    contact_name = user_contact_names.get(user_id, default_contact_name)
    start_index = user_start_indexes.get(user_id, default_start_index)
    
    vcf_data = ""
    for i, num in enumerate(sorted(session['numbers']), start=start_index):
        name = f"{contact_name}{str(i).zfill(3)}"
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{num}\nEND:VCARD\n"
    
    with open(output_path, 'w') as f:
        f.write(vcf_data)
    
    # Send the file to user
    await update.message.reply_document(document=open(output_path, 'rb'))
    os.remove(output_path)
    
    # Clean up
    await update.message.reply_text(
        f"Merge complete! {len(session['numbers'])} unique contacts created."
    )
    del merge_data[user_id]

async def handle_bulk_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process CSV file with bulk user data"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only the owner can perform bulk operations.")
        return
    
    if not update.message.document or not update.message.document.file_name.endswith('.csv'):
        await update.message.reply_text("Please upload a CSV file.")
        return
    
    # Download the file
    file = await context.bot.get_file(update.message.document.file_id)
    file_data = await file.download_as_bytearray()
    csv_data = file_data.decode('utf-8')
    
    # Process CSV
    success_count = 0
    error_count = 0
    reader = csv.reader(StringIO(csv_data))
    
    for row in reader:
        if len(row) < 2:  # Skip invalid rows
            error_count += 1
            continue
        
        try:
            user_id = int(row[0])
            access_level = row[1].lower()
            expiry_date = None
            
            if len(row) > 2 and row[2]:
                expiry_date = datetime.strptime(row[2], '%Y-%m-%d')
            
            if access_level not in ACCESS_LEVELS:
                error_count += 1
                continue
            
            user_access[user_id] = {
                'level': ACCESS_LEVELS[access_level],
                'expiry': expiry_date
            }
            success_count += 1
        except Exception as e:
            error_count += 1
            print(f"Error processing row: {row}. Error: {str(e)}")
    
    await update.message.reply_text(
        f"Bulk user import complete!\n"
        f"Successfully processed: {success_count}\n"
        f"Failed to process: {error_count}"
    )

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export user list as CSV"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only the owner can export user data.")
        return
    
    # Prepare CSV data
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['User ID', 'Access Level', 'Expiry Date'])
    
    for user_id, data in user_access.items():
        level_name = [k for k, v in ACCESS_LEVELS.items() if v == data['level']][0]
        expiry = data['expiry'].strftime('%Y-%m-%d') if data['expiry'] else ''
        writer.writerow([user_id, level_name, expiry])
    
    # Send as file
    output.seek(0)
    with open('user_list.csv', 'w') as f:
        f.write(output.getvalue())
    
    await update.message.reply_document(document=open('user_list.csv', 'rb'))
    os.remove('user_list.csv')

async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show owner/admin control panel"""
    user = update.effective_user
    chat = update.effective_chat
    
    is_owner = user.id == OWNER_ID
    is_admin = False
    if chat.type in ["group", "supergroup"]:
        member = await chat.get_member(user.id)
        is_admin = member.status in ["administrator", "creator"]
    
    if not (is_owner or is_admin):
        await update.message.reply_text("Only the owner or a group admin can access this.")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Add User", callback_data='add_user')],
        [InlineKeyboardButton("➖ Remove User", callback_data='remove_user')],
        [InlineKeyboardButton("📋 List Users", callback_data='list_users')],
        [InlineKeyboardButton("📥 Bulk Add Users", callback_data='bulk_add')],
        [InlineKeyboardButton("📤 Export Users", callback_data='export_users')],
        [InlineKeyboardButton("⏳ Temporary Access", callback_data='temp_user')],
        [InlineKeyboardButton("👑 Add Admin", callback_data='add_admin')],
        [InlineKeyboardButton("🚫 Remove Admin", callback_data='remove_admin')],
        [InlineKeyboardButton("📜 List Admins", callback_data='list_admins')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👑 Owner/Admin Control Panel:", reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle panel callback queries"""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if user_id != OWNER_ID and user_id not in GROUP_ADMINS:
        await query.edit_message_text("❌ Unauthorized.")
        return
    
    if data == 'add_user':
        context.user_data['mode'] = 'add_user'
        await query.edit_message_text("📝 Send the user ID to add in this format:\n\n<code>user_id access_level</code>\n\nExample: <code>123456789 admin</code>\n\nAvailable levels: admin, editor, viewer", parse_mode='HTML')
    elif data == 'remove_user':
        context.user_data['mode'] = 'remove_user'
        await query.edit_message_text("🗑 Send the user ID to remove:")
    elif data == 'list_users':
        if not user_access:
            await query.edit_message_text("ℹ️ No users found.")
            return
        
        message = "👥 List of Users:\n\n"
        for uid, data in sorted(user_access.items(), key=lambda x: x[1]['level'], reverse=True):
            level_name = [k for k, v in ACCESS_LEVELS.items() if v == data['level']][0].title()
            expiry = data['expiry'].strftime('%Y-%m-%d') if data['expiry'] else 'No expiry'
            message += f"🆔 <b>{uid}</b>\n⚙️ Level: {level_name}\n📅 Expiry: {expiry}\n\n"
        
        await query.edit_message_text(message, parse_mode='HTML')
    elif data == 'bulk_add':
        await query.edit_message_text("📂 Please upload a CSV file with the following format:\n\n<code>user_id,access_level,expiry_date(optional)</code>\n\nExample:\n<code>123456789,admin,2023-12-31</code>", parse_mode='HTML')
    elif data == 'export_users':
        await export_users(update, context)
    elif data == 'temp_user':
        context.user_data['mode'] = 'temp_user'
        await query.edit_message_text("⏳ Send user ID and duration in minutes in this format:\n\n<code>user_id minutes</code>\n\nExample: <code>123456789 60</code>", parse_mode='HTML')
    elif data == 'add_admin':
        context.user_data['mode'] = 'add_admin'
        await query.edit_message_text("👑 Send user ID to make admin:")
    elif data == 'remove_admin':
        context.user_data['mode'] = 'remove_admin'
        await query.edit_message_text("🚫 Send user ID to remove from admin:")
    elif data == 'list_admins':
        if not GROUP_ADMINS:
            await query.edit_message_text("ℹ️ No group admins found.")
        else:
            message = "👑 Group Admins:\n\n" + '\n'.join(f"🆔 {uid}" for uid in sorted(GROUP_ADMINS))
            await query.edit_message_text(message)

async def handle_owner_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process owner/admin input from panel"""
    user = update.effective_user
    if user.id != OWNER_ID and user.id not in GROUP_ADMINS: 
        return
    
    mode = context.user_data.get('mode')
    
    try:
        if mode == 'add_user':
            parts = update.message.text.split()
            if len(parts) >= 2:
                user_id = int(parts[0])
                access_level = parts[1].lower()
                
                if access_level not in ACCESS_LEVELS:
                    await update.message.reply_text("❌ Invalid access level. Use: admin, editor, or viewer")
                    return
                
                expiry = None
                if len(parts) > 2:
                    try:
                        expiry = datetime.strptime(parts[2], '%Y-%m-%d')
                    except ValueError:
                        await update.message.reply_text("⚠️ Invalid date format. Use YYYY-MM-DD or leave blank for no expiry")
                        return
                
                user_access[user_id] = {
                    'level': ACCESS_LEVELS[access_level],
                    'expiry': expiry
                }
                await update.message.reply_text(f"✅ User {user_id} added as {access_level}" + (f" until {expiry}" if expiry else ""))
            else:
                await update.message.reply_text("❌ Usage: user_id access_level (admin/editor/viewer) [expiry_date]")
        
        elif mode == 'remove_user':
            try:
                user_id = int(update.message.text)
                if user_id in user_access:
                    del user_access[user_id]
                    await update.message.reply_text(f"✅ User {user_id} removed.")
                else:
                    await update.message.reply_text("❌ User not found.")
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID.")
        
        elif mode == 'temp_user':
            try:
                uid, minutes = map(int, update.message.text.split())
                TEMP_USERS[uid] = time.time() + minutes * 60
                await update.message.reply_text(f"⏳ Temporary access given to {uid} for {minutes} minutes.")
            except:
                await update.message.reply_text("❌ Usage: user_id minutes")
        
        elif mode == 'add_admin':
            try:
                admin_id = int(update.message.text)
                GROUP_ADMINS.add(admin_id)
                await update.message.reply_text(f"👑 User {admin_id} added as admin.")
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID.")
        
        elif mode == 'remove_admin':
            try:
                admin_id = int(update.message.text)
                GROUP_ADMINS.discard(admin_id)
                await update.message.reply_text(f"🚫 User {admin_id} removed from admins.")
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID.")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    
    context.user_data['mode'] = None

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads"""
    if not is_authorized(update.effective_user.id): return
    
    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    user_id = update.effective_user.id
    
    # Check if in merge mode
    if user_id in merge_data:
        merge_data[user_id]['files'].append(path)
        file_ext = file.file_name.split('.')[-1].lower()
        
        if file_ext == 'vcf':
            numbers = extract_numbers_from_vcf(path)
        elif file_ext == 'txt':
            numbers = extract_numbers_from_txt(path)
        else:
            await update.message.reply_text("Only VCF and TXT files can be merged.")
            os.remove(path)
            return
        
        merge_data[user_id]['numbers'].update(numbers)
        os.remove(path)
        
        await update.message.reply_text(
            f"📂 File added to merge. Total unique numbers: {len(merge_data[user_id]['numbers'])}\n"
            "Send more files or /done to finish."
        )
        return
    
    # Normal file processing
    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path)
        elif path.endswith('.xlsx'):
            df = pd.read_excel(path)
        elif path.endswith('.txt'):
            with open(path, 'r') as f:
                numbers = [''.join(filter(str.isdigit, word)) for word in f.read().split() if len(word) >= 7]
            df = pd.DataFrame({'Numbers': numbers})
        elif path.endswith('.vcf'):
            with open(path, 'r') as f:
                data = f.read()
            entries = set()
            for card in data.split("END:VCARD"):
                if "TEL" in card:
                    lines = card.splitlines()
                    tel = next((l for l in lines if l.startswith("TEL")), None)
                    if tel:
                        entries.add(tel.split(":")[-1].strip())
            df = pd.DataFrame({'Numbers': list(entries)})
        else:
            await update.message.reply_text("❌ Unsupported file type.")
            return
        
        await process_numbers(update, context, df['Numbers'].dropna().astype(str).tolist())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        if os.path.exists(path): os.remove(path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages with numbers"""
    if not is_authorized(update.effective_user.id): return
    
    numbers = [''.join(filter(str.isdigit, word)) for word in update.message.text.split() if len(word) >= 7]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("❌ No valid numbers found.")

async def process_numbers(update, context, numbers):
    """Process list of numbers and generate VCF files"""
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_name_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, default_start_index)
    vcf_start_number = user_vcf_start_numbers.get(user_id, default_vcf_start_number)
    
    numbers = list(dict.fromkeys([n.strip() for n in numbers if n.strip().isdigit()]))
    chunks = [numbers[i:i + limit] for i in range(0, len(numbers), limit)]
    
    for idx, chunk in enumerate(chunks):
        file_path = generate_vcf(
            chunk, 
            f"{file_name_base}_{vcf_start_number + idx}", 
            contact_name, 
            start_index + idx * limit
        )
        await update.message.reply_document(document=open(file_path, "rb"))
        os.remove(file_path)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('setfilename', set_filename))
    app.add_handler(CommandHandler('setcontactname', set_contact_name))
    app.add_handler(CommandHandler('setlimit', set_limit))
    app.add_handler(CommandHandler('setstart', set_start))
    app.add_handler(CommandHandler('setvcfstart', set_vcf_start))
    app.add_handler(CommandHandler('makevcf', make_vcf_command))
    app.add_handler(CommandHandler('merge', merge_command))
    app.add_handler(CommandHandler('done', done_merge))
    app.add_handler(CommandHandler('panel', owner_panel))
    app.add_handler(CommandHandler('exportusers', export_users))
    
    # Callback and message handlers
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & (filters.User(user_id=OWNER_ID) | filters.User(user_id=GROUP_ADMINS)), handle_owner_input))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    app.run_polling()

# ---- Original Bot Logic End ----

@flask_app.route("/", methods=["GET"])
def home():
    return "Bot is alive!"

@flask_app.route("/webhook", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok"

if __name__ == "__main__":
    async def start():
        try:
            await application.initialize()
            await application.bot.set_webhook(WEBHOOK_URL)
            await application.start()
        except Exception as e:
            print("Webhook error:", e)
        finally:
            flask_app.run(
                host="0.0.0.0",
                port=int(os.environ.get("PORT", 5000)),
                debug=False,
                use_reloader=False
            )

    asyncio.run(start())
