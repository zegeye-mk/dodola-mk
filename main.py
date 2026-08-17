import datetime
import logging
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)

# --- RENDER HEALTH CHECK SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# --- CONFIGURATION ---
BOT_TOKEN = "8129704477:AAEoX1nI0QmpiHfK0VXrinG-yWyMn9OZVLM"
ADMIN_ID = 829583750

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("association.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            is_executive INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            user_id INTEGER,
            date TEXT,
            status TEXT,
            PRIMARY KEY (user_id, date)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            user_id INTEGER,
            month_year TEXT,
            payment_type TEXT,
            amount REAL,
            PRIMARY KEY (user_id, month_year, payment_type)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect("association.db")

def get_meeting_link():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'meeting_link'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "https://t.me"

def set_meeting_link(link: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('meeting_link', ?)", (link,))
    conn.commit()
    conn.close()

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, full_name) VALUES (?, ?)",
        (user.id, user.full_name or user.first_name)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"ሰላም {user.first_name}! እንኳን ወደ የዶዶላ ወረዳ ማዕከል ማህበረ ቅዱሳን ቦት በሰላም መጡ።\n\n"
        "📌 **የአድሚን ትዕዛዞች:**\n"
        "/set_link <ሊንክ> - አዲሱን የስብሰባ ሊንክ ለመመዝገብ\n"
        "/send_link - አሁኑኑ የስብሰባውን ሊንክ ለሁሉም ለመላክ\n"
        "/make_exec <User_ID> - ስራ አስፈፃሚ ለማድረግ\n"
        "/attendance - የአርብ አቴንዳንስ ለመያዝ\n"
        "/pay_monthly <User_ID> <መጠን> - የወርሃዊ ክፍያ ለመመዝገብ\n"
        "/pay_social <User_ID> <መጠን> - የማህበራዊ ክፍያ ለመመዝገብ\n"
        "/broadcast <መልእክት> - ለሁሉም አባላት ማስታወቂያ ለመላክ"
    )

async def set_link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("እባክዎን ሊንኩን ያስገቡ። ምሳሌ፡\n/set_link https://zoom.us/j/12345678")
        return
    
    new_link = context.args[0]
    set_meeting_link(new_link)
    await update.message.reply_text(f"✅ የስብሰባው ሊንክ በተሳካ ሁኔታ ተመዝግቧል፡\n{new_link}")

async def send_link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    link = get_meeting_link()
    keyboard = [[InlineKeyboardButton("🔗 ወደ ስብሰባው ግባ (Join)", url=link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    count = 0
    msg_text = "📢 **የስብሰባ ማሳሰቢያ:**\n\nየስብሰባ ሰዓት ስለደረሰ ከታች ያለውን ቁልፍ ተጭነው መግባት ይችላሉ።"
    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=msg_text, reply_markup=reply_markup, parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"የስብሰባው ሊንክ ለ {count} አባላት ተልኳል።")

async def make_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_executive = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"ተጠቃሚ {target_id} በተሳካ ሁኔታ ስራ አስፈፃሚ ሆኖ ተመዝግቧል።")
    except Exception:
        await update.message.reply_text("እባክዎን ትክክለኛ የUser ID ያስገቡ። ምሳሌ፡ /make_exec 123456789")

async def attendance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, full_name FROM users")
    users = cursor.fetchall()
    conn.close()

    if not users:
        await update.message.reply_text("ምንም የተመዘገበ አባል የለም።")
        return

    keyboard = []
    for u in users:
        keyboard.append([InlineKeyboardButton(f"👤 {u[1]}", callback_data=f"att_user_{u[0]}")])

    await update.message.reply_text("እባክዎን አቴንዳንስ መያዝ የሚፈልጉትን አባል ይምረጡ፡", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("att_user_"):
        user_id = int(data.split("_")[2])
        keyboard = [
            [
                InlineKeyboardButton("✔️ Present (ተገኝቷል)", callback_data=f"set_att_{user_id}_PRESENT"),
                InlineKeyboardButton("❌ Absent (ቀርቷል)", callback_data=f"set_att_{user_id}_ABSENT"),
            ],
            [InlineKeyboardButton("🅿️ Permission (በፍቃድ)", callback_data=f"set_att_{user_id}_PERMISSION")],
        ]
        await query.edit_message_text("እባክዎን የአባሉን የስብሰባ ሁኔታ ይምረጡ፡", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("set_att_"):
        _, _, user_id_str, status = data.split("_")
        user_id = int(user_id_str)
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO attendance (user_id, date, status) VALUES (?, ?, ?)",
            (user_id, today_str, status)
        )
        conn.commit()
        conn.close()

        status_icon = "✔️ Present" if status == "PRESENT" else "❌ Absent" if status == "ABSENT" else "🅿️ Permission"
        await query.edit_message_text(f"አቴንዳንስ በተሳካ ሁኔታ ተመዝግቧል፡ {status_icon}")

        if status == "ABSENT":
            await check_consecutive_absences(user_id, context)

async def check_consecutive_absences(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM attendance WHERE user_id = ? ORDER BY date DESC LIMIT 2",
        (user_id,)
    )
    records = cursor.fetchall()
    conn.close()

    if len(records) >= 2 and all(r[0] == "ABSENT" for r in records):
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="⚠️ **ማስጠንቀቂያ:** በተከታታይ ሁለትና ከዚያ በላይ የአርብ ስብሰባዎች ላይ አልተገኙም። እባክዎን በቀጣይ ስብሰባዎች ላይ በሰዓቱ ይገኙ።"
            )
        except Exception:
            pass

async def pay_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        month_year = datetime.datetime.now().strftime("%Y-%m")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO payments VALUES (?, ?, 'MONTHLY', ?)",
            (user_id, month_year, amount)
        )
        conn.commit()
        conn.close()
        await update.message.reply_text(f"የአባል ID {user_id} የወርሃዊ አስተዋፅኦ {amount} ብር ተመዝግቧል።")
    except Exception:
        await update.message.reply_text("አጠቃቀም፡ /pay_monthly <User_ID> <መጠን> (ምሳሌ፡ /pay_monthly 829583750 100)")

async def pay_social(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        month_year = datetime.datetime.now().strftime("%Y-%m")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO payments VALUES (?, ?, 'SOCIAL', ?)",
            (user_id, month_year, amount)
        )
        conn.commit()
        conn.close()
        await update.message.reply_text(f"የአባል ID {user_id} የማህበራዊ አስተዋፅኦ {amount} ብር ተመዝግቧል።")
    except Exception:
        await update.message.reply_text("አጠቃቀም፡ /pay_social <User_ID> <መጠን> (ምሳሌ፡ /pay_social 829583750 50)")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("አጠቃቀም፡ /broadcast <መልእክት>")
        return

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    count = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=f"📢 **ማስታወቂያ:**\n\n{msg}", parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"መልእክቱ ለ {count} አባላት ተልኳል።")

# --- SCHEDULED JOBS ---
async def wednesday_exec_job(context: ContextTypes.DEFAULT_TYPE):
    link = get_meeting_link()
    keyboard = [[InlineKeyboardButton("🔗 ወደ ስብሰባው ግባ (Join)", url=link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_executive = 1")
    execs = cursor.fetchall()
    conn.close()

    msg = "📢 **የስራ አስፈፃሚ ማሳሰቢያ:**\n\nከአምስት ደቂቃ በኋላ ማታ 3:00 ስብሰባ ይጀመራል። ከታች ያለውን ቁልፍ ተጭነው ይግቡ።"
    for u in execs:
        try:
            await context.bot.send_message(chat_id=u[0], text=msg, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception:
            pass

async def sunday_exec_job(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_executive = 1")
    execs = cursor.fetchall()
    conn.close()

    msg = "📢 **የስራ አስፈፃሚ ማሳሰቢያ:**\n\nከጠዋቱ 1:40 ስብሰባ ስላለ በፅህፈት ቤት ይገኙ።"
    for u in execs:
        try:
            await context.bot.send_message(chat_id=u[0], text=msg)
        except Exception:
            pass

async def friday_all_job(context: ContextTypes.DEFAULT_TYPE):
    link = get_meeting_link()
    keyboard = [[InlineKeyboardButton("🔗 ወደ ስብሰባው ግባ (Join)", url=link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    msg = "📢 **የአባላት ማሳሰቢያ:**\n\nዛሬ አርብ ከቀኑ 11:30 ጀምሮ የስብሰባ ሰዓት ስለሆነ ከታች ያለውን ቁልፍ ተጭነው ይግቡ።"
    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=msg, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception:
            pass

async def monthly_payment_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    msg = "💳 **የክፍያ ማሳሰቢያ:**\n\nእባክዎን የወርሃዊ እና የማህበራዊ አስተዋፅኦ ክፍያዎን በሰዓቱ እንዲከፍሉ እናሳስባለን።"
    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=msg)
        except Exception:
            pass

def main():
    # Render የጤንነት ፍተሻ (Health Check) ሰርቨርን ከበስተጀርባ ማስጀመር
    Thread(target=run_health_check_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_link", set_link_cmd))
    app.add_handler(CommandHandler("send_link", send_link_cmd))
    app.add_handler(CommandHandler("make_exec", make_exec))
    app.add_handler(CommandHandler("attendance", attendance_menu))
    app.add_handler(CommandHandler("pay_monthly", pay_monthly))
    app.add_handler(CommandHandler("pay_social", pay_social))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button_handler))

    job_queue = app.job_queue
    job_queue.run_daily(wednesday_exec_job, time=datetime.time(hour=20, minute=55, second=0), days=(2,))
    job_queue.run_daily(sunday_exec_job, time=datetime.time(hour=7, minute=35, second=0), days=(6,))
    job_queue.run_daily(friday_all_job, time=datetime.time(hour=17, minute=25, second=0), days=(4,))
    job_queue.run_monthly(monthly_payment_reminder_job, time=datetime.time(hour=9, minute=0, second=0), day=1)

    app.run_polling()

if __name__ == "__main__":
    main()
