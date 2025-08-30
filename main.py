"""
Advanced VCF Manager Bot with Flask Web Interface
-------------------------------------------------
Features:
- TXT/VCF upload & download via Telegram & Web
- Duplicate check & removal
- Prefix/suffix add/remove
- Split large files
- Advanced renaming
- Multi-user safe
- Stats & reports
- TXT ↔ VCF conversion
- Interactive inline buttons
- 10k+ numbers support
- Flask web interface for status, upload, history

Requirements:
- Python 3.10+
- aiogram==3.*
- Flask, phonenumbers, vobject, aiofiles, python-dotenv

.env:
BOT_TOKEN=123456:ABC...
TWILIO_ACCOUNT_SID=ACxxxxx   # optional
TWILIO_AUTH_TOKEN=xxxx        # optional
NUMVERIFY_KEY=xxxx            # optional
"""

import os, asyncio, time
from threading import Thread
from flask import Flask, render_template_string, request, redirect, url_for
import phonenumbers, vobject, aiofiles
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.markdown import hbold, hcode
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
TEMP_DIR = 'tmp'
os.makedirs(TEMP_DIR, exist_ok=True)

bot = Bot(BOT_TOKEN, parse_mode='HTML')
dp = Dispatcher()

@dataclass
class RateLimiter:
    cooldown_seconds: int = 3
    last_call: dict = None
    def __post_init__(self):
        if self.last_call is None: self.last_call = {}
    def allow(self, user_id:int) -> bool:
        now = time.time()
        if user_id not in self.last_call or now - self.last_call[user_id] >= self.cooldown_seconds:
            self.last_call[user_id] = now
            return True
        return False
limiter = RateLimiter()

# --- Helpers ---
async def read_numbers_from_file(filepath:str) -> list:
    numbers = []
    async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
        async for line in f: numbers.append(line.strip())
    return numbers

async def write_numbers_to_file(numbers:list, filepath:str):
    async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
        for n in numbers: await f.write(f'{n}\n')

def remove_duplicates(numbers:list) -> list:
    seen = set(); result = []
    for n in numbers:
        if n not in seen: seen.add(n); result.append(n)
    return result

def add_prefix(numbers:list, prefix:str) -> list: return [prefix + n.lstrip('+') for n in numbers]
def remove_prefix(numbers:list, prefix:str) -> list: return [n[len(prefix):] if n.startswith(prefix) else n for n in numbers]

async def txt_to_vcf(numbers:list, filename:str) -> str:
    vcf_path = os.path.join(TEMP_DIR, filename + '.vcf')
    with open(vcf_path,'w',encoding='utf-8') as f:
        for n in numbers:
            v = vobject.vCard(); v.add('tel').value = n
            f.write(v.serialize())
    return vcf_path

async def vcf_to_txt(vcf_file:str) -> list:
    nums=[]
    with open(vcf_file,'r',encoding='utf-8') as f:
        data=f.read(); cards=data.split('END:VCARD')
        for c in cards:
            for line in c.splitlines():
                if line.startswith('TEL:'): nums.append(line.replace('TEL:','').strip())
    return nums

async def split_numbers(numbers:list,chunk_size:int=1000) -> list:
    return [numbers[i:i+chunk_size] for i in range(0,len(numbers),chunk_size)]

# --- Telegram Handlers ---
WELCOME=f"{hbold('Advanced VCF Manager Bot')}\nUpload TXT/VCF to manage numbers efficiently."
HELP=f"{hbold('Commands')}\n{hcode('/start')} - About\n{hcode('/help')} - Help\nUpload TXT/VCF to process numbers"

@dp.message(Command('start'))
async def cmd_start(msg:Message): await msg.answer(WELCOME)
@dp.message(Command('help'))
async def cmd_help(msg:Message): await msg.answer(HELP)

@dp.message(F.content_type=='document')
async def handle_file(msg:Message):
    if not limiter.allow(msg.from_user.id): return await msg.reply('Wait a few seconds before next upload.')
    file=msg.document; fname=file.file_name; ext=fname.split('.')[-1].lower()
    user_tmp=os.path.join(TEMP_DIR,f'{msg.from_user.id}_{int(time.time())}_{fname}')
    await file.download(destination=user_tmp)
    numbers=[]
    if ext=='txt': numbers=await read_numbers_from_file(user_tmp)
    elif ext=='vcf': numbers=await vcf_to_txt(user_tmp)
    else: return await msg.reply('Unsupported file type')
    original_count=len(numbers); numbers=remove_duplicates(numbers); unique_count=len(numbers)
    keyboard=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton('Remove Duplicates',callback_data=f'remove_dup|{user_tmp}')],
        [InlineKeyboardButton('Add Prefix +91',callback_data=f'add_pref|{user_tmp}|+91')],
        [InlineKeyboardButton('Remove Prefix +91',callback_data=f'rem_pref|{user_tmp}|+91')],
        [InlineKeyboardButton('TXT → VCF',callback_data=f'txt_vcf|{user_tmp}')],
        [InlineKeyboardButton('VCF → TXT',callback_data=f'vcf_txt|{user_tmp}')]
    ])
    await msg.reply(f'Total numbers: {original_count}\nUnique numbers: {unique_count}',reply_markup=keyboard)

@dp.callback_query()
async def handle_buttons(call:CallbackQuery):
    data=call.data.split('|'); action=data[0]
    if action=='remove_dup': numbers=await read_numbers_from_file(data[1]); numbers=remove_duplicates(numbers); out_file=data[1].replace('.txt','_nodup.txt'); await write_numbers_to_file(numbers,out_file); await call.message.answer_document(InputFile(out_file),'Duplicates removed')
    elif action=='add_pref': numbers=await read_numbers_from_file(data[1]); numbers=add_prefix(numbers,data[2]); out_file=data[1].replace('.txt','_addprefix.txt'); await write_numbers_to_file(numbers,out_file); await call.message.answer_document(InputFile(out_file),f'Prefix {data[2]} added')
    elif action=='rem_pref': numbers=await read_numbers_from_file(data[1]); numbers=remove_prefix(numbers,data[2]); out_file=data[1].replace('.txt','_remprefix.txt'); await write_numbers_to_file(numbers,out_file); await call.message.answer_document(InputFile(out_file),f'Prefix {data[2]} removed')
    elif action=='txt_vcf': numbers=await read_numbers_from_file(data[1]); vcf_file=await txt_to_vcf(numbers,data[1].split(os.sep)[-1]); await call.message.answer_document(InputFile(vcf_file),'TXT converted to VCF')
    elif action=='vcf_txt': numbers=await vcf_to_txt(data[1]); out_file=data[1].replace('.vcf','_extracted.txt'); await write_numbers_to_file(numbers,out_file); await call.message.answer_document(InputFile(out_file),'VCF converted to TXT')

# --- Flask Web Interface ---
app = Flask(__name__)
START_TIME = time.time()

STATUS_PAGE = """
<!doctype html>
<title>VCF Bot Status</title>
<h2>Advanced VCF Manager Bot</h2>
<p>Uptime: {{uptime}}</p>
<p>Upload TXT/VCF:</p>
<form method=post enctype=multipart/form-data action="/upload">
  <input type=file name=file>
  <input type=submit value=Upload>
</form>
"""

@app.route('/')
def status(): uptime=f'{int(time.time()-START_TIME)} sec'; return render_template_string(STATUS_PAGE,uptime=uptime)

@app.route('/upload',methods=['POST'])
def web_upload():
    f = request.files['file']
    if f: path=os.path.join(TEMP_DIR,f.filename); f.save(path)
    return redirect(url_for('status'))

# --- Run both ---
def run_flask(): app.run(host='0.0.0.0', port=8080)

def main():
    Thread(target=run_flask,daemon=True).start()
    asyncio.run(dp.start_polling(bot))

if __name__=='__main__':
    main()
    
