import os
import re
import json
import threading
from flask import Flask
from waitress import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
TOKEN = os.getenv("8874887697:AAGK0BTfJS54vZzQU0_egeYpSla87jbLiE4")  # Токен из переменных окружения Render
if not TOKEN:
    raise ValueError("❌ Переменная TELEGRAM_TOKEN не установлена!")

ADMIN_ID = 6665950252  # Ваш Telegram ID

# ========== РАБОТА С ДАННЫМИ ==========
DATA_FILE = "packs_data.json"

def load_packs():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_packs(packs):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(packs, f, indent=2, ensure_ascii=False)

RESOURCE_PACKS = load_packs()
if not RESOURCE_PACKS:
    RESOURCE_PACKS = {
        "1.20.4": [],
        "1.19.2": [],
        "1.18.2": [],
    }

user_versions = {}

# ========== СОЗДАЁМ БОТА ==========
app_bot = Application.builder().token(TOKEN).build()

# ========== ОБРАБОТЧИКИ ТЕЛЕГРАМ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(v, callback_data=f"ver_{v}")] for v in RESOURCE_PACKS.keys()]
    await update.message.reply_text("🎮 Выберите версию Minecraft:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("ver_"):
        version = data[4:]
        packs = RESOURCE_PACKS.get(version, [])
        if not packs:
            await query.edit_message_text("❌ Ресурспаков нет. Добавьте через /addpack")
            return
        user_versions[user_id] = version
        pack_list = "\n".join([f"#{str(i+1).zfill(2)} - {p['name']}" for i, p in enumerate(packs)])
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
        await query.edit_message_text(f"📦 {version}:\n{pack_list}\n\n💡 Введите #01:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "back":
        keyboard = [[InlineKeyboardButton(v, callback_data=f"ver_{v}")] for v in RESOURCE_PACKS.keys()]
        await query.edit_message_text("🎮 Выберите версию:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_versions:
        await update.message.reply_text("❌ Сначала /start")
        return
    version = user_versions[user_id]
    packs = RESOURCE_PACKS.get(version, [])
    match = re.search(r'#?(\d+)', update.message.text.strip())
    if not match:
        await update.message.reply_text("❌ Введите #01")
        return
    number = int(match.group(1))
    if number < 1 or number > len(packs):
        await update.message.reply_text(f"❌ Доступны: 01 - {str(len(packs)).zfill(2)}")
        return
    pack = packs[number - 1]
    await update.message.reply_document(document=pack["file_id"], caption=f"✅ {pack['name']} ({version})")

async def add_pack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав!")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("/addpack [версия] [название]\nПример: /addpack 1.20.4 Faithful")
        return
    version = args[0]
    name = " ".join(args[1:])
    context.user_data['pending_pack'] = {"version": version, "name": name}
    await update.message.reply_text(f"📤 Отправьте ZIP для:\n{version} - {name}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if 'pending_pack' in context.user_data:
        data = context.user_data['pending_pack']
        version = data['version']
        name = data['name']
        if version not in RESOURCE_PACKS:
            RESOURCE_PACKS[version] = []
        RESOURCE_PACKS[version].append({"name": name, "file_id": doc.file_id})
        save_packs(RESOURCE_PACKS)
        await update.message.reply_text(f"✅ Добавлен: {name} ({version})")
        del context.user_data['pending_pack']
    else:
        await update.message.reply_text(f"✅ file_id:\n`{doc.file_id}`")

# ========== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ==========
app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(CommandHandler("addpack", add_pack))
app_bot.add_handler(CallbackQueryHandler(button_handler))
app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_document))

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "🤖 Бот работает!", 200

@flask_app.route("/health")
def health():
    return "OK", 200

def run_flask():
    port = int(os.getenv("PORT", 10000))
    serve(flask_app, host="0.0.0.0", port=port)

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()
    
    print("✅ Бот запущен!")
    app_bot.run_polling()