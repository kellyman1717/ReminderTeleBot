import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler

# Enable logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Set timezone to UTC+7
TZ_UTC7 = timezone(timedelta(hours=7))

# Read Telegram Bot Token from file
def get_token():
    with open("token.txt", "r") as file:
        return file.read().strip()

# Database setup
def init_db():
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message TEXT,
            remind_time TEXT,
            repeat_interval TEXT,
            repeat_count INTEGER,
            repeat_remaining INTEGER
        )
    """)
    
    # Check and add missing columns if necessary
    cursor.execute("PRAGMA table_info(reminders)")
    columns = {col[1] for col in cursor.fetchall()}  # Extract column names

    if "repeat_count" not in columns:
        cursor.execute("ALTER TABLE reminders ADD COLUMN repeat_count INTEGER DEFAULT 1")
    
    if "repeat_remaining" not in columns:
        cursor.execute("ALTER TABLE reminders ADD COLUMN repeat_remaining INTEGER DEFAULT 1")
    
    conn.commit()
    conn.close()

# Add reminder
def add_reminder(chat_id, message, remind_time, repeat_interval, repeat_count):
    try:
        conn = sqlite3.connect("reminders.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO reminders (chat_id, message, remind_time, repeat_interval, repeat_count, repeat_remaining) VALUES (?, ?, ?, ?, ?, ?)",
                       (chat_id, message, remind_time, repeat_interval, repeat_count, repeat_count))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Gagal menambahkan pengingat: {e}")
        return False

# Get upcoming reminders
def get_reminders():
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, chat_id, message, remind_time, repeat_interval, repeat_remaining FROM reminders")
    reminders = cursor.fetchall()
    conn.close()
    return reminders

# Delete a reminder
def delete_reminder(reminder_id):
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

# Command Handlers
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Halo! Gunakan /add <time> <unit> <message> [repeat_count]. untuk menambahkan pengingat")

async def add(update: Update, context: CallbackContext):
    try:
        time_value = int(context.args[0])
        unit = context.args[1].lower()
        message = " ".join(context.args[2:-1]) if len(context.args) > 3 else " ".join(context.args[2:])
        repeat_count = int(context.args[-1]) if len(context.args) > 3 and context.args[-1].isdigit() else 1
        
        now = datetime.now(TZ_UTC7)
        repeat_interval = None
        
        if unit in ["second", "seconds"]:
            remind_time = now + timedelta(seconds=time_value)
        elif unit in ["minute", "minutes"]:
            remind_time = now + timedelta(minutes=time_value)
        elif unit in ["hour", "hours"]:
            remind_time = now + timedelta(hours=time_value)
        elif unit in ["day", "days"]:
            remind_time = now + timedelta(days=time_value)
        elif unit in ["week", "weeks"]:
            remind_time = now + timedelta(weeks=time_value)
        elif unit in ["month", "months"]:
            remind_time = now + timedelta(days=30 * time_value)
            repeat_interval = "monthly"
        elif unit in ["year", "years"]:
            remind_time = now + timedelta(days=365 * time_value)
            repeat_interval = "yearly"
        elif unit == "forever":
            remind_time = now + timedelta(days=36500)
            repeat_interval = "forever"
        else:
            await update.message.reply_text("Satuan waktu tidak valid. Gunakan seconds, minutes, hours, days, weeks, months, years, atau forever.")
            return
        
        success = add_reminder(update.message.chat_id, message, remind_time.strftime('%Y-%m-%d %H:%M:%S'), repeat_interval, repeat_count)
        if success:
            await update.message.reply_text(f"Pengingat diatur untuk {time_value} {unit}: {message} (Repeats: {repeat_count})")
        else:
            await update.message.reply_text("Gagal menambahkan pengingat. Coba lagi nanti.")
    except (IndexError, ValueError):
        await update.message.reply_text("Gunakan: /add <time> <unit> <message> [repeat_count]")
    except Exception as e:
        logger.error(f"Kesalahan pada perintah add: {e}")
        await update.message.reply_text("Terjadi kesalahan. Coba lagi nanti.")

# Reminder Checker
async def check_reminders(app: Application):
    reminders = get_reminders()
    now = datetime.now(TZ_UTC7)
    for reminder in reminders:
        remind_time = datetime.strptime(reminder[3], '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ_UTC7)
        if remind_time <= now:
            await app.bot.send_message(chat_id=reminder[1], text=f"Reminder: {reminder[2]}")
            if reminder[4] == "monthly":
                new_time = remind_time + timedelta(days=30)
                add_reminder(reminder[1], reminder[2], new_time.strftime('%Y-%m-%d %H:%M:%S'), reminder[4])
            elif reminder[4] == "yearly":
                new_time = remind_time + timedelta(days=365)
                add_reminder(reminder[1], reminder[2], new_time.strftime('%Y-%m-%d %H:%M:%S'), reminder[4])
            elif reminder[4] != "forever":
                delete_reminder(reminder[0])

# Function to safely run async function in scheduler
def run_check_reminders():
    asyncio.run(check_reminders(app))

# Main Function
def main():
    global app
    init_db()
    
    app = Application.builder().token(get_token()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_check_reminders, 'interval', seconds=10)
    scheduler.start()
    
    logger.info("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()
