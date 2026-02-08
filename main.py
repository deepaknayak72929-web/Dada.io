import os
import logging
import requests
import random
import string
import asyncio
import time
import math
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- ENVIRONMENT VARIABLES (RAILWAY) ---
BOT_TOKEN = os.environ.get("8516508205:AAFTFsbJczCYqJwJcA7cNhPPGBqiBSd8UMQ")       # Set this in Railway Env Variables
ADMIN_ID = int(os.environ.get("6582969543"))    # Set this in Railway Env Variables

# --- CONFIGURATION ---
API_BASE = "https://api.cavira.vip"

# Allowed Users
ALLOWED_USERS = {6582969543}

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- GLOBAL DATA STORE ---
accounts_queue = []
active_sessions = {}
monitored_numbers = {}

# --- HELPER FUNCTIONS ---
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

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Access Denied. Contact Admin.")
        return

    keyboard = [
        [KeyboardButton("📂 Upload Account File"), KeyboardButton("📊 Status")],
        [KeyboardButton("🆔 Add User Access")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_msg = (
        "👋 Welcome, Admin!\n"
        "System Status: Online\n"
        "Cycle Mode: Auto-Login (Every 5 mins)\n"
        "Monitoring Limit: 50 Hours per account\n"
        "Upload account file or check Status."
    )
    
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
    
    if not context.bot_data.get('monitor_started'):
        context.bot_data['monitor_started'] = True
        asyncio.create_task(monitor_accounts_loop(context.bot))

# --- STATUS & PAGINATION HANDLER ---
async def show_status_page(update: Update, page=0):
    items_per_page = 10
    all_items = list(monitored_numbers.items())
    total_items = len(all_items)
    total_pages = max(1, math.ceil(total_items / items_per_page))
    
    if total_items == 0:
        text = "No numbers are currently being monitored."
        if update.callback_query:
            await update.callback_query.message.edit_text(text)
        else:
            await update.message.reply_text(text)
        return

    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = all_items[start_idx:end_idx]
    
    status_text = f"Live Monitoring Status (Page {page + 1}/{total_pages})\n\n"
    current_time = time.time()
    
    for i, (phone, info) in enumerate(page_items, start=start_idx + 1):
        duration_sec = current_time - info.get('linked_at', current_time)
        duration_str = format_duration(duration_sec)
        email = info.get('email', 'Unknown')
        status_text += f"{i}.) {email} | {phone} | {duration_str}\n"
        
    buttons = []
    if page > 0: buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"sts_prev_{page}"))
    buttons.append(InlineKeyboardButton("❌ Cancel", callback_data="sts_cancel"))
    if end_idx < total_items: buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"sts_next_{page}"))
        
    reply_markup = InlineKeyboardMarkup([buttons])
    if update.callback_query:
        await update.callback_query.message.edit_text(status_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(status_text, reply_markup=reply_markup)

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

# --- MESSAGE HANDLER ---
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
            await update.message.reply_text(f"User Added: {new_id}")
        except:
            await update.message.reply_text("Error: Use /add 123456")
        return

    if text == "📂 Upload Account File":
        await update.message.reply_text("Upload .txt file with format:\nEmail\nPassword\nEmail\nPassword")
        return

    if context.user_data.get('waiting_for_phone'):
        await process_phone_submission(update, context, text.strip())

# --- MAIN ---
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
