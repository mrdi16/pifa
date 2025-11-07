# config.py
import os

# Настройки бота
BOT_TOKEN = "8091583677:AAGx-bgSQWculaPipu9T48hM_4fcGVD3hZs"
BOT_USERNAME = "pythagoras_cube_bot"

# Базы данных и файлы
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'pythagoras_cube.db')
REFERRAL_LINKS_FILE = 'referral_links.json'
USER_STATS_FILE = 'user_stats.json'

# Лимиты
MAX_CALCULATIONS = 5

# Цены
SUBSCRIPTION_PRICE = 199
SUBSCRIPTION_PRICE_TELEGRAM = 199

# Реквизиты для оплаты
TBANK_CARD_NUMBER = "2200700888201950"
TBANK_PHONE = "+79222020960"

# Контакты
YOUR_TELEGRAM = "@HelpPifaBot"
ADMIN_IDS = [5917286646, 1698403624]

# Платежи
TELEGRAM_PAYMENT_LINK = "https://t.me/tribute/app?startapp=pm6X"