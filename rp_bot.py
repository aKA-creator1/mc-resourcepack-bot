import os
import re
import json
import time
import logging
import threading
from flask import Flask
from waitress import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ПОЛУЧАЕМ ТОКЕН ==========
TOKEN = 
"8874887697:AAHzVjGC6M5Q5NtZ5FMwjFJ47-MFE422PLs"
if not TOKEN:
    logger.error("❌ Переменная TELEGRAM_TOKEN не установлена!")
    raise ValueError("❌ Переменная TELEGRAM_TOKEN не установлена!")

ADMIN_ID = 6665950252  # ЗАМЕНИТЕ НА СВОЙ ID

# ========== РАБОТА С ДАННЫМИ ==========
DATA_FILE = "packs_data.json"
LOCK_FILE = "packs_data.lock"

def load_packs():
    """Безопасная загрузка данных с обработкой ошибок"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                else:
                    logger.warning("⚠️ Данные повреждены, создаём новый словарь")
                    return {}
        return {}
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"❌ Ошибка загрузки данных: {e}")
        return {}

def save_packs(packs):
    """Безопасное сохранение данных с блокировкой"""
    try:
        # Создаём блокировку для предотвращения конфликтов
        with open(LOCK_FILE, "w") as lock:
            lock.write(str(os.getpid()))
        
        # Сохраняем данные
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(packs, f, indent=2, ensure_ascii=False)
        
        # Удаляем блокировку
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения данных: {e}")
        return False

# Загружаем данные
RESOURCE_PACKS = load_packs()
if not RESOURCE_PACKS:
    RESOURCE_PACKS = {
        "1.20.4": [],
        "1.19.2": [],
        "1.18.2": [],
    }
    save_packs(RESOURCE_PACKS)

user_versions = {}

# ========== СОЗДАЁМ БОТА ==========
app_bot = Application.builder().token(TOKEN).build()

# ========== ОБРАБОТЧИКИ ТЕЛЕГРАМ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню с выбором версии"""
    try:
        keyboard = [[InlineKeyboardButton(v, callback_data=f"ver_{v}")] for v in RESOURCE_PACKS.keys()]
        await update.message.reply_text(
            "🎮 Выберите версию Minecraft:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в start: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка, попробуйте позже")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    try:
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
            await query.edit_message_text(
                f"📦 {version}:\n{pack_list}\n\n💡 Введите #01:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif data == "back":
            keyboard = [[InlineKeyboardButton(v, callback_data=f"ver_{v}")] for v in RESOURCE_PACKS.keys()]
            await query.edit_message_text(
                "🎮 Выберите версию:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"❌ Ошибка в button_handler: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода номера ресурспака"""
    try:
        user_id = update.message.from_user.id
        if user_id not in user_versions:
            await update.message.reply_text("❌ Сначала /start")
            return
        
        version = user_versions[user_id]
        packs = RESOURCE_PACKS.get(version, [])
        if not packs:
            await update.message.reply_text("❌ Ресурспаков в этой версии нет")
            return
        
        match = re.search(r'#?(\d+)', update.message.text.strip())
        if not match:
            await update.message.reply_text("❌ Введите номер, например: #01 или 01")
            return
        
        number = int(match.group(1))
        if number < 1 or number > len(packs):
            await update.message.reply_text(f"❌ Доступны: 01 - {str(len(packs)).zfill(2)}")
            return
        
        pack = packs[number - 1]
        await update.message.reply_document(
            document=pack["file_id"],
            caption=f"✅ {pack['name']} ({version})"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_text: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка, попробуйте позже")

async def add_pack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление ресурспака (только для админа)"""
    try:
        if update.message.from_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав!")
            return
        
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "/addpack [версия] [название]\n"
                "Пример: /addpack 1.20.4 Faithful"
            )
            return
        
        version = args[0]
        name = " ".join(args[1:])
        context.user_data['pending_pack'] = {"version": version, "name": name}
        await update.message.reply_text(f"📤 Отправьте ZIP для:\n{version} - {name}")
    except Exception as e:
        logger.error(f"❌ Ошибка в add_pack: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка загруженных файлов"""
    try:
        doc = update.message.document
        
        if 'pending_pack' in context.user_data:
            data = context.user_data['pending_pack']
            version = data['version']
            name = data['name']
            
            if version not in RESOURCE_PACKS:
                RESOURCE_PACKS[version] = []
            
            RESOURCE_PACKS[version].append({"name": name, "file_id": doc.file_id})
            
            if save_packs(RESOURCE_PACKS):
                await update.message.reply_text(f"✅ Добавлен: {name} ({version})")
            else:
                await update.message.reply_text("⚠️ Ошибка сохранения, попробуйте снова")
            
            del context.user_data['pending_pack']
        else:
            await update.message.reply_text(f"✅ file_id:\n`{doc.file_id}`")
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_document: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка")

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
    try:
        port = int(os.getenv("PORT", 10000))
        serve(flask_app, host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"❌ Ошибка веб-сервера: {e}")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    try:
        # Запускаем Flask в отдельном потоке
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        logger.info("✅ Бот запущен!")
        app_bot.run_polling()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
