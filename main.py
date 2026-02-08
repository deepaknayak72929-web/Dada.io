# ------------------------- IMPORTS -------------------------
import logging
import asyncio
import time
import math
import string
import random
import os
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ------------------------- CONFIGURATION -------------------------
BOT_TOKEN = os.environ.get("8516508205:AAFTFsbJczCYqJwJcA7cNhPPGBqiBSd8UMQ")
ADMIN_ID = int(os.environ.get("6582969543"))
API_BASE = "https://api.cavira.vip"

# Allowed Users
ALLOWED_USERS = {6582969543}

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------- GLOBAL DATA -------------------------
accounts_queue = []
active_sessions = {} 
monitored_numbers = {}

# ------------------------- HELPER FUNCTIONS -------------------------
def generate_uuid(length=17):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def get_headers(token=""):
    headers = {
        "Host": "api.cavira.vip",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36",
        "Origin": "https://cavira.vip",
        "Referer": "https://cavira.vip/",
        "h5-platform": "cavira.vip",
        "x-token": token if token else ""
    }
    return headers

def is_allowed(user_id):
    return user_id in ALLOWED_USERS

def format_duration(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{int(h)}h {int(m)}m"

# ------------------------- BOT HANDLERS -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ **Access Denied.** Contact Admin.", parse_mode="Markdown")
        return

    keyboard = [
        [KeyboardButton("📂 Upload Account File"), KeyboardButton("📊 Status")],
        [KeyboardButton("🆔 Add User Access")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_msg = (
        "👋 **Welcome, Admin!**\n\n"
        "🤖 **System Status:** `Online`\n"
        "🔄 **Cycle Mode:** `Auto-Login (Every 5 mins)`\n"
        "⏱️ **Monitoring Limit:** `50 Hours` per account\n\n"
        "📂 *Upload account file or check Status.*"
    )
    
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode="Markdown")
    
    if not context.bot_data.get('monitor_started'):
        context.bot_data['monitor_started'] = True
        asyncio.create_task(monitor_accounts_loop(context.bot))

# ------------------------- STATUS HANDLER -------------------------
async def show_status_page(update: Update, page=0):
    items_per_page = 10
    all_items = list(monitored_numbers.items())
    total_items = len(all_items)
    total_pages = max(1, math.ceil(total_items / items_per_page))
    
    if total_items == 0:
        text = "📭 **No numbers are currently being monitored.**"
        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, parse_mode="Markdown")
        return

    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = all_items[start_idx:end_idx]
    
    status_text = f"📊 **Live Monitoring Status (Page {page + 1}/{total_pages})**\n\n"
    current_time = time.time()
    
    for i, (phone, info) in enumerate(page_items, start=start_idx + 1):
        duration_sec = current_time - info.get('linked_at', current_time)
        duration_str = format_duration(duration_sec)
        email = info.get('email', 'Unknown')
        status_text += f"`{i}.)` {email} | `{phone}` | `{duration_str}`\n"
        
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"sts_prev_{page}"))
    buttons.append(InlineKeyboardButton("❌ Cancel", callback_data="sts_cancel"))
    if end_idx < total_items:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"sts_next_{page}"))
        
    reply_markup = InlineKeyboardMarkup([buttons])
    if update.callback_query:
        await update.callback_query.message.edit_text(status_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode="Markdown")

async def status_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "sts_cancel":
        await query.message.delete()
        return
    if data.startswith("sts_next_"):
        current_page = int(data.split("_")[2])
        await show_status_page(update, page=current_page + 1)
    elif data.startswith("sts_prev_"):
        current_page = int(data.split("_")[2])
        await show_status_page(update, page=current_page - 1)

# ------------------------- MESSAGE HANDLER -------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if not is_allowed(user_id): return

    if text == "📊 Status":
        await show_status_page(update, page=0)
        return

    if text.startswith("/add "):
        try:
            new_id = int(text.split()[1])
            ALLOWED_USERS.add(new_id)
            await update.message.reply_text(f"✅ **User Added:** `{new_id}`", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ **Error:** Use format `/add 123456`", parse_mode="Markdown")
        return

    if text == "📂 Upload Account File":
        await update.message.reply_text(
            "📂 **Upload Accounts**\n\n"
            "Please send the `.txt` file containing accounts.\n"
            "Format:\n`Email`\n`Password`\n`Email`\n`Password`",
            parse_mode="Markdown"
        )
        return

    if context.user_data.get('waiting_for_phone'):
        await process_phone_submission(update, context, text.strip())
        return

# ------------------------- DOCUMENT HANDLER -------------------------
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id): return

    file = await update.message.document.get_file()
    content = await file.download_as_bytearray()
    lines = content.decode('utf-8').splitlines()

    global accounts_queue
    accounts_queue = []
    
    temp_email = None
    count = 0
    for line in lines:
        line = line.strip()
        if not line: continue
        if temp_email is None:
            temp_email = line
        else:
            accounts_queue.append({'email': temp_email, 'password': line})
            temp_email = None
            count += 1
            
    await update.message.reply_text(
        f"✅ **File Loaded Successfully!**\n\n"
        f"📊 **Total Accounts:** `{count}`\n"
        f"🚀 *Starting the process now...*",
        parse_mode="Markdown"
    )
    await process_next_account(update, context)

# ------------------------- ACCOUNT PROCESSING -------------------------
async def process_next_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global accounts_queue, active_sessions
    
    if not accounts_queue:
        await update.message.reply_text("🏁 **All Tasks Completed!** No more accounts in queue.", parse_mode="Markdown")
        return

    account = accounts_queue.pop(0)
    email = account['email']
    password = account['password']
    
    msg = await update.message.reply_text(f"🔄 **Logging in...**\n📧 `{email}`", parse_mode="Markdown")
    
    try:
        url = f"{API_BASE}/h5/taskBase/login"
        payload = {"email": email, "password": password}
        resp = requests.post(url, json=payload, headers=get_headers())
        data = resp.json()
        
        if data.get("code") == 0:
            token = data["data"]["token"]
            
            active_sessions[email] = {
                'password': password,
                'token': token,
                'start_time': time.time()
            }
            context.user_data['current_email'] = email 
            context.user_data['waiting_for_phone'] = True
            
            await msg.edit_text(
                f"✅ **Login Successful!**\n\n"
                f"👤 **Account:** `{email}`\n"
                f"📱 *Please enter the phone number to link:*",
                parse_mode="Markdown"
            )
        else:
            await msg.edit_text(f"❌ **Login Failed!**\nReason: `{data.get('msg')}`\n\n⏭️ *Skipping to next account...*", parse_mode="Markdown")
            await process_next_account(update, context)
            
    except Exception as e:
        await update.message.reply_text(f"⚠️ **Error:** `{e}`", parse_mode="Markdown")
        await process_next_account(update, context)

# ------------------------- PHONE SUBMISSION -------------------------
async def process_phone_submission(update: Update, context: ContextTypes.DEFAULT_TYPE, phone):
    email = context.user_data.get('current_email')
    token = active_sessions[email]['token']
    uuid = generate_uuid()
    
    msg = await update.message.reply_text("🔄 **Requesting Verification Code...**", parse_mode="Markdown")
    
    try:
        url = f"{API_BASE}/h5/taskUser/phoneCode"
        payload = {"uuid": uuid, "phone": phone, "type": 2}
        resp = requests.post(url, json=payload, headers=get_headers(token))
        data = resp.json()
        
        if data.get("code") == 0:
            code = data["data"]["phone_code"]
            await msg.edit_text(
                f"📟 **VERIFICATION CODE RECEIVED**\n\n"
                f"🔢 **Code:** `{code}`\n"
                f"📞 **Phone:** `{phone}`\n\n"
                f"⏳ *Waiting for you to scan/confirm...*",
                parse_mode="Markdown"
            )
            asyncio.create_task(check_link_success(update, context, token, uuid, email))
            context.user_data['waiting_for_phone'] = False
        else:
            await msg.edit_text(f"❌ **Failed:** `{data.get('msg')}`\n\n*Please enter a valid number again:*", parse_mode="Markdown")
            
    except Exception as e:
        await update.message.reply_text(f"⚠️ **Error:** `{e}`", parse_mode="Markdown")

# ------------------------- LINK CHECK -------------------------
async def check_link_success(update: Update, context: ContextTypes.DEFAULT_TYPE, token, uuid, email):
    for i in range(60): 
        await asyncio.sleep(5)
        try:
            url = f"{API_BASE}/h5/taskUser/scanCodeResult"
            resp = requests.post(url, json={'uuid': uuid}, headers=get_headers(token))
            data = resp.json()
            
            if data.get("code") == 0 and data.get("data"):
                number = str(data['data'])
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        f"🎉 **LINKING SUCCESSFUL!**\n\n"
                        f"✅ **Number:** `{number}`\n"
                        f"📧 **Account:** `{email}`\n\n"
                        f"🔄 *Switching to next account in queue...*"
                    ),
                    parse_mode="Markdown"
                )
                
                monitored_numbers[number] = {
                    'email': email,
                    'notified_24': False,
                    'notified_48': False,
                    'linked_at': time.time()
                }
                
                await process_next_account(update, context)
                return
        except: pass
        
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="⚠️ **Timeout!** Linking took too long.\n⏭️ *Moving to next account...*",
        parse_mode="Markdown"
    )
    await process_next_account(update, context)

# ------------------------- MONITORING LOOP -------------------------
async def monitor_accounts_loop(bot):
    while True:
        try:
            await asyncio.sleep(300) # 5 Minutes
            
            if not active_sessions:
                continue

            current_time = time.time()
            TIME_LIMIT = 50 * 3600 # 50 Hours

            for email in list(active_sessions.keys()):
                session = active_sessions[email]
                password = session['password']
                start_time = session.get('start_time', current_time)
                
                if current_time - start_time > TIME_LIMIT:
                    await bot.send_message(ADMIN_ID, f"🛑 **50H Limit:** Monitoring ended for `{email}`", parse_mode="Markdown")
                    del active_sessions[email]
                    
                    numbers_to_remove = [p for p, i in monitored_numbers.items() if i['email'] == email]
                    for n in numbers_to_remove:
                        del monitored_numbers[n]
                    continue

                try:
                    login_resp = requests.post(f"{API_BASE}/h5/taskBase/login", 
                                             json={"email": email, "password": password}, 
                                             headers=get_headers())
                    login_data = login_resp.json()
                    
                    if login_data.get("code") == 0:
                        new_token = login_data["data"]["token"]
                        active_sessions[email]['token'] = new_token 
                        
                        list_resp = requests.get(f"{API_BASE}/h5/taskUser/bindWsList", 
                                               headers=get_headers(new_token))
                        list_data = list_resp.json()
                        
                        if list_data.get("code") == 0:
                            online_list = list_data.get("data", [])
                            active_phones_now = [str(item['phone']) for item in online_list]
                            
                            for mon_phone, info in list(monitored_numbers.items()):
                                if info['email'] == email and mon_phone not in active_phones_now:
                                    await bot.send_message(
                                        chat_id=ADMIN_ID,
                                        text=f"🚨 **REMOVED!**\n📞 `{mon_phone}`\n📧 `{email}`",
                                        parse_mode="Markdown"
                                    )
                                    del monitored_numbers[mon_phone]
                            
                            for item in online_list:
                                phone = str(item['phone'])
                                on_time = item.get('online_time', 0)
                                
                                if phone in monitored_numbers:
                                    if on_time >= 86400 and not monitored_numbers[phone]['notified_24']:
                                        await bot.send_message(ADMIN_ID, f"✅ **24 HOURS**\n📞 `{phone}`\n📧 `{email}`", parse_mode="Markdown")
                                        monitored_numbers[phone]['notified_24'] = True
                                    if on_time >= 172800 and not monitored_numbers[phone]['notified_48']:
                                        await bot.send_message(ADMIN_ID, f"🔥 **48 HOURS**\n📞 `{phone}`\n📧 `{email}`", parse_mode="Markdown")
                                        monitored_numbers[phone]['notified_48'] = True
                                        
                    else:
                        del active_sessions[email]

                except Exception as e:
                    logger.error(f"Monitor Error {email}: {e}")

        except Exception as e:
            logger.error(f"Loop Error: {e}")

# ------------------------- MAIN -------------------------
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.MimeType("text/plain"), handle_document))
    application.add_handler(CallbackQueryHandler(status_callback_handler))
    application.add_handler(MessageHandler(filters.TEXT, handle_message))
    print("Bot Started...")
    application.run_polling()

if __name__ == "__main__":
    main()