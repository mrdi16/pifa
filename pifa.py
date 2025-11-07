import sqlite3
import random
import asyncio
import json
import secrets
import string
import os
import time
from collections import defaultdict
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from functools import wraps
from PIL import Image, ImageDraw, ImageFont 

from config import (
    BOT_TOKEN, 
    BOT_USERNAME,
    REFERRAL_LINKS_FILE,
    MAX_CALCULATIONS,
    USER_STATS_FILE,
    SUBSCRIPTION_PRICE,
    SUBSCRIPTION_PRICE_TELEGRAM,
    TBANK_CARD_NUMBER,
    TBANK_PHONE,
    YOUR_TELEGRAM,
    ADMIN_IDS,
    BASE_DIR,
    DB_NAME,
    TELEGRAM_PAYMENT_LINK
)
print(f"📁 Путь к базе данных: {DB_NAME}")

if os.path.exists(DB_NAME):
    print(f"✅ База данных найдена: {DB_NAME}")
    print(f"📊 Размер базы: {os.path.getsize(DB_NAME)} байт")
else:
    print(f"🆕 База данных будет создана: {DB_NAME}")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    print("🔄 Инициализация базы данных...")
    
    print("🆕 Создаем таблицы...")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            birth_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Таблица users создана/проверена")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            is_active BOOLEAN DEFAULT FALSE,
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Таблица subscriptions создана/проверена")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            amount INTEGER NOT NULL,
            payment_method TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            admin_id INTEGER
        )
    ''')
    print("✅ Таблица payments создана/проверена")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calculation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            calculation_type TEXT NOT NULL,
            name TEXT,
            birth_date TEXT,
            result_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            psychomatrix_json TEXT
        )
    ''')
    print("✅ Таблица calculation_history создана/проверена")
    
    print("🔍 Проверяем структуру таблиц...")
    
    try:
        cursor.execute("PRAGMA table_info(calculation_history)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'psychomatrix_json' not in columns:
            print("🆕 Добавляем поле psychomatrix_json в calculation_history...")
            cursor.execute('''
                ALTER TABLE calculation_history 
                ADD COLUMN psychomatrix_json TEXT
            ''')
            print("✅ Колонка psychomatrix_json добавлена")
        else:
            print("✅ Колонка psychomatrix_json уже существует")
            
    except Exception as e:
        print(f"⚠️ Ошибка при проверке структуры calculation_history: {e}")
    
    conn.commit()
    
    print("📊 Проверяем статистику базы...")
    
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM subscriptions")
        subs_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM payments")
        payments_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM calculation_history")
        history_count = cursor.fetchone()[0]
        
        print(f"📊 Текущая статистика базы:")
        print(f"   👥 Пользователей: {users_count}")
        print(f"   💎 Подписок: {subs_count}")
        print(f"   💰 Платежей: {payments_count}")
        print(f"   📊 Записей истории: {history_count}")
        
    except Exception as e:
        print(f"⚠️ Ошибка при получении статистики: {e}")
    
    conn.close()
    print("✅ Инициализация базы данных завершена")

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        
        if user.id not in ADMIN_IDS:
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.answer("❌ Эта команда только для администраторов", show_alert=True)
            else:
                await update.message.reply_text("❌ Эта команда только для администраторов")
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapper
    
class PsychomatrixVisualizer:
    def __init__(self):
        self.cell_size = 120
        self.border = 30
        self.image_size = self.cell_size * 3 + self.border * 2
        
    def create_psychomatrix_image(self, psychomatrix, name, birth_date):
        try:
            img = Image.new('RGB', (self.image_size, self.image_size), 'white')
            draw = ImageDraw.Draw(img)
            
            try:
                font_large = ImageFont.truetype("arial.ttf", 32)
                font_medium = ImageFont.truetype("arial.ttf", 16)
                font_small = ImageFont.truetype("arial.ttf", 12)
            except:
                try:
                    font_large = ImageFont.truetype("/usr/share/fonts/truetype/freefont/FreeMono.ttf", 32)
                    font_medium = ImageFont.truetype("/usr/share/fonts/truetype/freefont/FreeMono.ttf", 16)
                    font_small = ImageFont.truetype("/usr/share/fonts/truetype/freefont/FreeMono.ttf", 12)
                except:
                    font_large = ImageFont.load_default()
                    font_medium = ImageFont.load_default()
                    font_small = ImageFont.load_default()
            
            draw.rectangle([self.border-2, self.border-2, 
                          self.image_size-self.border+2, self.image_size-self.border+2], 
                         outline='black', width=3)
            
            for i in range(1, 3):
                x = self.border + i * self.cell_size
                draw.line([(x, self.border), (x, self.image_size - self.border)], fill='black', width=2)
                
                y = self.border + i * self.cell_size
                draw.line([(self.border, y), (self.image_size - self.border, y)], fill='black', width=2)
            
            positions = {
                '1': (0, 0), '2': (1, 0), '3': (2, 0),
                '4': (0, 1), '5': (1, 1), '6': (2, 1),
                '7': (0, 2), '8': (1, 2), '9': (2, 2)
            }
            
            cell_names = {
                '1': 'ХАРАКТЕР', '2': 'ЭНЕРГИЯ', '3': 'ИНТЕРЕСЫ',
                '4': 'ЗДОРОВЬЕ', '5': 'ЛОГИКА', '6': 'ТРУД',
                '7': 'УДАЧА', '8': 'ДОЛГ', '9': 'ПАМЯТЬ'
            }
            
            for digit, (col, row) in positions.items():
                count = psychomatrix.get(digit, 0)
                cell_name = cell_names[digit]
                
                x1 = self.border + col * self.cell_size
                y1 = self.border + row * self.cell_size
                x2 = x1 + self.cell_size
                y2 = y1 + self.cell_size
                
                if count >= 3:
                    bg_color = '#4CAF50'  # Зеленый
                elif count == 0:
                    bg_color = '#FF6B6B'  # Красный
                else:
                    bg_color = '#B3D9FF'  # Голубой
                
                draw.rectangle([x1, y1, x2, y2], fill=bg_color)
                
                count_text = str(count) if count > 0 else "0"
                bbox = draw.textbbox((0, 0), count_text, font=font_large)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                count_x = x1 + (self.cell_size - text_width) // 2
                count_y = y1 + (self.cell_size - text_height) // 2 - 10
                
                draw.text((count_x, count_y), count_text, fill='black', font=font_large)
                
                name_bbox = draw.textbbox((0, 0), cell_name, font=font_small)
                name_width = name_bbox[2] - name_bbox[0]
                name_x = x1 + (self.cell_size - name_width) // 2
                name_y = y2 - 25
                
                draw.text((name_x, name_y), cell_name, fill='darkblue', font=font_small)
                
                digit_x = x1 + 5
                digit_y = y1 + 5
                draw.text((digit_x, digit_y), digit, fill='gray', font=font_small)
            
            title = f"Квадрат Пифагора: {name}"
            date_text = f"Дата рождения: {birth_date}"
            
            final_height = self.image_size + 80
            final_img = Image.new('RGB', (self.image_size, final_height), 'white')
            final_img.paste(img, (0, 0))
            final_draw = ImageDraw.Draw(final_img)
            
            try:
                title_font = ImageFont.truetype("arial.ttf", 18)
                date_font = ImageFont.truetype("arial.ttf", 14)
                legend_font = ImageFont.truetype("arial.ttf", 10)
            except:
                title_font = ImageFont.load_default()
                date_font = ImageFont.load_default()
                legend_font = ImageFont.load_default()
            
            title_bbox = final_draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (self.image_size - title_width) // 2
            final_draw.text((title_x, self.image_size + 10), title, fill='black', font=title_font)
            
            date_bbox = final_draw.textbbox((0, 0), date_text, font=date_font)
            date_width = date_bbox[2] - date_bbox[0]
            date_x = (self.image_size - date_width) // 2
            final_draw.text((date_x, self.image_size + 35), date_text, fill='darkred', font=date_font)
            
            legend_text = "● Сильно (3+)  ● Норма (1-2)  ● Слабо (0)"
            legend_bbox = final_draw.textbbox((0, 0), legend_text, font=legend_font)
            legend_width = legend_bbox[2] - legend_bbox[0]
            legend_x = (self.image_size - legend_width) // 2
            final_draw.text((legend_x, self.image_size + 58), legend_text, fill='gray', font=legend_font)
            
            return final_img
            
        except Exception as e:
            print(f"❌ Ошибка создания изображения: {e}")
            import traceback
            traceback.print_exc()
            return None
            
def validate_birth_date(date_str):
   
    try:
        date_str = date_str.replace(' ', '')
        
        if '.' in date_str:
            parts = date_str.split('.')
        elif '/' in date_str:
            parts = date_str.split('/')
        elif '-' in date_str:
            parts = date_str.split('-')
        else:
            return False, "❌ Неверный формат! Используйте ДД.ММ.ГГГГ", None
        
        if len(parts) != 3:
            return False, "❌ Неверный формат! Должно быть три части: день, месяц, год", None
        
        day, month, year = parts
        
        if not (day.isdigit() and month.isdigit() and year.isdigit()):
            return False, "❌ В дате должны быть только цифры!", None
        
        formatted_date = f"{int(day):02d}.{int(month):02d}.{year}"
        
        birth_date = datetime.strptime(formatted_date, '%d.%m.%Y')
        current_date = datetime.now()
        
        if birth_date > current_date:
            return False, "❌ Дата рождения не может быть в будущем!", None
        
        if birth_date.year < 1900:
            return False, "❌ Дата рождения не может быть раньше 1900 года!", None
        
        age = current_date.year - birth_date.year
        if age > 120:
            return False, "❌ Проверьте дату рождения - возраст слишком большой!", None
            
        return True, "✅ Дата корректна", formatted_date
        
    except ValueError as e:
        return False, f"❌ Неверная дата: {str(e)}", None
    except Exception as e:
        return False, f"❌ Ошибка проверки даты: {str(e)}", None

psychomatrix_viz = PsychomatrixVisualizer()

class PythagorasCube:
    def __init__(self, birth_date):
        self.birth_date = birth_date
    
    def calculate(self):
        try:
            print(f"🔢 Начало расчета для даты: {self.birth_date}")
            
            date_str = self.birth_date.replace('.', '').replace('/', '').replace('-', '').replace(' ', '')
            print(f"🔢 Очищенная дата: {date_str}")
            
            if not date_str.isdigit():
                print(f"❌ В дате есть нецифровые символы: {date_str}")
                return {str(i): 0 for i in range(1, 10)}
            
            if len(date_str) != 8:
                print(f"❌ Неправильная длина даты: {len(date_str)} (ожидается 8)")
                return {str(i): 0 for i in range(1, 10)}
            
            digits = [int(d) for d in date_str]
            print(f"🔢 Цифры даты: {digits}")
            
            first = sum(digits)
            print(f"🔢 Первое число: {first}")
            
            second = sum(int(d) for d in str(first))
            print(f"🔢 Второе число: {second}")
            
            third = first - 2 * digits[0]
            print(f"🔢 Третье число: {third}")
            
            fourth = sum(int(d) for d in str(abs(third)))
            print(f"🔢 Четвертое число: {fourth}")
            
            all_digits = ''.join([
                date_str, 
                str(first),
                str(second),
                str(third),
                str(fourth)
            ])
            print(f"🔢 Все цифры для анализа: {all_digits}")
            
            psychomatrix = {}
            for i in range(1, 10):
                count = all_digits.count(str(i))
                psychomatrix[str(i)] = count
                print(f"🔢 Цифра {i}: {count} раз")
            
            print(f"✅ Психоматрица рассчитана: {psychomatrix}")
            return psychomatrix
            
        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА в calculate(): {e}")
            import traceback
            traceback.print_exc()

            return {str(i): 1 for i in range(1, 10)}

    def get_detailed_interpretation(self, psychomatrix, name):
        try:
            print(f"📖 Начало формирования интерпретации для {name}")
            print(f"📖 Психоматрица: {psychomatrix}")
            
            text = f"🔮 *ПОЛНЫЙ АНАЛИЗ КВАДРАТА ПИФАГОРА ДЛЯ {name.upper()}*\n\n"
            
            char = psychomatrix.get('1', 0)
            text += "🎭 *1. ХАРАКТЕР И СИЛА ВОЛИ*\n"
            
            character_interpretations = {
                0: {
                    "title": "Безвольный характер",
                    "analysis": """Вы очень мягкий и уступчивый человек. Часто идете на поводу у других, не умеете отстаивать свою точку зрения. Ваша слабость может мешать в достижении целей.""",
                    "professions": "Помощник, социальный работник, воспитатель",
                    "relationships": "Подчиняемая позиция в отношениях",
                    "development": "Учитесь говорить 'нет', развивайте уверенность"
                },
                1: {
                    "title": "Уравновешенный эгоист", 
                    "analysis": """У вас достаточно воли для достижения личных целей, но вы не стремитесь доминировать над другими. Умеете отстаивать свои интересы, когда это необходимо.""",
                    "professions": "Специалист, индивидуальный предприниматель, фрилансер",
                    "relationships": "Равноправные отношения, умеете договариваться", 
                    "development": "Развивайте лидерские качества"
                },
                2: {
                    "title": "Сильный характер",
                    "analysis": """Вы обладаете сильной волей и харизмой. Умеете вести за собой людей, принимать решения и нести за них ответственность. Иногда можете быть слишком упрямым.""",
                    "professions": "Руководитель, менеджер, организатор",
                    "relationships": "Лидер в отношениях, берет ответственность",
                    "development": "Учитесь слушать мнение других"
                },
                3: {
                    "title": "Волевой диктатор", 
                    "analysis": """Очень сильная воля, граничащая с деспотизмом. Вы привыкли, чтобы все было по-вашему, и тяжело переносите неподчинение.""",
                    "professions": "Директор, военачальник, политик",
                    "relationships": "Доминирующая позиция, контроль над партнером",
                    "development": "Учитесь уважать чужое мнение"
                },
                4: {
                    "title": "Тиранический характер",
                    "analysis": """Чрезвычайно сильная воля, часто переходящая в тиранию. Вы готовы идти по головам для достижения целей.""",
                    "professions": "Крупный руководитель, лидер организации",
                    "relationships": "Полный контроль, подавление партнера",
                    "development": "Развивайте эмпатию и сострадание"
                }
            }
            
            char_data = character_interpretations.get(char, character_interpretations[1])
            text += f"   ⚡ *Тип:* {char_data['title']}\n"
            text += f"   📝 *Анализ:* {char_data['analysis']}\n"
            text += f"   💼 *Профессии:* {char_data['professions']}\n"
            text += f"   ❤️ *Отношения:* {char_data['relationships']}\n" 
            text += f"   💡 *Развитие:* {char_data['development']}\n\n"

            energy = psychomatrix.get('2', 0)
            text += "⚡ *2. БИОЭНЕРГИЯ И ЭНЕРГЕТИКА*\n"
            
            energy_interpretations = {
                0: {
                    "level": "Энергетический вампир",
                    "analysis": """У вас очень слабая собственная энергетика. Вы подсознательно тянете энергию от других людей, что может вызывать у них дискомфорт.""",
                    "protection": "Избегайте конфликтов, занимайтесь спортом",
                    "recovery": "Природа, сон, здоровое питание",
                    "danger": "Быстрое истощение, зависимость от других"
                },
                1: {
                    "level": "Донор для вампиров", 
                    "analysis": """У вас нормальная энергетика, но вы легко становитесь жертвой энергетических вампиров. Нужно учиться защищаться.""",
                    "protection": "Избегайте токсичных людей, носите обереги",
                    "recovery": "Хобби, прогулки, позитивное общение",
                    "danger": "Энергетическое истощение от общения"
                },
                2: {
                    "level": "Стабильная энергетика",
                    "analysis": """У вас хорошая устойчивая энергетика. Вы можете быть донором, но при этом не страдаете. Умеете восстанавливаться.""",
                    "protection": "Здоровый образ жизни, медитации",
                    "recovery": "Отдых, смена деятельности", 
                    "danger": "Длительные стрессы"
                },
                3: {
                    "level": "Сильная биоэнергетика",
                    "analysis": """Вы обладаете сильной энергетикой и можете быть целителем. Люди чувствуют себя лучше в вашем присутствии.""",
                    "protection": "Контроль над эмоциями",
                    "recovery": "Быстрое восстановление",
                    "danger": "Можете неосознанно влиять на других"
                },
                4: {
                    "level": "Мощный экстрасенс", 
                    "analysis": """Очень сильная энергетика, граничащая с экстрасенсорными способностями. Вы можете чувствовать энергии и влиять на них.""",
                    "protection": "Сложные энергетические практики",
                    "recovery": "Медитации, работа с чакрами",
                    "danger": "Неосознанное влияние на окружающих"
                }
            }
            
            energy_data = energy_interpretations.get(energy, energy_interpretations[2])
            text += f"   🔋 *Уровень:* {energy_data['level']}\n"
            text += f"   📝 *Анализ:* {energy_data['analysis']}\n"
            text += f"   🛡️ *Защита:* {energy_data['protection']}\n"
            text += f"   🔄 *Восстановление:* {energy_data['recovery']}\n"
            text += f"   ⚠️ *Опасности:* {energy_data['danger']}\n\n"

            science = psychomatrix.get('3', 0)
            text += "🔬 *3. ПОЗНАНИЕ И ТЕХНИЧЕСКИЕ СПОСОБНОСТИ*\n"
            
            science_interpretations = {
                0: {
                    "type": "Гуманитарий",
                    "analysis": """Вы чистый гуманитарий. Технические науки даются с трудом, зато прекрасные способности к языкам, искусству, психологии.""",
                    "professions": "Писатель, психолог, учитель, художник",
                    "learning": "Через образы и метафоры",
                    "development": "Развивайте логическое мышление"
                },
                1: {
                    "type": "Гуманитарий с наклонностями",
                    "analysis": """В основном гуманитарный склад ума, но есть интерес к технике. Можете разбираться в технологиях при необходимости.""",
                    "professions": "Дизайнер, маркетолог, журналист",
                    "learning": "Практический подход",
                    "development": "Изучайте точные науки"
                },
                2: {
                    "type": "Гармоничный ум",
                    "analysis": """Сбалансированные способности. В равной степени можете заниматься как гуманитарными, так и техническими науками.""",
                    "professions": "Архитектор, программист, врач",
                    "learning": "Любые методы",
                    "development": "Углубление в специализацию"
                },
                3: {
                    "type": "Технарь с наклонностями",
                    "analysis": """В основном технический склад ума, но есть гуманитарные интересы. Логика преобладает над эмоциями.""",
                    "professions": "Инженер, ученый, аналитик",
                    "learning": "Системный подход",
                    "development": "Развивайте творчество"
                },
                4: {
                    "type": "Чистый технарь",
                    "analysis": """Ярко выраженные технические способности. Мыслите логически, любите точные науки и технологии.""",
                    "professions": "Программист, математик, физик",
                    "learning": "Логические схемы",
                    "development": "Развивайте эмоциональный интеллект"
                }
            }
            
            science_data = science_interpretations.get(science, science_interpretations[2])
            text += f"   🧠 *Тип ума:* {science_data['type']}\n"
            text += f"   📝 *Анализ:* {science_data['analysis']}\n"
            text += f"   💼 *Профессии:* {science_data['professions']}\n"
            text += f"   📚 *Обучение:* {science_data['learning']}\n"
            text += f"   💡 *Развитие:* {science_data['development']}\n\n"

            health = psychomatrix.get('4', 0)
            text += "❤️ *4. ЗДОРОВЬЕ И ВИТАЛЬНОСТЬ*\n"
            
            health_interpretations = {
                0: {
                    "potential": "Слабое здоровье",
                    "analysis": """От природы слабое здоровье, склонность к заболеваниям. Нужно особенно внимательно относиться к образу жизни.""",
                    "recommendations": "Щадящий режим, регулярные обследования",
                    "prevention": "Здоровое питание, избегание стрессов",
                    "dangers": "Хронические заболевания, низкий иммунитет"
                },
                1: {
                    "potential": "Среднее здоровье",
                    "analysis": """Здоровье нормальное, но не железное. При неправильном образе жизни легко возникают проблемы.""",
                    "recommendations": "Регулярные умеренные нагрузки",
                    "prevention": "Сбалансированное питание, витамины",
                    "dangers": "Стрессы, вредные привычки"
                },
                2: {
                    "potential": "Крепкое здоровье", 
                    "analysis": """Хорошее здоровье от природы. Быстрое восстановление после болезней, высокая жизнестойкость.""",
                    "recommendations": "Активный образ жизни, спорт",
                    "prevention": "Регулярные физические нагрузки",
                    "dangers": "Пренебрежение профилактикой"
                },
                3: {
                    "potential": "Очень крепкое здоровье",
                    "analysis": """Отличное здоровье, практически не болеете. Высокая выносливость и быстрая регенерация.""",
                    "recommendations": "Профессиональный спорт, экстрим",
                    "prevention": "Поддержание формы",
                    "dangers": "Излишняя самоуверенность"
                },
                4: {
                    "potential": "Железное здоровье",
                    "analysis": """Невероятно крепкое здоровье, можете переносить экстремальные нагрузки. Редко болеете.""",
                    "recommendations": "Экстремальные виды спорта",
                    "prevention": "Интенсивные тренировки",
                    "dangers": "Практически отсутствуют"
                }
            }
            
            health_data = health_interpretations.get(health, health_interpretations[2])
            text += f"   💪 *Потенциал:* {health_data['potential']}\n"
            text += f"   📝 *Анализ:* {health_data['analysis']}\n"
            text += f"   🏃 *Рекомендации:* {health_data['recommendations']}\n"
            text += f"   🛡️ *Профилактика:* {health_data['prevention']}\n"
            text += f"   ⚠️ *Риски:* {health_data['dangers']}\n\n"

            logic = psychomatrix.get('5', 0)
            text += "🧠 *5. ЛОГИКА И ИНТУИЦИЯ*\n"
            
            logic_interpretations = {
                0: {
                    "type": "Чистая интуиция",
                    "analysis": """Вы действуете преимущественно интуитивно. Логика слабая, но прекрасное чутье и предвидение.""",
                    "strengths": "Предчувствия, озарения, тонкое восприятие",
                    "weaknesses": "Сложности с планированием, нелогичность",
                    "development": "Развивайте логическое мышление"
                },
                1: {
                    "type": "Интуиция с логикой",
                    "analysis": """Интуиция преобладает над логикой, но вы способны к рациональному мышлению при необходимости.""",
                    "strengths": "Хорошее чутье, творческий подход",
                    "weaknesses": "Недостаток системности",
                    "development": "Тренируйте аналитические способности"
                },
                2: {
                    "type": "Гармоничный баланс",
                    "analysis": """Идеальный баланс логики и интуиции. Умеете и просчитывать варианты, и доверять внутреннему голосу.""",
                    "strengths": "Взвешенные решения, предвидение",
                    "weaknesses": "Временные колебания",
                    "development": "Совершенствуйте оба качества"
                },
                3: {
                    "type": "Логика с интуицией",
                    "analysis": """Логика преобладает, но интуиция тоже работает. Принимаете решения на основе анализа.""",
                    "strengths": "Аналитический ум, системность",
                    "weaknesses": "Излишний рационализм",
                    "development": "Развивайте доверие к интуиции"
                },
                4: {
                    "type": "Чистая логика",
                    "analysis": """Ярко выраженное логическое мышление. Доверяете только фактам и расчетам.""",
                    "strengths": "Анализ, планирование, стратегия",
                    "weaknesses": "Недооценка интуиции",
                    "development": "Учитесь слушать внутренний голос"
                }
            }
            
            logic_data = logic_interpretations.get(logic, logic_interpretations[2])
            text += f"   ⚖️ *Тип мышления:* {logic_data['type']}\n"
            text += f"   📝 *Анализ:* {logic_data['analysis']}\n"
            text += f"   ✅ *Сильные стороны:* {logic_data['strengths']}\n"
            text += f"   ❌ *Слабые стороны:* {logic_data['weaknesses']}\n"
            text += f"   💡 *Развитие:* {logic_data['development']}\n\n"

            labor = psychomatrix.get('6', 0)
            text += "🛠️ *6. ТРУДОЛЮБИЕ И МАСТЕРСТВО*\n"
            
            labor_interpretations = {
                0: {
                    "approach": "Творческий бездельник",
                    "analysis": """Не любите физический труд, предпочитаете творчество или интеллектуальную работу. Может быть лень.""",
                    "ideal_work": "Искусство, дизайн, консультирование",
                    "difficulties": "Рутина, монотонный труд",
                    "development": "Развивайте дисциплину"
                },
                1: {
                    "approach": "Избирательный работник",
                    "analysis": """Трудолюбивы в том, что интересно. Можете лениться при выполнении скучных задач.""",
                    "ideal_work": "Проектная работа, творческие профессии",
                    "difficulties": "Рутинные обязанности",
                    "development": "Учитесь доводить дела до конца"
                },
                2: {
                    "approach": "Гармоничный работник", 
                    "analysis": """Нормальное трудолюбие. Умеете и работать, и отдыхать. Ответственно относитесь к обязанностям.""",
                    "ideal_work": "Большинство профессий",
                    "difficulties": "Экстремальные нагрузки",
                    "development": "Развивайте специализацию"
                },
                3: {
                    "approach": "Трудоголик",
                    "analysis": """Очень трудолюбивы, можете работать на износ. Иногда забываете об отдыхе и личной жизни.""",
                    "ideal_work": "Карьерные позиции, бизнес",
                    "difficulties": "Баланс работа-отдых",
                    "development": "Учитесь отдыхать"
                },
                4: {
                    "approach": "Мастер-профессионал",
                    "analysis": """Исключительное трудолюбие и мастерство. Доводите любое дело до совершенства.""",
                    "ideal_work": "Эксперт, мастер, руководитель",
                    "difficulties": "Перфекционизм, выгорание",
                    "development": "Делегирование полномочий"
                }
            }
            
            labor_data = labor_interpretations.get(labor, labor_interpretations[2])
            text += f"   🔧 *Подход к труду:* {labor_data['approach']}\n"
            text += f"   📝 *Анализ:* {labor_data['analysis']}\n"
            text += f"   💼 *Идеальная работа:* {labor_data['ideal_work']}\n"
            text += f"   ⚠️ *Сложности:* {labor_data['difficulties']}\n"
            text += f"   💡 *Развитие:* {labor_data['development']}\n\n"

            luck = psychomatrix.get('7', 0)
            text += "🍀 *7. УДАЧА И ВЕЗЕНИЕ*\n"
            
            luck_interpretations = {
                0: {
                    "attitude": "Невезучий",
                    "analysis": """Вам часто не везет, приходится всего добиваться тяжелым трудом. Удача обходит стороной.""",
                    "strengths": "Упорство, самостоятельность",
                    "weaknesses": "Постоянные препятствия",
                    "development": "Учитесь создавать возможности"
                },
                1: {
                    "attitude": "Стабильный",
                    "analysis": """Удача бывает, но нечасто. В основном полагаетесь на собственные силы и планирование.""",
                    "strengths": "Надежность, предсказуемость",
                    "weaknesses": "Нехватка везения в критических ситуациях",
                    "development": "Развивайте интуицию для распознавания шансов"
                },
                2: {
                    "attitude": "Удачливый", 
                    "analysis": """Вам часто везет в важных вопросах. Умеете оказаться в нужное время в нужном месте.""",
                    "strengths": "Везение, своевременные возможности",
                    "weaknesses": "Можете полагаться на удачу больше необходимого",
                    "development": "Сочетайте везение с планированием"
                },
                3: {
                    "attitude": "Везунчик",
                    "analysis": """Вам очень везет по жизни. Даже в сложных ситуациях находится неожиданный выход.""",
                    "strengths": "Постоянное везение, выход из любых ситуаций",
                    "weaknesses": "Риск стать беспечным",
                    "development": "Используйте удачу для помощи другим"
                },
                4: {
                    "attitude": "Счастливчик",
                    "analysis": """Невероятно удачливый человек. Фортуна всегда на вашей стороне.""",
                    "strengths": "Феноменальное везение, выигрыши",
                    "weaknesses": "Могут завидовать",
                    "development": "Делитесь удачей с окружающими"
                }
            }
            
            luck_data = luck_interpretations.get(luck, luck_interpretations[2])
            text += f"   🎯 *Отношение удачи:* {luck_data['attitude']}\n"
            text += f"   📝 *Анализ:* {luck_data['analysis']}\n"
            text += f"   ✅ *Сильные стороны:* {luck_data['strengths']}\n"
            text += f"   ❌ *Слабые стороны:* {luck_data['weaknesses']}\n"
            text += f"   💡 *Развитие:* {luck_data['development']}\n\n"

            duty = psychomatrix.get('8', 0)
            text += "⚖️ *8. ЧУВСТВО ДОЛГА И ОТВЕТСТВЕННОСТЬ*\n"
            
            duty_interpretations = {
                0: {
                    "attitude": "Безответственный",
                    "analysis": """Избегаете ответственности, не любите обязательства. Предпочитаете свободу и независимость.""",
                    "strengths": "Свобода действий, гибкость",
                    "weaknesses": "Ненадежность, безответственность",
                    "development": "Учитесь брать на себя обязательства"
                },
                1: {
                    "attitude": "Избирательная ответственность",
                    "analysis": """Ответственны в том, что важно для вас. Можете уклоняться от неинтересных обязательств.""",
                    "strengths": "Гибкость, умение расставлять приоритеты",
                    "weaknesses": "Непостоянство",
                    "development": "Развивайте надежность"
                },
                2: {
                    "attitude": "Ответственный", 
                    "analysis": """Нормальное чувство долга. Выполняете обещанное, на вас можно положиться.""",
                    "strengths": "Надежность, исполнительность",
                    "weaknesses": "Иногда берете на себя слишком много",
                    "development": "Учитесь говорить 'нет'"
                },
                3: {
                    "attitude": "Чрезмерно ответственный",
                    "analysis": """Очень развитое чувство долга. Часто берете на себя лишнюю ответственность.""",
                    "strengths": "Высокая надежность, преданность",
                    "weaknesses": "Перегрузка, стресс",
                    "development": "Учитесь делегировать"
                },
                4: {
                    "attitude": "Гиперответственный",
                    "analysis": """Чрезмерно развитое чувство долга. Берете ответственность за всех и вся.""",
                    "strengths": "Исключительная надежность",
                    "weaknesses": "Выгорание, мученичество",
                    "development": "Учитесь заботиться о себе"
                }
            }
            
            duty_data = duty_interpretations.get(duty, duty_interpretations[2])
            text += f"   🎯 *Отношение к долгу:* {duty_data['attitude']}\n"
            text += f"   📝 *Анализ:* {duty_data['analysis']}\n"
            text += f"   ✅ *Сильные стороны:* {duty_data['strengths']}\n"
            text += f"   ❌ *Слабые стороны:* {duty_data['weaknesses']}\n"
            text += f"   💡 *Развитие:* {duty_data['development']}\n\n"

            memory = psychomatrix.get('9', 0)
            text += "📚 *9. ПАМЯТЬ, УМ И ЭРУДИЦИЯ*\n"
            
            memory_interpretations = {
                0: {
                    "type": "Практический ум",
                    "analysis": """Память слабая, но хорошие практические способности. Запоминаете только то, что нужно для дела.""",
                    "strengths": "Практическое применение знаний",
                    "weaknesses": "Плохая память, забывчивость",
                    "development": "Тренируйте память, используйте ассоциации"
                },
                1: {
                    "type": "Избирательная память",
                    "analysis": """Хорошая память на важное, но можете забывать несущественные детали.""",
                    "strengths": "Эффективное использование памяти",
                    "weaknesses": "Пробелы в знаниях",
                    "development": "Расширяйте кругозор"
                },
                2: {
                    "type": "Хорошая память", 
                    "analysis": """Хорошие способности к запоминанию и обучению. Быстро усваиваете новую информацию.""",
                    "strengths": "Быстрое обучение, эрудиция",
                    "weaknesses": "Перегрузка информацией",
                    "development": "Систематизируйте знания"
                },
                3: {
                    "type": "Отличная память",
                    "analysis": """Прекрасная память и аналитические способности. Можете стать экспертом в своей области.""",
                    "strengths": "Глубокие знания, аналитический ум",
                    "weaknesses": "Излишняя критичность",
                    "development": "Развивайте творческое мышление"
                },
                4: {
                    "type": "Феноменальная память",
                    "analysis": """Исключительные способности к запоминанию и анализу. Можете достичь вершин в науке или искусстве.""",
                    "strengths": "Энциклопедические знания, гениальность",
                    "weaknesses": "Сложности в общении с обычными людьми",
                    "development": "Учитесь просто объяснять сложное"
                }
            }
            
            memory_data = memory_interpretations.get(memory, memory_interpretations[2])
            text += f"   🧠 *Тип интеллекта:* {memory_data['type']}\n"
            text += f"   📝 *Анализ:* {memory_data['analysis']}\n"
            text += f"   ✅ *Сильные стороны:* {memory_data['strengths']}\n"
            text += f"   ❌ *Слабые стороны:* {memory_data['weaknesses']}\n"
            text += f"   💡 *Развитие:* {memory_data['development']}\n\n"

            text += "🌟 *ОБЩИЙ АНАЛИЗ И РЕКОМЕНДАЦИИ*\n\n"
            
            strong_numbers = [k for k, v in psychomatrix.items() if v >= 3]
            weak_numbers = [k for k, v in psychomatrix.items() if v == 0]
            
            if strong_numbers:
                text += "✅ *ВАШИ СИЛЬНЫЕ СТОРОНЫ:*\n"
                for num in strong_numbers:
                    strengths = {
                        '1': "• Сильная воля и лидерские качества",
                        '2': "• Хорошая энергетика и выносливость", 
                        '3': "• Технические или гуманитарные способности",
                        '4': "• Крепкое здоровье и жизнестойкость",
                        '5': "• Развитая логика или интуиция",
                        '6': "• Трудолюбие и мастерство",
                        '7': "• Удача и везение",
                        '8': "• Ответственность и надежность",
                        '9': "• Хорошая память и интеллект"
                    }
                    text += f"{strengths.get(num, '• Уникальные способности')}\n"
                text += "\n"
            
            if weak_numbers:
                text += "⚠️ *ЗОНЫ РОСТА:*\n"
                for num in weak_numbers:
                    recommendations = {
                        '1': "• Развивайте уверенность в себе, учитесь отстаивать свое мнение",
                        '2': "• Занимайтесь энергетическими практиками, спортом",
                        '3': "• Изучайте новые области знаний, развивайте любознательность",
                        '4': "• Уделяйте внимание здоровью, правильному питанию и режиму",
                        '5': "• Тренируйте логическое мышление и развивайте интуицию",
                        '6': "• Находите радость в труде, развивайте профессиональные навыки", 
                        '7': "• Учитесь видеть возможности, развивайте позитивное мышление",
                        '8': "• Берите на себя ответственность, выполняйте обещания",
                        '9': "• Тренируйте память, читайте книги, учитесь постоянно"
                    }
                    text += f"{recommendations.get(num, '• Гармоничное развитие личности')}\n"
                text += "\n"
            
            text += "📖 *КАРМИЧЕСКИЕ ЗАДАЧИ:*\n"
            karmic_tasks = []
            
            if psychomatrix.get('1', 0) == 0:
                karmic_tasks.append("• Научиться отстаивать свои границы")
            if psychomatrix.get('2', 0) == 0:
                karmic_tasks.append("• Научиться сохранять и восстанавливать энергию")
            if psychomatrix.get('3', 0) == 0:
                karmic_tasks.append("• Развивать любознательность и стремление к знаниям")
            if psychomatrix.get('4', 0) == 0:
                karmic_tasks.append("• Укреплять здоровье и ценить свое тело")
            if psychomatrix.get('5', 0) == 0:
                karmic_tasks.append("• Находить баланс между логикой и интуицией")
            if psychomatrix.get('6', 0) == 0:
                karmic_tasks.append("• Находить радость в труде и служении")
            if psychomatrix.get('7', 0) == 0:
                karmic_tasks.append("• Учиться видеть возможности и доверять жизни")
            if psychomatrix.get('8', 0) == 0:
                karmic_tasks.append("• Развивать чувство ответственности перед другими")
            if psychomatrix.get('9', 0) == 0:
                karmic_tasks.append("• Стремиться к постоянному обучению и развитию")
            
            if not karmic_tasks:
                karmic_tasks.append("• Помогать другим в их развитии и становлении")
            
            text += "\n".join(karmic_tasks)
            text += "\n\n"
            
            text += "💫 *ЗАКЛЮЧЕНИЕ:*\n"
            text += random.choice([
                "Квадрат Пифагора показывает, что {name} обладает уникальным сочетанием качеств, которые при правильном развитии могут привести к успеху и гармонии. Помните, что цифры показывают потенциал, а его реализация зависит от вас!",
                "Расчет Пифагора открывает перед {name} удивительные возможности! Цифры указывают на сильные стороны, которые станут вашим надежным фундаментом на пути к самореализации и достижению целей.",
                "Числовой портрет {name} отражает глубокую связь с космическими ритмами. Каждая цифра - это ключ к пониманию вашей истинной природы и предназначения в этом мире.",
                "Анализ Пифагора дает {name} четкую карту личностных качеств. Используйте эти знания как практический инструмент для развития сильных сторон и работы над слабыми местами.",
                "Карта чисел {name} сияет многообещающими возможностями! Каждая характеристика - это ваш личный суперсил, готовый раскрыться в нужный момент.",
                "Нумерологический анализ {name} демонстрирует сбалансированную комбинацию психоматрических элементов. Данная конфигурация предполагает значительный потенциал для адаптации и роста.",
                "Пифагорейский квадрат {name} - это зашифрованное послание духа. Расшифровав его, вы поймете законы, управляющие вашей кармической судьбой.",
                "Квадрат судьбы {name} указывает на особое духовное задание. Цифры ведут вас по пути самопознания к высшему пониманию своего места во Вселенной.",
                "Цифровой профиль {name} поражает своим разнообразием! Вы обладаете всем необходимым, чтобы превратить жизненные вызовы в блестящие победы.",
                "Пифагор раскрыл для {name} тайный код личности. Эти цифры - лишь начало увлекательного путешествия вглубь себя, где вас ждут удивительные открытия.",
                "Числовой код {name} хранит тайны прошлых воплощений. Расшифровка этой матрицы откроет доступ к родовой мудрости и духовным дарам.",
                "Для {name} числа раскрывают кармический путь. Каждая цифра - это ступень на лестнице духовного восхождения к вашему высшему предназначению."
            ]).format(name=name) + "\n\n"
            text += "\n✨ Рассчитано ботом [🅿️🅸🅵🅰️](tg://resolve?domain=pythagoras_cube_bot)"
            
            print(f"✅ Интерпретация успешно сформирована")
            return text
            
        except Exception as e:
            print(f"❌ ОШИБКА в get_detailed_interpretation(): {e}")
            import traceback
            traceback.print_exc()
            return f"❌ Произошла ошибка при формировании анализа. Пожалуйста, попробуйте еще раз.\n\nОшибка: {str(e)}"
    def get_enhanced_psychomatrix_text(self, psychomatrix, name):
        """Создает улучшенное текстовое представление психоматрицы с эмодзи"""
        matrix = [
            [psychomatrix.get('1', 0), psychomatrix.get('2', 0), psychomatrix.get('3', 0)],
            [psychomatrix.get('4', 0), psychomatrix.get('5', 0), psychomatrix.get('6', 0)],
            [psychomatrix.get('7', 0), psychomatrix.get('8', 0), psychomatrix.get('9', 0)]
        ]
        
        emojis = ['🎭', '⚡', '🔬', '❤️', '🧠', '🛠️', '🍀', '⚖️', '📚']
        qualities = ['ХАРАКТЕР', 'ЭНЕРГИЯ', 'ИНТЕРЕСЫ', 'ЗДОРОВЬЕ', 'ЛОГИКА', 'ТРУД', 'УДАЧА', 'ДОЛГ', 'ПАМЯТЬ']
               
        text = "📊 *ТЕКСТОВАЯ ПСИХОМАТРИЦА:*\n\n"
        text += "┌───────────┬───────────┬───────────┐\n"
        
        for i, row in enumerate(matrix):
            row_text = "│"
            for j, cell in enumerate(row):
                emoji = emojis[i * 3 + j]
                cell_text = str(cell)
                if cell == 0:
                    row_text += f" {emoji} {cell_text}   │"
                else:
                    row_text += f" {emoji} {cell_text}   │"
            text += row_text + "\n"
            
            if i < 2:
                text += "├───────────┼───────────┼───────────┤\n"
            else:
                text += "└───────────┴───────────┴───────────┘\n"
        
        text += "\n*📖 РАСШИФРОВКА:*\n"
        
        for i, quality in enumerate(qualities):
            count = psychomatrix.get(str(i + 1), 0)
            emoji = emojis[i]
            count_text = str(count)
            
            if count == 0:
                status = "🔴 Слабо"
            elif count < 3:
                status = "🟡 Норма" 
            else:
                status = "🟢 Сильно"
            text += f"{emoji} {quality}: {count_text} ({status})\n"
        
        return text

    def calculate_compatibility(self, psychomatrix1, psychomatrix2, name1, name2):
        
        text = f"💞 *ПОЛНЫЙ АНАЛИЗ СОВМЕСТИМОСТИ: {name1.upper()} И {name2.upper()}*\n\n"
        
        total_score = 0
        max_score = 27
        
        char1 = psychomatrix1.get('1', 0)
        char2 = psychomatrix2.get('1', 0)
        char_compat = self._calculate_character_compatibility(char1, char2)
        total_score += char_compat
        
        text += "🎭 *1. СОВМЕСТИМОСТЬ ХАРАКТЕРОВ*\n"
        text += f"   {name1}: {self._get_character_description(char1)}\n"
        text += f"   {name2}: {self._get_character_description(char2)}\n"
        
        if char_compat >= 8:
            text += "   ✅ *ИДЕАЛЬНОЕ СОЧЕТАНИЕ!*\n"
            text += "   Вы идеально дополняете друг друга! Один партнер приносит в отношения мягкость и гармонию, другой - решительность и силу. Такой союз может стать очень продуктивным и счастливым.\n\n"
        elif char_compat >= 5:
            text += "   ⚠️ *ХОРОШАЯ СОВМЕСТИМОСТЬ*\n"
            text += "   В целом гармоничный союз. Возможны небольшие разногласия, но при взаимном уважении они легко решаются. Идеальная почва для роста отношений.\n\n"
        else:
            text += "   ❌ *СЛОЖНОЕ СОЧЕТАНИЕ*\n"
            text += "   Возможны серьезные конфликты из-за разницы в характерах. Требуется большая работа над отношениями, умение слушать и идти на компромиссы.\n\n"

        energy1 = psychomatrix1.get('2', 0)
        energy2 = psychomatrix2.get('2', 0)
        energy_compat = self._calculate_energy_compatibility(energy1, energy2)
        total_score += energy_compat
        
        text += "⚡ *2. ЭНЕРГЕТИЧЕСКАЯ СОВМЕСТИМОСТЬ*\n"
        text += f"   {name1}: {self._get_energy_description(energy1)}\n"
        text += f"   {name2}: {self._get_energy_description(energy2)}\n"
        
        if energy_compat >= 8:
            text += "   ✅ *ОТЛИЧНЫЙ ЭНЕРГООБМЕН!*\n"
            text += "   Вы заряжаете друг друга положительной энергией! Отношения наполнены страстью и взаимным вдохновением. Идеально для страстного и продуктивного союза.\n\n"
        elif energy_compat >= 5:
            text += "   ⚠️ *СТАБИЛЬНЫЙ БАЛАНС*\n"
            text += "   Энергии достаточно для комфортных отношений. Партнеры не истощают друг друга, сохраняя здоровый баланс сил. Стабильность и предсказуемость.\n\n"
        else:
            text += "   ❌ *ЭНЕРГЕТИЧЕСКИЙ ДИСБАЛАНС*\n"
            text += "   Один партнер может истощать другого. Важно давать пространство для восстановления, учиться распределять энергию и уважать потребности партнера.\n\n"

        int1 = psychomatrix1.get('3', 0)
        int2 = psychomatrix2.get('3', 0)
        int_compat = self._calculate_interests_compatibility(int1, int2)
        total_score += int_compat
        
        text += "🔬 *3. ИНТЕЛЛЕКТУАЛЬНАЯ СОВМЕСТИМОСТЬ*\n"
        text += f"   {name1}: {self._get_interests_description(int1)}\n"
        text += f"   {name2}: {self._get_interests_description(int2)}\n"
        
        if int_compat >= 8:
            text += "   ✅ *ИДЕАЛЬНОЕ СОЧЕТАНИЕ!*\n"
            text += "   Вам никогда не бывает скучно вместе! Можете часами обсуждать интересные темы, делиться идеями и вдохновлять друг друга на новые свершения.\n\n"
        elif int_compat >= 5:
            text += "   ⚠️ *РАЗНЫЕ, НО ДОПОЛНЯЮЩИЕ*\n"
            text += "   Вы можете учиться друг у друга новому. Разница в интересах становится источником взаимного обогащения, если оба партнера открыты к новому.\n\n"
        else:
            text += "   ❌ *СЛОЖНОСТИ В ОБЩЕНИИ*\n"
            text += "   Разные взгляды на жизнь могут создавать недопонимание. Важно находить общие темы, уважать различия и учиться понимать мировоззрение партнера.\n\n"

        compatibility_percent = (total_score / max_score) * 100
        
        text += f"📊 *ОБЩАЯ СОВМЕСТИМОСТЬ: {compatibility_percent:.0f}%*\n\n"
        
        if compatibility_percent >= 80:
            text += "🌟 *ВЫСОКАЯ СОВМЕСТИМОСТЬ!*\n"
            text += "Этот союз имеет все шансы стать гармоничным, счастливым и долговечным! Вы идеально подходите друг другу по основным параметрам личности.\n\n"
        elif compatibility_percent >= 60:
            text += "💫 *ХОРОШАЯ СОВМЕСТИМОСТЬ*\n"
            text += "Отношения очень перспективные! При взаимных усилиях и понимании вы можете создать крепкий и счастливый союз. Работайте вместе над отношениями.\n\n"
        elif compatibility_percent >= 40:
            text += "⚖️ *СРЕДНЯЯ СОВМЕСТИМОСТЬ*\n"
            text += "Отношения возможны, но потребуют много работы над собой и взаимных уступок. Важно быть готовыми к компромиссам и постоянной работе.\n\n"
        else:
            text += "💔 *НИЗКАЯ СОВМЕСТИМОСТЬ*\n"
            text += "Союз будет сложным и потребует серьезной работы над отношениями. Возможно, стоит пересмотреть целесообразность таких отношений или быть готовыми к большим усилиям.\n\n"
        
        text += "💡 *ДЕТАЛЬНЫЕ РЕКОМЕНДАЦИИ ДЛЯ ПАРЫ:*\n\n"
        
        if char1 == 0 and char2 >= 2:
            text += "🎭 *По характеру:*\n"
            text += f"• {name2} - будьте особенно тактичны, не подавляйте партнера\n"
            text += f"• {name1} - учитесь отстаивать свои границы и выражать мнение\n"
            text += "• Идеальное распределение: сила + гармония = баланс\n\n"
        elif char2 == 0 and char1 >= 2:
            text += "🎭 *По характеру:*\n"
            text += f"• {name1} - будьте особенно тактичны, не подавляйте партнера\n"
            text += f"• {name2} - учитесь отстаивать свои границы\n"
            text += "• Баланс силы и мягкости - ключ к гармонии\n\n"
        
        if energy1 == 0 or energy2 == 0:
            text += "⚡ *По энергии:*\n"
            text += "• Энергетически слабому партнеру - больше отдыха и уединения\n"
            text += "• Совместные медитации и прогулки на природе восстановят баланс\n"
            text += "• Избегайте стрессовых ситуаций и шумных мероприятий\n\n"
        
        if int1 != int2:
            text += "🔬 *По интересам:*\n"
            text += "• Уважайте разницу в интересах - это взаимное обогащение\n"
            text += "• Находите общие хобби и занятия\n"
            text += "• Учитесь слушать и интересоваться миром партнера\n\n"
        
        text += "🌱 *ОБЩИЕ СОВЕТЫ ПО РАЗВИТИЮ ОТНОШЕНИЙ:*\n"
        text += "• Регулярно проводите качественное время вместе наедине\n"
        text += "• Учитесь выражать благодарность и appreciation\n"
        text += "• Создавайте совместные ритуалы и традиции\n"
        text += "• Не бойтесь обращаться к семейному психологу при необходимости\n"
        text += "• Помните: идеальных отношений не существует, есть work in progress\n\n"
        
        text += "\n✨ Рассчитано ботом [🅿️🅸🅵🅰️](tg://resolve?domain=pythagoras_cube_bot)"
        
        return text
    
    def _get_character_description(self, char):
        descriptions = {
            0: "Мягкий, уступчивый, безвольный",
            1: "Уравновешенный, тактичный, гибкий", 
            2: "Сильный, решительный, лидер",
            3: "Волевой, упрямый, диктатор",
            4: "Тиранический, деспотичный"
        }
        return descriptions.get(char, "Не определен")
    
    def _get_energy_description(self, energy):
        descriptions = {
            0: "Слабая энергетика, вампир",
            1: "Нормальная энергетика, донор",
            2: "Хорошая энергетика, стабильный",
            3: "Сильная энергетика, целитель",
            4: "Мощная энергетика, экстрасенс"
        }
        return descriptions.get(energy, "Не определен")
    
    def _get_interests_description(self, interests):
        descriptions = {
            0: "Гуманитарный склад ума",
            1: "Гуманитарный с техническими наклонностями", 
            2: "Гармоничный ум",
            3: "Технический с гуманитарными наклонностями",
            4: "Технический склад ума"
        }
        return descriptions.get(interests, "Не определен")
    
    def _calculate_character_compatibility(self, char1, char2):
        if (char1 == 1 and char2 == 2) or (char1 == 2 and char2 == 1):
            return 9
        elif char1 == 1 and char2 == 1:
            return 8
        elif (char1 == 0 and char2 == 2) or (char1 == 2 and char2 == 0):
            return 7
        elif (char1 == 0 and char2 == 1) or (char1 == 1 and char2 == 0):
            return 6
        elif char1 == 0 and char2 == 0:
            return 3
        elif char1 == 2 and char2 == 2:
            return 2
        else:
            return 5
    
    def _calculate_energy_compatibility(self, energy1, energy2):
        if (energy1 == 2 and energy2 == 1) or (energy1 == 1 and energy2 == 2):
            return 9
        elif energy1 == 2 and energy2 == 2:
            return 8
        elif energy1 == 1 and energy2 == 1:
            return 7
        elif (energy1 == 2 and energy2 == 0) or (energy1 == 0 and energy2 == 2):
            return 6
        elif energy1 == 0 and energy2 == 0:
            return 2
        elif (energy1 == 0 and energy2 == 1) or (energy1 == 1 and energy2 == 0):
            return 4
        else:
            return 5
    
    def _calculate_interests_compatibility(self, int1, int2):
        if int1 == int2:
            return 9
        elif int1 == 3 or int2 == 3:
            return 8
        elif (int1 == 1 and int2 == 2) or (int1 == 2 and int2 == 1):
            return 4
        else:
            return 6

class UserStats:
    def __init__(self):
        self.stats = self.load_stats()
        self.existing_users = set(self.stats['user_calculations'].keys())
        print(f"📊 Статистика загружена: {len(self.existing_users)} пользователей")
    
    def is_existing_user(self, user_id):
        """Проверяет, был ли пользователь уже в боте"""
        return str(user_id) in self.existing_users
    
    def load_stats(self):
        try:
            if os.path.exists(USER_STATS_FILE):
                with open(USER_STATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"✅ Файл статистики загружен: {USER_STATS_FILE}")
                    if 'user_calculations' in data:
                        data['user_calculations'] = defaultdict(int, data['user_calculations'])
                    if 'referral_bonuses' not in data:
                        data['referral_bonuses'] = defaultdict(int)
                    return data
            else:
                print(f"🆕 Файл статистики будет создан: {USER_STATS_FILE}")
        except Exception as e:
            print(f"❌ Ошибка загрузки статистики: {e}")
        
        return {
            'total_users': 0,
            'active_today': 0,
            'calculations_today': 0,
            'calculations_total': 0,
            'compatibility_total': 0,
            'user_calculations': defaultdict(int),
            'referral_bonuses': defaultdict(int),
            'last_reset': datetime.now().strftime('%Y-%m-%d')
        }
    
    def get_calculations_left(self, user_id):
        if user_id in ADMIN_IDS:
            return 999

        user_id_str = str(user_id)
        user_calcs = self.stats['user_calculations'].get(user_id_str, 0)
    
        base_calculations_left = max(0, MAX_CALCULATIONS - user_calcs)
    
        bonus_calculations = self.stats['referral_bonuses'].get(user_id_str, 0)
    
        total_calculations_left = base_calculations_left + bonus_calculations
    
        print(f"📊 Расчеты пользователя {user_id}:")
        print(f"   Использовано: {user_calcs}/{MAX_CALCULATIONS}")
        print(f"   Базовых осталось: {base_calculations_left}")
        print(f"   Бонусных: {bonus_calculations}")
        print(f"   Всего осталось: {total_calculations_left}")
    
        return total_calculations_left
        
    def can_make_calculation(self, user_id):
        if user_id in ADMIN_IDS:
            return True

        if subscription_manager.check_subscription(user_id):
            return True

        return self.get_calculations_left(user_id) > 0

    def add_referral_bonus(self, user_id):
        user_id_str = str(user_id)
        
        self.stats['referral_bonuses'][user_id_str] += 3
        self.save_stats()

        print(f"🎁 Бонус за реферала начислен пользователю {user_id}")
        print(f"📊 Бонусных расчетов: {self.stats['referral_bonuses'][user_id_str]}")
    
    def save_stats(self):
        with open(USER_STATS_FILE, 'w', encoding='utf-8') as f:
            stats_to_save = self.stats.copy()
            stats_to_save['user_calculations'] = dict(self.stats['user_calculations'])
            stats_to_save['referral_bonuses'] = dict(self.stats['referral_bonuses'])
            json.dump(stats_to_save, f, ensure_ascii=False, indent=2)
    
    def reset_daily_stats(self):
        today = datetime.now().strftime('%Y-%m-%d')
        if self.stats['last_reset'] != today:
            self.stats['active_today'] = 0
            self.stats['calculations_today'] = 0
            self.stats['last_reset'] = today
            self.save_stats()
    
    def add_user(self, user_id, username):
        self.reset_daily_stats()
        
        user_id_str = str(user_id)
        
        self.existing_users.add(user_id_str)
        
        if user_id_str not in self.stats['user_calculations']:
            self.stats['total_users'] += 1
            self.stats['active_today'] += 1
        
        if user_id_str not in self.stats['user_calculations']:
            self.stats['user_calculations'][user_id_str] = 0
        
        if user_id_str not in self.stats['referral_bonuses']:
            self.stats['referral_bonuses'][user_id_str] = 0
        
        self.save_stats()
    
    def add_calculation(self, user_id, calculation_type="personal"):
        self.reset_daily_stats()
        
        self.stats['calculations_total'] += 1
        self.stats['calculations_today'] += 1
        self.stats['user_calculations'][str(user_id)] = self.stats['user_calculations'].get(str(user_id), 0) + 1
        
        if calculation_type == "compatibility":
            self.stats['compatibility_total'] += 1
        
        self.save_stats()
    
    def get_stats(self):
        self.reset_daily_stats()
        return self.stats
    
    def get_user_stats(self, user_id):
        user_calcs = self.stats['user_calculations'].get(str(user_id), 0)
        bonus_calcs = self.stats['referral_bonuses'].get(str(user_id), 0)
        return {
            'user_calculations': user_calcs,
            'bonus_calculations': bonus_calcs,
            'calculations_left': self.get_calculations_left(user_id),
            'rank': self.get_user_rank(user_id)
        }
        
    def debug_user_stats(self, user_id):
        user_calcs = self.stats['user_calculations'].get(str(user_id), 0)
        bonus_calcs = self.stats['referral_bonuses'].get(str(user_id), 0)
        return {
            'user_id': user_id,
            'used_calculations': user_calcs,
            'bonus_calculations': bonus_calcs,
            'calculations_left': self.get_calculations_left(user_id),
            'max_calculations': MAX_CALCULATIONS
        }
    
    def get_user_rank(self, user_id):
        user_calcs = self.stats['user_calculations'].get(str(user_id), 0)
        all_calcs = sorted(self.stats['user_calculations'].values(), reverse=True)
        
        try:
            rank = all_calcs.index(user_calcs) + 1
            total_users = len(all_calcs)
            return f"{rank}/{total_users}"
        except ValueError:
            return "Н/Д"

user_stats = UserStats()

class ReferralSystem:
    def __init__(self):
        self.referral_data = self.load_referral_data()
    def load_referral_data(self):
        try:
            with open(REFERRAL_LINKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}  
    def save_referral_data(self):
        with open(REFERRAL_LINKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.referral_data, f, ensure_ascii=False, indent=2) 
    def generate_referral_link(self, user_id):
        code = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
        self.referral_data[code] = {
            'user_id': user_id,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'used_by': [],
            'uses_count': 0
        }
        self.save_referral_data()
        return f"https://t.me/{BOT_USERNAME}?start=ref_{code}"
    
    def get_user_referral_link(self, user_id):
        for code, data in self.referral_data.items():
            if data['user_id'] == user_id:
                return f"https://t.me/{BOT_USERNAME}?start=ref_{code}"
        return self.generate_referral_link(user_id)
    
    def get_referral_code_by_user(self, user_id):
        for code, data in self.referral_data.items():
            if data['user_id'] == user_id:
                return code
        return None
    
    def use_referral_link(self, code, new_user_id):
        if code in self.referral_data:
            if user_stats.is_existing_user(new_user_id):
                print(f"🚫 Пользователь {new_user_id} УЖЕ был в боте. Бонусы не начислены!")
                return False
        
            ref_owner_id = self.referral_data[code]['user_id']
            if ref_owner_id == new_user_id:
                print(f"🚫 Пользователь {new_user_id} пытается использовать свою ссылку")
                return False
        
            self.referral_data[code]['used_by'].append(new_user_id)
            self.referral_data[code]['uses_count'] += 1
            self.save_referral_data()
            user_stats.add_referral_bonus(ref_owner_id)
        
            print(f"✅ НОВЫЙ РЕФЕРАЛ: {new_user_id} → {ref_owner_id}")
            return True
    
        return False
    
    def get_referral_stats(self, user_id):
        """Статистика рефералов пользователя"""
        code = self.get_referral_code_by_user(user_id)
        if code and code in self.referral_data:
            data = self.referral_data[code]
            return {
                'link': f"https://t.me/{BOT_USERNAME}?start=ref_{code}",
                'uses_count': data['uses_count'],
                'referrals': len(data['used_by']),
                'code': code
            }
        return None
        
async def debug_referral_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Эта команда только для администраторов")
        return
    
    user_stats_info = user_stats.debug_user_stats(user.id)
    
    ref_stats = referral_system.get_referral_stats(user.id)
    
    test_link = referral_system.get_user_referral_link(user.id)
    
    text = f"🐛 *ОТЛАДКА РЕФЕРАЛЬНОЙ СИСТЕМЫ*\n\n"
    text += f"👤 *Ваша статистика:*\n"
    text += f"• Использовано расчетов: {user_stats_info['used_calculations']}\n"
    text += f"• Доступно расчетов: {user_stats_info['calculations_left']}\n"
    text += f"• Максимум: {user_stats_info['max_calculations']}\n\n"
    
    if ref_stats:
        text += f"🔗 *Реферальная статистика:*\n"
        text += f"• Приглашено: {ref_stats['referrals']}\n"
        text += f"• Использований: {ref_stats['uses_count']}\n"
        text += f"• Код: {ref_stats['code']}\n\n"
    else:
        text += f"❌ Нет реферальной статистики\n\n"
    
    text += f"🔗 *Ваша реферальная ссылка:*\n`{test_link}`\n\n"
    
    text += f"📊 *Общая статистика:*\n"
    text += f"• Всего пользователей: {user_stats.stats['total_users']}\n"
    text += f"• Всего расчетов: {user_stats.stats['calculations_total']}\n\n"
    
    text += f"🧪 *Тестирование:*\n"
    text += f"1. Используйте свою реферальную ссылку в инкогнито\n"
    text += f"2. После регистрации проверьте статистику снова\n"
    text += f"3. Должно стать: +2 доступных расчета\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')
        
async def check_referral_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    referral_stats = referral_system.get_referral_stats(user.id)
    user_calc_stats = user_stats.get_user_stats(user.id)
    
    text = f"📊 *ВАША РЕФЕРАЛЬНАЯ СТАТИСТИКА*\n\n"
    
    if referral_stats:
        text += f"🔗 *Реферальная ссылка:*\n"
        text += f"`{referral_stats['link']}`\n\n"
        text += f"👥 *Приглашено друзей:* {referral_stats['referrals']}\n"
        text += f"📎 *Использований ссылки:* {referral_stats['uses_count']}\n\n"
    else:
        ref_link = referral_system.get_user_referral_link(user.id)
        text += f"🔗 *Ваша реферальная ссылка:*\n"
        text += f"`{ref_link}`\n\n"
        text += f"👥 *Приглашено друзей:* 0\n\n"
    
    text += f"🔮 *Ваши расчеты:*\n"
    text += f"• Использовано: {user_calc_stats['user_calculations']}/{MAX_CALCULATIONS}\n"
    text += f"• Осталось: {user_calc_stats['calculations_left']}\n"
    text += f"• Рейтинг: {user_calc_stats['rank']}\n\n"
    
    text += "💡 *За каждого приглашенного друга вы получаете +3 бесплатных расчета!*"
    
    keyboard = [
        [InlineKeyboardButton("📤 Поделиться ссылкой", 
             url=f"https://t.me/share/url?url={referral_stats['link'] if referral_stats else ref_link}&text=🔮 Рассчитай свой Квадрат Пифагора и узнай все тайны личности!")],
        [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        
class SubscriptionManager:
    def __init__(self, bot=None):
        self.bot = bot
        self.init_subscriptions_table()
    
    def init_subscriptions_table(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subscriptions'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            print("🆕 Создаем таблицу subscriptions...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id INTEGER PRIMARY KEY,
                    is_active BOOLEAN DEFAULT FALSE,
                    start_date TIMESTAMP,
                    end_date TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            print("✅ Таблица подписок создана")
        else:
            print("✅ Таблица подписок уже существует")
            
        cursor.execute('SELECT COUNT(*) FROM subscriptions WHERE is_active = TRUE')
        active_subs = cursor.fetchone()[0]
        print(f"💎 Активных подписок: {active_subs}")
        
        conn.close()
    
    def create_subscription(self, user_id, duration_days=30):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        from datetime import datetime, timedelta
        
        start_date = datetime.now()
        end_date = start_date + timedelta(days=duration_days)
        
        cursor.execute('SELECT user_id FROM subscriptions WHERE user_id = ?', (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE subscriptions 
                SET is_active = TRUE, start_date = ?, end_date = ?
                WHERE user_id = ?
            ''', (start_date, end_date, user_id))
            action = "обновлена"
        else:
            cursor.execute('''
                INSERT INTO subscriptions (user_id, is_active, start_date, end_date) 
                VALUES (?, ?, ?, ?)
            ''', (user_id, True, start_date, end_date))
            action = "создана"
        
        conn.commit()
        conn.close()
        
        print(f"✅ Подписка {action} для {user_id} до {end_date}")
        
        self.log_subscription_activation(user_id, action, end_date)
    
    def log_subscription_activation(self, user_id, action, end_date):
        log_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'user_id': user_id,
            'action': action,
            'end_date': end_date.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        log_file = 'subscription_logs.json'
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            else:
                logs = []
            
            logs.append(log_entry)
            
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"❌ Ошибка записи лога: {e}")
    
    def check_subscription(self, user_id):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT is_active, end_date FROM subscriptions 
            WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return False
        
        is_active, end_date_str = result
        if is_active:
            from datetime import datetime
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M:%S.%f')
            if datetime.now() < end_date:
                return True
            else:
                self.deactivate_subscription(user_id)
        return False
        
    def send_expiration_notification(self, user_id):
        if self.bot:
            try:
                text = (
                    "💎 *ВАША ПОДПИСКА ЗАКОНЧИЛАСЬ*\n\n"
                    "⏰ Срок вашей подписки истек.\n\n"
                    "🔒 *Теперь ограничения:*\n"
                    "• 🔮 3 базовых расчета\n" 
                    "• 💞 3 расчета совместимости\n"
                    "• 📊 Нет доступа к истории\n\n"
                    "💡 *Чтобы вернуть полный доступ:*\n"
                    "Перейдите в Личный кабинет и продлите подписку!"
                )
            
                keyboard = [
                    [InlineKeyboardButton("👤 Перейти в Личный кабинет", callback_data="personal_cabinet")],
                    [InlineKeyboardButton("💎 Купить подписку", callback_data="buy_subscription")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
                async def send_msg():
                    try:
                        await self.bot.send_message(
                            chat_id=user_id,
                            text=text,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        print(f"📢 Уведомление об окончании подписки отправлено пользователю {user_id}")
                    except Exception as e:
                        print(f"❌ Не удалось отправить уведомление пользователю {user_id}: {e}")
            
                asyncio.create_task(send_msg())
            
            except Exception as e:
                print(f"❌ Ошибка при создании уведомления: {e}")
    
    def deactivate_subscription(self, user_id):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE subscriptions SET is_active = FALSE 
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()
        
        self.send_expiration_notification(user_id)

def save_calculation_history(user_id, calculation_type, name, birth_date, result_text, psychomatrix=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    short_result = result_text[:500] + "..." if len(result_text) > 500 else result_text
    
    psychomatrix_json = json.dumps(psychomatrix) if psychomatrix else None
    
    cursor.execute('''
        INSERT INTO calculation_history (user_id, calculation_type, name, birth_date, result_text, psychomatrix_json)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, calculation_type, name, birth_date, short_result, psychomatrix_json))
    
    conn.commit()
    conn.close()
    print(f"💾 История сохранена с психоматрицей: {user_id}")

@admin_only
async def payments_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    payment_stats = payment_tracker.get_payment_stats()
    
    text = "💰 *ИСТОРИЯ ПЛАТЕЖЕЙ*\n\n"
    
    text += f"📈 *Статистика:*\n"
    text += f"   ✅ Завершено: {payment_stats['completed']['count']}\n"
    text += f"   ⏳ Ожидает: {payment_stats['pending']['count']}\n"
    text += f"   💰 Сумма: {payment_stats['total_amount']} руб.\n\n"
    
    text += "💡 Используйте админ-панель для более детальной статистики."
    
    await update.message.reply_text(text, parse_mode='Markdown')

@admin_only
async def payments_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    payment_stats = payment_tracker.get_payment_stats()
    payment_history = payment_tracker.get_payment_history()
    
    text = "💰 *ИСТОРИЯ ПЛАТЕЖЕЙ*\n\n"
    
    text += f"📈 *Статистика:*\n"
    text += f"   ✅ Завершено: {payment_stats['completed']['count']}\n"
    text += f"   ⏳ Ожидает: {payment_stats['pending']['count']}\n"
    text += f"   💰 Сумма: {payment_stats['total_amount']} руб.\n\n"
    
    if not payment_history:
        text += "❌ Нет данных о платежах"
    else:
        text += "📋 *Последние платежи:*\n"
        for payment in payment_history[:10]:
            (payment_id, user_id, username, amount, method, status, 
             created_at, completed_at, admin_id) = payment
            
            status_icon = "✅" if status == 'completed' else "⏳"
            username_display = f"@{username}" if username else "без username"
            date_display = created_at[:10] if created_at else "нет даты"
            amount_display = f"{amount} руб." if amount else "0 руб."
            
            text += f"{status_icon} {user_id} ({username_display}) - {amount_display} ({date_display})\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="payments_history")],
        [InlineKeyboardButton("📊 Детальная статистика", callback_data="payment_stats_detail")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)

@admin_only
async def show_payment_stats_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    payment_stats = payment_tracker.get_payment_stats()
    payment_history = payment_tracker.get_payment_history()
    
    text = "📊 *ДЕТАЛЬНАЯ СТАТИСТИКА ПЛАТЕЖЕЙ*\n\n"
    
    text += f"📈 *Общая статистика:*\n"
    text += f"   ✅ Завершено: {payment_stats['completed']['count']}\n"
    text += f"   ⏳ Ожидает: {payment_stats['pending']['count']}\n"
    text += f"   💰 Общая сумма: {payment_stats['total_amount']} руб.\n\n"
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT payment_method, COUNT(*), SUM(amount) 
        FROM payments 
        WHERE status = 'completed'
        GROUP BY payment_method
    ''')
    
    text += "💳 *По методам оплаты (завершено):*\n"
    method_stats = cursor.fetchall()
    if method_stats:
        for method, count, amount in method_stats:
            amount_display = amount if amount else 0
            text += f"   • {method}: {count} платежей, {amount_display} руб.\n"
    else:
        text += "   ❌ Нет данных\n"
    text += "\n"
    
    cursor.execute('''
        SELECT user_id, username, amount, payment_method, completed_at 
        FROM payments 
        WHERE status = 'completed' 
        ORDER BY completed_at DESC 
        LIMIT 5
    ''')
    
    text += "🆕 *Последние завершенные платежи:*\n"
    recent_completed = cursor.fetchall()
    if recent_completed:
        for user_id, username, amount, method, completed_at in recent_completed:
            username_display = f"@{username}" if username else "без username"
            date_display = completed_at[:16] if completed_at else "нет даты"
            amount_display = f"{amount} руб." if amount else "0 руб."
            text += f"   • {user_id} ({username_display}) - {amount_display} ({date_display})\n"
    else:
        text += "   ❌ Нет завершенных платежей\n"
    
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📋 Общий список", callback_data="payments_history")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="payment_stats_detail")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
@admin_only
async def show_payment_stats_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    payment_stats = payment_tracker.get_payment_stats()
    payment_history = payment_tracker.get_payment_history()
    
    text = "📊 *ДЕТАЛЬНАЯ СТАТИСТИКА ПЛАТЕЖЕЙ*\n\n"
    
    text += f"📈 *Общая статистика:*\n"
    text += f"   ✅ Завершено: {payment_stats['completed']['count']}\n"
    text += f"   ⏳ Ожидает: {payment_stats['pending']['count']}\n"
    text += f"   💰 Общая сумма: {payment_stats['total_amount']} руб.\n\n"
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT payment_method, COUNT(*), SUM(amount) 
        FROM payments 
        WHERE status = 'completed'
        GROUP BY payment_method
    ''')
    
    text += "💳 *По методам оплаты (завершено):*\n"
    method_stats = cursor.fetchall()
    if method_stats:
        for method, count, amount in method_stats:
            amount_display = amount if amount else 0
            text += f"   • {method}: {count} платежей, {amount_display} руб.\n"
    else:
        text += "   ❌ Нет данных\n"
    text += "\n"
    
    cursor.execute('''
        SELECT user_id, username, amount, payment_method, completed_at 
        FROM payments 
        WHERE status = 'completed' 
        ORDER BY completed_at DESC 
        LIMIT 5
    ''')
    
    text += "🆕 *Последние завершенные платежи:*\n"
    recent_completed = cursor.fetchall()
    if recent_completed:
        for user_id, username, amount, method, completed_at in recent_completed:
            username_display = f"@{username}" if username else "без username"
            date_display = completed_at[:16] if completed_at else "нет даты"
            text += f"   • {user_id} ({username_display}) - {amount} руб. ({date_display})\n"
    else:
        text += "   ❌ Нет завершенных платежей\n"
    
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📋 Общий список", callback_data="payments_history")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="payment_stats_detail")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)

class ManualPaymentTracker:
    def __init__(self):
        self.pending_payments = {}
    
    def add_payment_request(self, user_id, username, amount=SUBSCRIPTION_PRICE, payment_method="manual"):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO payments (user_id, username, amount, payment_method, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, amount, payment_method, 'pending'))
        
        payment_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
   
        self.pending_payments[user_id] = {
            'payment_id': payment_id,
            'username': username,
            'amount': amount,
            'timestamp': time.time(),
            'user_info': f"ID: {user_id} | @{username}" if username else f"ID: {user_id}",
            'payment_method': payment_method
        }
        print(f"💰 Новый запрос оплаты сохранен в БД: {user_id} (@{username}) - ID: {payment_id}")
    
    def confirm_payment(self, user_id, admin_id=None):
        """Подтверждает оплату в БД"""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE payments 
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP, admin_id = ?
            WHERE user_id = ? AND status = 'pending'
        ''', (admin_id, user_id))
        
        rows_updated = cursor.rowcount
        conn.commit()
        conn.close()
        
        if user_id in self.pending_payments:
            user_info = self.pending_payments[user_id]['user_info']
            subscription_manager.create_subscription(user_id)
            del self.pending_payments[user_id]
            print(f"✅ Платеж подтвержден в БД: {user_info} - обновлено записей: {rows_updated}")
            return True
        return False
    
    def get_pending_payments_from_db(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, username, amount, payment_method, created_at 
            FROM payments 
            WHERE status = 'pending' 
            ORDER BY created_at DESC
        ''')
        
        pending_payments = {}
        for row in cursor.fetchall():
            user_id, username, amount, payment_method, created_at = row
            pending_payments[user_id] = {
                'username': username,
                'amount': amount,
                'user_info': f"ID: {user_id} | @{username}" if username else f"ID: {user_id}",
                'payment_method': payment_method,
                'created_at': created_at
            }
        
        conn.close()
        return pending_payments
    
    def get_payment_history(self, user_id=None):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        if user_id:
            cursor.execute('''
                SELECT id, user_id, username, amount, payment_method, status, 
                       created_at, completed_at, admin_id 
                FROM payments 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT id, user_id, username, amount, payment_method, status, 
                       created_at, completed_at, admin_id 
                FROM payments 
                ORDER BY created_at DESC 
                LIMIT 100
            ''')
        
        payments = cursor.fetchall()
        conn.close()
        
        print(f"📊 Получено записей из БД: {len(payments)}")
        for payment in payments:
            print(f"   💰 Платеж: {payment}")
        
        return payments
    
    def get_pending_list(self):
        db_payments = self.get_pending_payments_from_db()
        
        for user_id, payment_data in db_payments.items():
            if user_id not in self.pending_payments:
                self.pending_payments[user_id] = payment_data
        
        return self.pending_payments

    def get_payment_stats(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT status, COUNT(*), SUM(amount) 
            FROM payments 
            GROUP BY status
        ''')
        
        stats = {
            'completed': {'count': 0, 'amount': 0},
            'pending': {'count': 0, 'amount': 0},
            'total_amount': 0
        }
        
        for status, count, amount in cursor.fetchall():
            if status == 'completed':
                stats['completed']['count'] = count
                stats['completed']['amount'] = amount if amount else 0
            elif status == 'pending':
                stats['pending']['count'] = count
                stats['pending']['amount'] = amount if amount else 0
        
        stats['total_amount'] = stats['completed']['amount']
        
        conn.close()
        return stats

payment_tracker = ManualPaymentTracker()

referral_system = ReferralSystem()

MAIN_MENU = 0
WAITING_SELF_NAME = 1
WAITING_SELF_DATE = 2
WAITING_PARTNER1_NAME = 3
WAITING_PARTNER1_DATE = 4
WAITING_PARTNER2_NAME = 5
WAITING_PARTNER2_DATE = 6

user_states = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    is_new_referral = False
    if context.args and context.args[0].startswith('ref_'):
        ref_code = context.args[0][4:]
        is_new_referral = referral_system.use_referral_link(ref_code, user.id)
    
    user_stats.add_user(user.id, user.username)
    
    if is_new_referral:
        await update.message.reply_text(
            "🎉 Ты пришел по ссылке друга!\n"
            "Владелец ссылки получил +2 бесплатных расчета в подарок",
            parse_mode='Markdown'
        )
    
    keyboard = [
        [InlineKeyboardButton("🔮 Рассчитать психоматрицу", callback_data="self_calculation")],
        [InlineKeyboardButton("💞 Совместимость партнеров", callback_data="compatibility_calculation")],
        [InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🧮 *🅿️🅸🅵🅰️* - нумерология для:\n"
        "✔️ Понимания своих сильных сторон\n" 
        "✔️ Раскрытия скрытых талантов\n"
        "✔️ Анализа совместимости с другими\n"
        "✔️ Поиска своего предназначения\n\n"
        "Выберите действие:"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)
    
async def handle_visualize_matrix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, birth_date, psychomatrix_json, calculation_type 
            FROM calculation_history 
            WHERE user_id = ? AND psychomatrix_json IS NOT NULL
            ORDER BY created_at DESC 
            LIMIT 1
        ''', (user.id,))
        
        last_calculation = cursor.fetchone()
        conn.close()
        
        if not last_calculation:
            keyboard = [
                [InlineKeyboardButton("🔮 Сделать расчет", callback_data="self_calculation")],
                [InlineKeyboardButton("🔙 В кабинет", callback_data="personal_cabinet")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "❌ *Нет данных для визуализации*\n\n"
                "У вас нет сохраненных расчетов с психоматрицей.\n"
                "Сначала сделайте расчет вашего Квадрата Пифагора.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return
        
        name, birth_date, psychomatrix_json, calculation_type = last_calculation
        
        print(f"🔍 Данные для визуализации: {name}, {birth_date}, тип: {calculation_type}")
        
        try:
            psychomatrix_data = json.loads(psychomatrix_json)
            print(f"🔍 Психоматрица данные: {psychomatrix_data}")
            
            keyboard = [
                [InlineKeyboardButton("🔙 В кабинет", callback_data="personal_cabinet")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if calculation_type == 'personal':
                psychomatrix = psychomatrix_data
                
                temp_filename = f"temp_viz_{user.id}.png"
                viz_img = psychomatrix_viz.create_psychomatrix_image(psychomatrix, name, birth_date)
                
                if viz_img:
                    viz_img.save(temp_filename)
                    
                    with open(temp_filename, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=photo,
                            caption=f"🔮 *Визуальная психоматрица для {name}*\n\n"
                                   f"📅 Дата рождения: {birth_date}\n\n"
                                   f"*Расшифровка цветов:*\n"
                                   f"• 🟢 Зеленый - сильная черта (3+ цифры)\n"
                                   f"• 🔵 Голубой - нормальное развитие (1-2 цифры)\n"
                                   f"• 🔴 Красный - слабая черта (0 цифр)",
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                    
                    os.remove(temp_filename)
                    print(f"✅ Личная визуализация отправлена для пользователя {user.id}")
                else:
                    await query.message.reply_text(
                        "❌ Не удалось создать визуализацию. Попробуйте позже.",
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
                    
            elif calculation_type == 'compatibility':
                if isinstance(psychomatrix_data, dict) and 'partner1' in psychomatrix_data and 'partner2' in psychomatrix_data:
                    psychomatrix1 = psychomatrix_data['partner1']
                    psychomatrix2 = psychomatrix_data['partner2']
                    
                    if ' и ' in name:
                        names = name.replace('Совместимость: ', '').split(' и ')
                        name1 = names[0] if len(names) > 0 else "Партнер 1"
                        name2 = names[1] if len(names) > 1 else "Партнер 2"
                    else:
                        name1 = "Партнер 1"
                        name2 = "Партнер 2"
                    
                    if ' + ' in birth_date:
                        dates = birth_date.split(' + ')
                        date1 = dates[0] if len(dates) > 0 else birth_date
                        date2 = dates[1] if len(dates) > 1 else birth_date
                    else:
                        date1 = birth_date
                        date2 = birth_date
                    
                    temp_filename1 = f"temp_viz_{user.id}_1.png"
                    viz_img1 = psychomatrix_viz.create_psychomatrix_image(psychomatrix1, name1, date1)
                    
                    if viz_img1:
                        viz_img1.save(temp_filename1)
                        with open(temp_filename1, 'rb') as photo:
                            await context.bot.send_photo(
                                chat_id=query.message.chat_id,
                                photo=photo,
                                caption=f"🔮 *Психоматрица {name1}*\n📅 {date1}",
                                parse_mode='Markdown'
                            )
                        os.remove(temp_filename1)
                    
                    temp_filename2 = f"temp_viz_{user.id}_2.png"
                    viz_img2 = psychomatrix_viz.create_psychomatrix_image(psychomatrix2, name2, date2)
                    
                    if viz_img2:
                        viz_img2.save(temp_filename2)
                        with open(temp_filename2, 'rb') as photo:
                            await context.bot.send_photo(
                                chat_id=query.message.chat_id,
                                photo=photo,
                                caption=f"🔮 *Психоматрица {name2}*\n📅 {date2}\n\n"
                                       f"*Расшифровка цветов:*\n"
                                       f"• 🟢 Зеленый - сильная черта (3+ цифры)\n"
                                       f"• 🔵 Голубой - нормальное развитие (1-2 цифры)\n"
                                       f"• 🔴 Красный - слабая черта (0 цифр)",
                                parse_mode='Markdown',
                                reply_markup=reply_markup
                            )
                        os.remove(temp_filename2)
                    
                    print(f"✅ Визуализация совместимости отправлена для пользователя {user.id}")
                else:
                    await query.message.reply_text(
                        "❌ Ошибка формата данных совместимости.",
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
            else:
                await query.message.reply_text(
                    "❌ Неизвестный тип расчета.",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON: {e}")
            
            keyboard = [
                [InlineKeyboardButton("🔮 Сделать расчет", callback_data="self_calculation")],
                [InlineKeyboardButton("🔙 В кабинет", callback_data="personal_cabinet")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "❌ Ошибка при чтении данных расчета.\n"
                "Пожалуйста, сделайте новый расчет.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
    except Exception as e:
        print(f"❌ Критическая ошибка в handle_visualize_matrix: {e}")
        import traceback
        traceback.print_exc()
        
        keyboard = [
            [InlineKeyboardButton("🔮 Сделать расчет", callback_data="self_calculation")],
            [InlineKeyboardButton("🔙 В кабинет", callback_data="personal_cabinet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "❌ Произошла ошибка при создании визуализации.\n"
            "Попробуйте сделать новый расчет.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    if query.data == "visualize_matrix":
        await handle_visualize_matrix(update, context)
        return
        
    elif query.data == "personal_cabinet":
        await show_personal_cabinet(update, context)
        return
    
    if query.data == "self_calculation":
        if not user_stats.can_make_calculation(user.id):
            keyboard = [
                [InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "❌ *Лимит расчетов исчерпан!*\n\n"
                "Вы использовали все доступные расчеты. "
                "Чтобы получить больше расчетов:\n\n"
                "1. Перейдите в *Личный кабинет*\n"
                "2. Поделитесь своей реферальной ссылкой\n"
                "3. За каждого друга получите +3 расчета\n\n"
                "Бонусы начисляются автоматически!",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return
            
        await query.message.reply_text(
            "🔮 *РАСЧЕТ ВАШЕГО КВАДРАТА ПИФАГОРА*\n\n"
            "Введите имя:",
            parse_mode='Markdown'
        )
        user_states[user.id] = WAITING_SELF_NAME
        
    elif query.data == "compatibility_calculation":
        if not user_stats.can_make_calculation(user.id):
            keyboard = [
                [InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "❌ *Лимит расчетов исчерпан!*\n\n"
                "Вы использовали все доступные расчетов. "
                "Чтобы получить больше расчетов:\n\n"
                "1. Перейдите в *Личный кабинет*\n"
                "2. Поделитесь своей реферальной ссылкой\n"
                "3. За каждого друга получите +3 расчета\n\n"
                "Бонусы начисляются автоматически!",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return
            
        await query.message.reply_text(
            "💞 *РАСЧЕТ СОВМЕСТИМОСТИ*\n\n"
            "Введите имя первого человека:",
            parse_mode='Markdown'
        )
        user_states[user.id] = WAITING_PARTNER1_NAME
        
    elif query.data == "buy_subscription":
        await choose_payment_method(update, context)
        
    elif query.data == "choose_payment":
        await choose_payment_method(update, context)
        
    elif query.data == "pay_tbank":
        await handle_tbank_payment(update, context)
        
    elif query.data == "pay_telegram":
        await handle_telegram_payment(update, context)
        
    elif query.data == "check_manual_payment":
        await check_manual_payment(update, context)
              
    elif query.data == "view_history":
        await show_calculation_history(update, context)
    
    elif query.data.startswith("history_page_"):
        await handle_history_page(update, context)
    
    elif query.data.startswith("history_detail_"):
        await show_calculation_details(update, context)
    
    elif query.data.startswith("visualize_history_"):
        await visualize_history_matrix(update, context)    
        
    elif query.data == "personal_cabinet":
        await show_personal_cabinet(update, context)
        
    elif query.data == "check_payment_status":
        await check_payment_status(update, context)
        
    elif query.data == "payments_history":
        await payments_command_callback(update, context)
        
    elif query.data == "payment_stats_detail":
        await show_payment_stats_detail(update, context)
        
    elif query.data == "new_calculation":
        if not user_stats.can_make_calculation(user.id):
            keyboard = [
                [InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "❌ *Лимит расчетов исчерпан!*\n\n"
                "Вы использовали все доступные расчетов. "
                "Чтобы получить больше расчетов:\n\n"
                "1. Перейдите в *Личный кабинет*\n"
                "2. Поделитесь своей реферальной ссылкой\n"
                "3. За каждого друга получите +3 расчета\n\n"
                "Бонусы начисляются автоматически!",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return
            
        await query.message.reply_text(
            "🔄 *НОВЫЙ РАСЧЕТ*\n\n"
            "Введите имя:",
            parse_mode='Markdown'
        )
        user_states[user.id] = WAITING_SELF_NAME
        
    elif query.data == "back_to_menu":
        keyboard = [
            [InlineKeyboardButton("🔮 Рассчитать дату", callback_data="self_calculation")],
            [InlineKeyboardButton("💞 Рассчитать совместимость", callback_data="compatibility_calculation")],
            [InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "🧮 *ГЛАВНОЕ МЕНЮ*\n\n"
            "Выберите действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        user_states[user.id] = MAIN_MENU
        
    elif query.data.startswith("confirm_send_") or query.data == "cancel_send":
        await handle_broadcast_confirmation(update, context)
    
    elif query.data == "admin_refresh":
        await admin_panel(update, context)
        
    elif query.data == "stats":
        await stats_command(update, context)
        
    elif query.data == "broadcast":
        if user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Эта команда только для администраторов")
            return

        context.user_data['waiting_for_broadcast'] = True
        
        await query.message.reply_text(
            "📢 *СОЗДАНИЕ РАССЫЛКИ*\n\n"
            "Отправьте сообщение которое хотите разослать всем пользователям.\n\n"
            "*Формат:*\n"
            "• Текст сообщения\n"
            "• Или фото/картинку с подписью\n\n"
            "❌ *Для отмены:* /cancel",
            parse_mode='Markdown'
        )
        
    elif query.data == "activate_sub":
        if user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Эта команда только для администраторов")
            return
        
        pending_payments = payment_tracker.get_pending_list()
        
        if not pending_payments:
            await query.message.reply_text(
                "💎 *АКТИВАЦИЯ ПОДПИСКИ*\n\n"
                "⭕ Нет ожидающих оплаты пользователей\n\n"
                "Для ручной активации используйте:\n"
                "`/activate user_id`\n\n"
                "Пример:\n"
                "`/activate 123456789`",
                parse_mode='Markdown'
            )
            return
            
            text = "💎 *АКТИВАЦИЯ ПОДПИСКИ*\n\n"
            text += "📋 *Ожидающие оплаты:*\n\n"
        
            keyboard = []
        
        text = "💎 *АКТИВАЦИЯ ПОДПИСКИ*\n\n"
        text += f"🔍 Отладка: найдено {len(pending_payments)} ожидающих платежей\n\n"
        text += "📋 *Ожидающие оплаты:*\n\n"
    
        keyboard = []
    
        if pending_payments:
            for i, (user_id, data) in enumerate(pending_payments.items(), 1):
                user_info = data['user_info']
                amount = data['amount']
        
                text += f"{i}. {user_info} - {amount} руб\n"
                text += f"   Активация: `/activate {user_id}`\n"
                text += f"   Отмена: `/cancel_activation {user_id}`\n\n"
        
                # Две кнопки в одном ряду - Активировать и Отменить
                keyboard.append([
                    InlineKeyboardButton("✅ Активировать", callback_data=f"quick_activate_{user_id}"),
                    InlineKeyboardButton("❌ Отменить", callback_data=f"quick_cancel_{user_id}")
                ])
    
            text += "⚡ *Быстрая активация:*\nНажмите на кнопку ниже для мгновенной активации\n\n"
            text += "📝 *Ручная активация:*\nИспользуйте команды выше"
        else:
            text += "❌ Нет ожидающих платежей для отображения"
        
        keyboard.append([InlineKeyboardButton("🔄 Обновить список", callback_data="activate_sub")])
        keyboard.append([InlineKeyboardButton("🔙 В админ-панель", callback_data="admin_refresh")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        
    elif query.data.startswith("quick_activate_"):
        if user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Эта команда только для администраторов")
            return
    
        try:
            target_user_id = int(query.data.replace("quick_activate_", ""))
    
            print(f"🔍 АКТИВАЦИЯ ПОДПИСКИ:")
            print(f"   👤 Админ: {user.id}")
            print(f"   🎯 Целевой пользователь: {target_user_id}")
    
            # 1. Создаем подписку
            subscription_manager.create_subscription(target_user_id)
            print(f"   ✅ Подписка создана")
    
            # 2. Подтверждаем платеж
            payment_confirmed = payment_tracker.confirm_payment(target_user_id, admin_id=user.id)
            print(f"   ✅ Платеж подтвержден: {payment_confirmed}")
    
            # 3. Получаем информацию о пользователе
            user_info = f"ID: {target_user_id}"
            try:
                target_user = await context.bot.get_chat(target_user_id)
                if target_user.username:
                    user_info = f"@{target_user.username} (ID: {target_user_id})"
                elif target_user.first_name:
                    user_info = f"👤 {target_user.first_name} (ID: {target_user_id})"
                print(f"   👤 Инфо о пользователе получена: {user_info}")
            except Exception as e:
                print(f"   ⚠️ Не удалось получить инфо о пользователе: {e}")
    
            # 4. Сообщение админу
            await query.message.reply_text(
                f"✅ *ПОДПИСКА АКТИВИРОВАНА!*\n\n"
                f"👤 {user_info}\n"
                f"💰 Статус: ✅ Активная подписка (30 дней)\n\n"
                f"⚡ Активация выполнена мгновенно!",
                parse_mode='Markdown'
            )
            print(f"   ✅ Сообщение админу отправлено")
    
            # 5. Сообщение пользователю - УЛУЧШЕННАЯ ВЕРСИЯ
            try:
                keyboard = [
                    [InlineKeyboardButton("📊 Главное меню", callback_data="back_to_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
        
                user_message = await context.bot.send_message(
                    chat_id=target_user_id,
                    text="🎉 *ВАША ПОДПИСКА АКТИВИРОВАНА!*\n\n"
                        "✅ Оплата подтверждена администратором!\n\n"
                        "✨ *Теперь у вас:*\n"
                        "• 🔮 Неограниченные расчеты\n"
                        "• 💞 Неограниченная совместимость\n" 
                        "• 📊 Приоритетная поддержка\n\n"
                        "Приятного использования! 🚀",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                print(f"   ✅ Сообщение пользователю отправлено. ID сообщения: {user_message.message_id}")
            
            except Exception as e:
                print(f"   ❌ НЕ УДАЛОСЬ отправить сообщение пользователю {target_user_id}: {e}")
                # Подробная диагностика ошибки
                error_msg = str(e)
                if "bot was blocked" in error_msg.lower():
                    print(f"   🚫 Пользователь {target_user_id} заблокировал бота")
                    await query.message.reply_text(
                        f"⚠️ *Пользователь заблокировал бота!*\n\n"
                        f"Сообщение не доставлено пользователю {target_user_id}",
                        parse_mode='Markdown'
                    )
                elif "chat not found" in error_msg.lower():
                    print(f"   ❓ Пользователь {target_user_id} никогда не писал боту")
                    await query.message.reply_text(
                        f"⚠️ *Пользователь никогда не писал боту!*\n\n"
                        f"Сообщение не доставлено пользователю {target_user_id}\n"
                        f"Пользователь должен сначала написать боту /start",
                        parse_mode='Markdown'
                    )
                else:
                    print(f"   🔧 Другая ошибка: {error_msg}")
                    await query.message.reply_text(
                        f"⚠️ *Ошибка отправки пользователю:*\n{error_msg}",
                        parse_mode='Markdown'
                    )
    
            await activate_sub_callback(update, context)
    
        except Exception as e:
            print(f"   ❌ Ошибка активации: {e}")
            await query.message.reply_text(
                f"❌ *ОШИБКА АКТИВАЦИИ*\n\n"
                f"Не удалось активировать подписку: {str(e)}",
                parse_mode='Markdown'
            )
            
    elif query.data.startswith("quick_cancel_"):
        if user.id not in ADMIN_IDS:
            await query.message.reply_text("❌ Эта команда только для администраторов")
            return

        try:
            target_user_id = int(query.data.replace("quick_cancel_", ""))

            pending_payments = payment_tracker.get_pending_list()
        
            if target_user_id not in pending_payments:
                await query.answer("❌ Платеж не найден", show_alert=True)
                return
        
            user_info = pending_payments[target_user_id]['user_info']
        
            if target_user_id in payment_tracker.pending_payments:
                del payment_tracker.pending_payments[target_user_id]
        
            # Помечаем как отменено в БД
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE payments 
                SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP, admin_id = ?
                WHERE user_id = ? AND status = 'pending'
            ''', (user.id, target_user_id))
            conn.commit()
            conn.close()
        
            try:
                keyboard = [
                    [InlineKeyboardButton("💎 Купить подписку", callback_data="buy_subscription")],
                    [InlineKeyboardButton("📞 Поддержка", url=f"https://t.me/{YOUR_TELEGRAM.replace('@', '')}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text="❌ *АКТИВАЦИЯ ОТМЕНЕНА*\n\n"
                         "⏰ Ваш запрос на активацию подписки был отменен администратором.\n\n"
                         "💡 *Возможные причины:*\n"
                         "• Платеж не поступил на счет\n"
                         "• Неверная сумма перевода\n"
                         "📝 *Что делать:*\n"
                         "1. Проверьте правильность перевода\n"
                         "2. Убедитесь, что сумма соответствует указанной\n"
                         "3. Пришлите чек в поддержку\n"
                         "4. При проблемах свяжитесь с поддержкой\n\n"
                         "Мы готовы помочь! 🤝",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            
                await query.answer(f"✅ Активация отменена для {target_user_id}", show_alert=True)
            
            except Exception as e:
                error_msg = str(e)
                await query.answer(f"✅ Отменено (уведомление не отправлено)", show_alert=True)
        
            # Обновляем список
            await activate_sub_callback(update, context)

        except Exception as e:
            await query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
            
@admin_only
async def test_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тест отправки сообщения пользователю"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /test_msg USER_ID")
        return
        
    try:
        target_user_id = int(context.args[0])
        
        print(f"🔍 ТЕСТ ОТПРАВКИ СООБЩЕНИЯ:")
        print(f"   👤 Админ: {update.effective_user.id}")
        print(f"   🎯 Целевой пользователь: {target_user_id}")
        
        # Пробуем отправить тестовое сообщение
        test_msg = await context.bot.send_message(
            chat_id=target_user_id,
            text="🔍 *ТЕСТОВОЕ СООБЩЕНИЕ ОТ АДМИНА*\n\n"
                 "Если вы видите это сообщение, значит бот может вам писать!",
            parse_mode='Markdown'
        )
        
        print(f"   ✅ Тестовое сообщение отправлено. ID: {test_msg.message_id}")
        await update.message.reply_text(f"✅ Тестовое сообщение отправлено пользователю {target_user_id}")
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Ошибка тестирования: {error_msg}")
        
        if "bot was blocked" in error_msg.lower():
            await update.message.reply_text(f"❌ Пользователь {target_user_id} ЗАБЛОКИРОВАЛ бота")
        elif "chat not found" in error_msg.lower():
            await update.message.reply_text(f"❌ Пользователь {target_user_id} никогда не писал боту")
        else:
            await update.message.reply_text(f"❌ Ошибка: {error_msg}")
        
async def activate_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    print(f"🔍 АКТИВАЦИЯ ПОДПИСКИ - пользователь {user.id}")
    
    if user.id not in ADMIN_IDS:
        print("❌ Не админ")
        return
    
    if query.data == "back_to_admin":
        await admin_panel(update, context)
        return    
    
    pending_payments = payment_tracker.get_pending_list()
    print(f"🔍 Найдено ожидающих платежей: {len(pending_payments)}")
    
    if not pending_payments:
        text = (
            "💎 *АКТИВАЦИЯ ПОДПИСКИ*\n\n"
            "✅ Все ожидающие обработаны!\n\n"
            "⭕ Нет новых ожидающих оплаты\n\n"
            "Для ручной активации используйте:\n"
            "`/activate user_id`"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить список", callback_data="activate_sub")],
            [InlineKeyboardButton("🔙 Назад в админ-панель", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        return
        
    text = "💎 *АКТИВАЦИЯ ПОДПИСКИ*\n\n"
    text += f"🔍 Отладка: найдено {len(pending_payments)} ожидающих платежей\n\n"
    text += "📋 *Ожидающие оплаты:*\n\n"
    
    keyboard = []
    
    if pending_payments:
        for i, (user_id, data) in enumerate(pending_payments.items(), 1):
            user_info = data['user_info']
            amount = data['amount']
        
            text += f"{i}. {user_info} - {amount} руб\n"
            text += f"   Активация: `/activate {user_id}`\n"
            text += f"   Отмена: `/cancel_activation {user_id}`\n\n"
        
            # Две кнопки в одном ряду - Активировать и Отменить
            keyboard.append([
                InlineKeyboardButton("✅ Активировать", callback_data=f"quick_activate_{user_id}"),
                InlineKeyboardButton("❌ Отменить", callback_data=f"quick_cancel_{user_id}")
            ])
    
        text += "⚡ *Быстрая активация:*\nНажмите на кнопку ниже для мгновенной активации\n\n"
        text += "📝 *Ручная активация:*\nИспользуйте команды выше"
    else:
        text += "❌ Нет ожидающих платежей для отображения"
    
    keyboard.append([InlineKeyboardButton("🔄 Обновить список", callback_data="activate_sub")])
    keyboard.append([InlineKeyboardButton("🔙 Назад в админ-панель", callback_data="back_to_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
async def debug_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 Ваш ID: {user.id}\n"
        f"👑 Админы: {ADMIN_IDS}\n"
        f"✅ Вы админ: {user.id in ADMIN_IDS}"
    )

@admin_only    
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        message = query.message
        is_callback = True
    else:
        user = update.effective_user
        message = update.message
        is_callback = False
    
    pending_payments = payment_tracker.get_pending_list()
    
    text = "👑 *ПАНЕЛЬ АДМИНИСТРАТОРА*\n\n"
    text += f"⏳ *Ожидают оплаты:* {len(pending_payments)}\n\n"
    
    if pending_payments:
        text += "📋 *Список ожидающих:*\n"
        for user_id, data in pending_payments.items():
            text += f"• {data['user_info']} - {data['amount']} руб\n"
    else:
        text += "✅ Нет ожидающих оплат\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("💰 Платежи", callback_data="payments_history")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")],
        [InlineKeyboardButton("💎 Активировать подписку", callback_data="activate_sub")],
        
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_callback:
        await message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

@admin_only        
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        user = update.callback_query.from_user
        message = update.callback_query.message
        is_callback = True
    else:
        user = update.effective_user
        message = update.message
        is_callback = False
    
    stats = user_stats.get_stats()
    text = (
        "📊 *СТАТИСТИКА БОТА*\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"🟢 Активных сегодня: {stats['active_today']}\n"
        f"🔮 Расчетов сегодня: {stats['calculations_today']}\n"
        f"📈 Всего расчетов: {stats['calculations_total']}\n"
        f"💞 Совместимостей: {stats['compatibility_total']}\n"
        f"📅 Последний сброс: {stats['last_reset']}"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_callback:
        await message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def show_personal_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    user_stats_info = user_stats.get_user_stats(user.id)
    calculations_left = user_stats_info['calculations_left']
    user_calcs = user_stats_info['user_calculations']
    
    referral_stats = referral_system.get_referral_stats(user.id)
    
    has_subscription = subscription_manager.check_subscription(user.id)
    
    text = f"👤 *ЛИЧНЫЙ КАБИНЕТ* {user.first_name}\n\n"
    
    text += f"📊 *Ваша статистика:*\n"
    text += f"• Использовано расчетов: {user_calcs}\n"
    text += f"• Доступно расчетов: {calculations_left}\n"
    
    if has_subscription:
        text += f"• 💎 *Статус:* ✅ Активная подписка\n\n"
    else:
        text += f"• 💎 *Статус:* ❌ Нет подписки\n\n"
    
    if referral_stats:
        text += f"🔗 *Реферальная программа:*\n"
        text += f"• Приглашено друзей: {referral_stats['referrals']}\n"
        text += f"• Всего использований ссылки: {referral_stats['uses_count']}\n"
        text += f"• 🎁 Получено бонусов: {referral_stats['referrals'] * 3} расчетов\n\n"
        
        text += f"📎 *Ваша реферальная ссылка:*\n"
        text += f"`{referral_stats['link']}`\n\n"
    else:
        ref_link = referral_system.get_user_referral_link(user.id)
        text += f"🔗 *Реферальная программа:*\n"
        text += f"• Приглашено друзей: 0\n"
        text += f"• 🎁 Получено бонусов: 0 расчетов\n\n"
        text += f"📎 *Ваша реферальная ссылка:*\n"
        text += f"`{ref_link}`\n\n"
    
    text += "💡 *Как получить больше расчетов:*\n"
    text += "1. Поделитесь своей реферальной ссылкой\n"
    text += "2. За каждого друга получите +3 расчета\n"
    text += f"3. *Купите подписку* - неограниченный доступ за {SUBSCRIPTION_PRICE} руб!\n\n"
    text += "📢 *Действия:*"
    share_link = referral_stats['link'] if referral_stats else referral_system.get_user_referral_link(user.id)
    keyboard = []
    
    if not has_subscription:
        keyboard.append([InlineKeyboardButton(f"💎 Купить подписку ({SUBSCRIPTION_PRICE} руб)", callback_data="buy_subscription")])
    else:
        keyboard.append([InlineKeyboardButton("📊 История расчетов", callback_data="view_history")])
        
    keyboard.append([InlineKeyboardButton("🖼️ Визуализация психоматрицы", callback_data="visualize_matrix")])
    
    keyboard.append([InlineKeyboardButton("📤 Поделиться ссылкой", 
                     url=f"https://t.me/share/url?url={share_link}&text=🔮 Рассчитай свой Квадрат Пифагора и узнай все тайны личности!")])
    keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        text, 
        parse_mode='Markdown', 
        reply_markup=reply_markup
    )

async def show_calculation_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if not subscription_manager.check_subscription(user.id):
        keyboard = [
            [InlineKeyboardButton("💎 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "❌ *ДОСТУП ЗАБЛОКИРОВАН*\n\n"
            "📊 История расчетов доступна только пользователям с активной подпиской.\n\n"
            "💎 *Приобретите подписку,* чтобы получить доступ к:\n"
            "• 📊 Полной истории ваших расчетов\n"
            "• 🔮 Неограниченным новым расчетам\n"
            "• 💞 Неограниченной совместимости\n\n"
            f"💰 Всего {SUBSCRIPTION_PRICE} руб./месяц",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT calculation_type, name, birth_date, result_text, created_at, psychomatrix_json
        FROM calculation_history 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 20
    ''', (user.id,))
    
    history_records = cursor.fetchall()
    conn.close()
    
    if not history_records:
        keyboard = [
            [InlineKeyboardButton("🔮 Сделать расчет", callback_data="self_calculation")],
            [InlineKeyboardButton("🔙 В кабинет", callback_data="personal_cabinet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "📊 *ИСТОРИЯ РАСЧЕТОВ*\n\n"
            "📭 У вас пока нет сохраненных расчетов.\n\n"
            "Сделайте свой первый расчет, и он появится здесь!",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
    
    page = context.user_data.get('history_page', 0)
    records_per_page = 5
    total_pages = (len(history_records) + records_per_page - 1) // records_per_page
    
    start_idx = page * records_per_page
    end_idx = start_idx + records_per_page
    page_records = history_records[start_idx:end_idx]
    
    text = f"📊 *ИСТОРИЯ ВАШИХ РАСЧЕТОВ* • Страница {page + 1}/{total_pages}\n\n"
    
    for i, record in enumerate(page_records, start_idx + 1):
        calc_type, name, birth_date, result_text, created_at, psychomatrix_json = record
        
        if calc_type == 'personal':
            emoji = "🔮"
            type_text = "Личный расчет"
        else:
            emoji = "💞" 
            type_text = "Совместимость"
        
        created_date = created_at.split(' ')[0] if created_at else "неизвестно"
        
        text += f"{emoji} *{type_text}* ({created_date})\n"
        text += f"   👤 {name}\n"
        text += f"   📅 {birth_date}\n\n"
    
    keyboard = []
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"history_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"history_page_{page+1}"))    
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.extend([
        [InlineKeyboardButton("🔄 Обновить", callback_data="view_history")],
        [InlineKeyboardButton("🔙 В кабинет", callback_data="personal_cabinet")]
    ])    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def handle_history_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split('_')[-1])
    context.user_data['history_page'] = page
    await show_calculation_history(update, context)

async def show_calculation_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    record_id = int(query.data.split('_')[-1])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT calculation_type, name, birth_date, result_text, created_at, psychomatrix_json
        FROM calculation_history 
        WHERE id = ? AND user_id = ?
    ''', (record_id, user.id))
    
    record = cursor.fetchone()
    conn.close()
    
    if not record:
        await query.message.reply_text(
            "❌ Запись не найдена или у вас нет доступа к ней.",
            parse_mode='Markdown'
        )
        return
    
    calc_type, name, birth_date, result_text, created_at, psychomatrix_json = record

    if calc_type == 'personal':
        title = f"🔮 ЛИЧНЫЙ РАСЧЕТ: {name}"
    else:
        title = f"💞 СОВМЕСТИМОСТЬ: {name}"
    
    text = f"{title}\n\n"
    text += f"📅 Дата рождения: {birth_date}\n"
    text += f"🕐 Дата расчета: {created_at}\n\n"
    
    if len(result_text) > 1500:
        preview_text = result_text[:1500] + "...\n\n💡 *Сообщение обрезано. Полный текст доступен в оригинальном расчете.*"
    else:
        preview_text = result_text
    
    text += preview_text
    
    keyboard = [
        [InlineKeyboardButton("🖼️ Показать психоматрицу", callback_data=f"visualize_history_{record_id}")],
        [InlineKeyboardButton("📊 Назад к истории", callback_data="view_history")],
        [InlineKeyboardButton("🔙 В кабинет", callback_data="personal_cabinet")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def visualize_history_matrix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    record_id = int(query.data.split('_')[-1])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT name, birth_date, psychomatrix_json, calculation_type 
        FROM calculation_history 
        WHERE id = ? AND user_id = ?
    ''', (record_id, user.id))
    
    record = cursor.fetchone()
    conn.close()
    
    if not record:
        await query.message.reply_text("❌ Запись не найдена.")
        return
    
    name, birth_date, psychomatrix_json, calculation_type = record
    
    if not psychomatrix_json:
        await query.message.reply_text("❌ Для этого расчета нет данных психоматрицы.")
        return
    
    try:
        psychomatrix_data = json.loads(psychomatrix_json)
        
        if calculation_type == 'personal':
            temp_filename = f"temp_history_{user.id}.png"
            viz_img = psychomatrix_viz.create_psychomatrix_image(psychomatrix_data, name, birth_date)
            
            if viz_img:
                viz_img.save(temp_filename)
                
                with open(temp_filename, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=photo,
                        caption=f"🔮 *Психоматрица из истории*\n\n"
                               f"👤 {name}\n"
                               f"📅 {birth_date}",
                        parse_mode='Markdown'
                    )
                
                os.remove(temp_filename)
            else:
                await query.message.reply_text("❌ Не удалось создать визуализацию.")
                
        elif calculation_type == 'compatibility':
            if isinstance(psychomatrix_data, dict) and 'partner1' in psychomatrix_data and 'partner2' in psychomatrix_data:
                psychomatrix1 = psychomatrix_data['partner1']
                psychomatrix2 = psychomatrix_data['partner2']
                
                if ' и ' in name:
                    names = name.replace('Совместимость: ', '').split(' и ')
                    name1 = names[0] if len(names) > 0 else "Партнер 1"
                    name2 = names[1] if len(names) > 1 else "Партнер 2"
                else:
                    name1 = "Партнер 1"
                    name2 = "Партнер 2"
                
                if ' + ' in birth_date:
                    dates = birth_date.split(' + ')
                    date1 = dates[0] if len(dates) > 0 else birth_date
                    date2 = dates[1] if len(dates) > 1 else birth_date
                else:
                    date1 = birth_date
                    date2 = birth_date
                
                temp_filename1 = f"temp_history_{user.id}_1.png"
                viz_img1 = psychomatrix_viz.create_psychomatrix_image(psychomatrix1, name1, date1)
                
                if viz_img1:
                    viz_img1.save(temp_filename1)
                    with open(temp_filename1, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=photo,
                            caption=f"🔮 *Психоматрица {name1}*\n📅 {date1}",
                            parse_mode='Markdown'
                        )
                    os.remove(temp_filename1)
                
                temp_filename2 = f"temp_history_{user.id}_2.png"
                viz_img2 = psychomatrix_viz.create_psychomatrix_image(psychomatrix2, name2, date2)
                
                if viz_img2:
                    viz_img2.save(temp_filename2)
                    with open(temp_filename2, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=photo,
                            caption=f"🔮 *Психоматрица {name2}*\n📅 {date2}",
                            parse_mode='Markdown'
                        )
                    os.remove(temp_filename2)
                    
    except Exception as e:
        print(f"❌ Ошибка визуализации истории: {e}")
        await query.message.reply_text("❌ Ошибка при создании визуализации.")

async def handle_self_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = update.message.text
    
    print(f"🔍 ОБРАБОТКА ИМЕНИ:")
    print(f"   👤 Пользователь: {user.id}")
    print(f"   📛 Введенное имя: {name}")
    
    context.user_data['self_name'] = name
    user_states[user.id] = WAITING_SELF_DATE
    print(f"   ✅ Имя сохранено, состояние установлено в WAITING_SELF_DATE")
    
    await update.message.reply_text(
        f"Отлично, {name}! ✨\n\n"
        "Теперь введите дату рождения в формате *ДД.ММ.ГГГГ*\n"
        "Пример: 15.09.1990",
        parse_mode='Markdown'
    )
    
async def check_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Эта команда только для администраторов")
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active = TRUE")
    active_subs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM subscriptions")
    total_subs = cursor.fetchone()[0]

    cursor.execute("SELECT user_id, username, name, created_at FROM users ORDER BY created_at DESC LIMIT 5")
    recent_users = cursor.fetchall()
    
    conn.close()
    
    text = (
        "📊 *СОСТОЯНИЕ БАЗЫ ДАННЫХ*\n\n"
        f"👥 Всего пользователей: {users_count}\n"
        f"💎 Активных подписок: {active_subs}\n"
        f"📋 Всего записей подписок: {total_subs}\n\n"
        "🆕 *Последние пользователи:*\n"
    )
    
    for user_id, username, name, created_at in recent_users:
        text += f"• {name} (@{username}) - {user_id}\n"
    
    text += f"\n📁 Файл базы: `{DB_NAME}`"
    
    await update.message.reply_text(text, parse_mode='Markdown')
    
async def show_progress_bar(update, context, message_text="🔮 Рассчитываю ваш Квадрат Пифагора...", total_steps=5, delay=1.0):
    if hasattr(update, 'message'):
        chat_id = update.effective_chat.id
        filled = 0
        empty = 10
        progress_bar = "▰" * filled + "▱" * empty
        text = f"{message_text}\n\n{progress_bar} 0%"
        message = await update.message.reply_text(text)
    else:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
        filled = 0
        empty = 10
        progress_bar = "▰" * filled + "▱" * empty
        text = f"{message_text}\n\n{progress_bar} 0%"
        message = await query.message.reply_text(text)
    
    progress_message_id = message.message_id
    
    for step in range(1, total_steps + 1):
        filled = int((step / total_steps) * 10)
        empty = 10 - filled
        progress_bar = "▰" * filled + "▱" * empty
        percentage = int((step / total_steps) * 100)
        
        text = f"{message_text}\n\n{progress_bar} {percentage}%"
        
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_message_id,
                text=text,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Ошибка обновления прогресс-бара: {e}")
        
        if step < total_steps:
            await asyncio.sleep(delay)
    
    return progress_message_id

async def handle_self_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    birth_date = update.message.text.strip()
    
    print(f"🔍 ОБРАБОТКА ДАТЫ:")
    print(f"   👤 Пользователь: {user.id}")
    print(f"   📅 Введенная дата: {birth_date}")
    print(f"   📛 Сохраненное имя: {context.user_data.get('self_name', 'не найдено')}")
    
    if 'self_name' not in context.user_data:
        await update.message.reply_text(
            "❌ Сначала введите имя. Начните заново с /start",
            parse_mode='Markdown'
        )
        user_states[user.id] = MAIN_MENU
        return
    
    if not user_stats.can_make_calculation(user.id):
        print(f"   ❌ Лимит расчетов исчерпан для пользователя {user.id}")
        keyboard = [
            [InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ *Лимит расчетов исчерпан!*\n\n"
            "Вы использовали все доступные расчеты. "
            "Чтобы получить больше расчетов:\n\n"
            "1. Перейдите в *Личный кабинет*\n"
            "2. Поделитесь своей реферальной ссылкой\n"
            "3. За каждого друга получите +3 расчета\n\n"
            "Бонусы начисляются автоматически!",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
        
    is_valid, error_message, formatted_date = validate_birth_date(birth_date)
    
    if not is_valid:
        print(f"   ❌ Ошибка валидации даты: {error_message}")
        await update.message.reply_text(
            f"{error_message}\n\n"
            "📝 Пример правильного формата: 15.09.1990\n"
            "Попробуйте еще раз:"
        )
        return
    
    print(f"   ✅ Дата успешно валидирована: {formatted_date}")
    
    name = context.user_data['self_name']
        
    try:
        print(f"   🔄 Попытка разбора даты: {birth_date}")
        
        birth_date = birth_date.replace(' ', '')
        
        if '.' in birth_date:
            parts = birth_date.split('.')
        elif '/' in birth_date:
            parts = birth_date.split('/')
        elif '-' in birth_date:
            parts = birth_date.split('-')
        else:
            print(f"   ❌ Неверный разделитель в дате: {birth_date}")
            await update.message.reply_text(
                "❌ Неверный формат! Используйте ДД.ММ.ГГГГ (например: 15.09.1990)\n"
                "Попробуйте еще раз:"
            )
            return
        
        if len(parts) != 3:
            print(f"   ❌ Неверное количество частей в дате: {parts}")
            await update.message.reply_text(
                "❌ Неверный формат! Должно быть три части: день, месяц, год\n"
                "Пример: 15.09.1990\n"
                "Попробуйте еще раз:"
            )
            return
        
        day, month, year = parts
        
        formatted_date = f"{int(day):02d}.{int(month):02d}.{year}"
        
        datetime.strptime(formatted_date, '%d.%m.%Y')
        
        print(f"   ✅ Дата успешно разобрана: {formatted_date}")
        
    except (ValueError, Exception) as e:
        print(f"   ❌ Ошибка валидации даты: {e}")
        await update.message.reply_text(
            "❌ Неверный формат даты или несуществующая дата!\n"
            "Используйте ДД.ММ.ГГГГ\n"
            "Пример: 15.09.1990\n"
            "Попробуйте еще раз:"
        )
        return
    
    name = context.user_data['self_name']
    print(f"   ✅ Дата принята для пользователя: {name}")

    user_stats.add_user(user.id, user.username)
    user_stats.add_calculation(user.id, "personal")
    print(f"   📊 Статистика обновлена для пользователя {user.id}")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user.id,))
    existing_user = cursor.fetchone()
    
    if existing_user:
        cursor.execute('UPDATE users SET username = ?, name = ?, birth_date = ? WHERE user_id = ?',
                      (user.username, name, formatted_date, user.id))
        print(f"🔄 Обновлен существующий пользователь: {user.id}")
    else:
        cursor.execute('INSERT INTO users (user_id, username, name, birth_date) VALUES (?, ?, ?, ?)',
                      (user.id, user.username, name, formatted_date))
        print(f"➕ Добавлен новый пользователь: {user.id}")
    
    conn.commit()
    conn.close()
    print(f"💾 Данные сохранены в базу: {user.id}, {name}, {formatted_date}")
    
    progress_message_id = await show_progress_bar(
        update, 
        context, 
        "🔮 *РАСЧЕТ ВАШЕГО КВАДРАТА ПИФАГОРА*",
        total_steps=5,
        delay=1.2
    )
    
    cube = PythagorasCube(formatted_date)
    psychomatrix = cube.calculate()
    
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id, 
            message_id=progress_message_id
        )
    except Exception as e:
        print(f"⚠️ Не удалось удалить прогресс-бар: {e}")
    
    try:
        temp_filename = f"temp_psychomatrix_{user.id}.png"
        viz_img = psychomatrix_viz.create_psychomatrix_image(psychomatrix, name, formatted_date)
        
        if viz_img:
            viz_img.save(temp_filename)
            
            with open(temp_filename, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"🔮 *Визуальная психоматрица для {name}*\n\n"
                           f"📅 Дата рождения: {formatted_date}\n\n"
                           f"*Расшифровка цветов:*\n"
                           f"• 🟢 Зеленый - сильная черта (3+ цифры)\n"
                           f"• 🔵 Голубой - нормальное развитие (1-2 цифры)\n"
                           f"• 🔴 Красный - слабая черта (0 цифр)",
                    parse_mode='Markdown'
                )
            
            os.remove(temp_filename)
            print(f"✅ Изображение психоматрицы отправлено для пользователя {user.id}")
            
    except Exception as e:
        print(f"⚠️ Не удалось создать изображение психоматрицы: {e}")
        text_matrix = cube.get_enhanced_psychomatrix_text(psychomatrix, name)
        await update.message.reply_text(
            text_matrix,
            parse_mode='Markdown'
        )
    
    result = cube.get_detailed_interpretation(psychomatrix, name)
    
    try:
        save_calculation_history(user.id, "personal", name, formatted_date, result, psychomatrix)
        print(f"✅ История с психоматрицей сохранена для пользователя {user.id}")
    except Exception as e:
        print(f"⚠️ Не удалось сохранить историю с психоматрицей: {e}")
        save_calculation_history(user.id, "personal", name, formatted_date, result)
    
    print(f"   ✅ Расчет завершен, отправляем результат")
    
    keyboard = [
        [InlineKeyboardButton("🔄 Новый расчет", callback_data="new_calculation")],
        [InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(result, parse_mode='Markdown', reply_markup=reply_markup)
    user_states[user.id] = MAIN_MENU
    print(f"   🏁 Состояние пользователя {user.id} установлено в MAIN_MENU")

async def handle_partner1_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = update.message.text
    
    context.user_data['partner1_name'] = name
    user_states[user.id] = WAITING_PARTNER1_DATE
    
    await update.message.reply_text(
        f"Хорошо! Теперь введите дату рождения *{name}* в формате ДД.ММ.ГГГГ:",
        parse_mode='Markdown'
    )

async def handle_partner1_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    birth_date = update.message.text.strip()
    
    try:
        print(f"🔍 ОБРАБОТКА ДАТЫ ПЕРВОГО ПАРТНЕРА:")
        print(f"   👤 Пользователь: {user.id}")
        print(f"   📅 Введенная дата: {birth_date}")
        
        is_valid, error_message, formatted_date = validate_birth_date(birth_date)
    
        if not is_valid:
            print(f"   ❌ Ошибка валидации даты: {error_message}")
            await update.message.reply_text(
                f"{error_message}\n\n"
                "📝 Пример правильного формата: 15.09.1990\n"
                "Попробуйте еще раз:"
            )
            return
    
        print(f"   ✅ Дата успешно валидирована: {formatted_date}")
    
        context.user_data['partner1_date'] = formatted_date
        user_states[user.id] = WAITING_PARTNER2_NAME
        
        birth_date = birth_date.replace(' ', '')
      
        if '.' in birth_date:
            parts = birth_date.split('.')
        elif '/' in birth_date:
            parts = birth_date.split('/')
        elif '-' in birth_date:
            parts = birth_date.split('-')
        else:
            print(f"   ❌ Неверный разделитель в дате: {birth_date}")
            await update.message.reply_text(
                "❌ Неверный формат! Используйте ДД.ММ.ГГГГ (например: 15.09.1990)\n"
                "Попробуйте еще раз:"
            )
            return
        
        if len(parts) != 3:
            print(f"   ❌ Неверное количество частей в дате: {parts}")
            await update.message.reply_text(
                "❌ Неверный формат! Должно быть три части: день, месяц, год\n"
                "Пример: 15.09.1990\n"
                "Попробуйте еще раз:"
            )
            return
        
        day, month, year = parts
        
        formatted_date = f"{int(day):02d}.{int(month):02d}.{year}"
        
        datetime.strptime(formatted_date, '%d.%m.%Y')
        
        print(f"   ✅ Дата успешно разобрана: {formatted_date}")
        
    except (ValueError, Exception) as e:
        print(f"   ❌ Ошибка валидации даты: {e}")
        await update.message.reply_text(
            "❌ Неверный формат даты или несуществующая дата!\n"
            "Используйте ДД.ММ.ГГГГ\n"
            "Пример: 15.09.1990\n"
            "Попробуйте еще раз:"
        )
        return
    
    context.user_data['partner1_date'] = formatted_date
    user_states[user.id] = WAITING_PARTNER2_NAME
    
    await update.message.reply_text(
        "💞 Теперь введите имя второго человека:",
        parse_mode='Markdown'
    )

async def handle_partner2_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = update.message.text
    
    context.user_data['partner2_name'] = name
    user_states[user.id] = WAITING_PARTNER2_DATE
    
    await update.message.reply_text(
        f"Отлично! Введите дату рождения *{name}* в формате ДД.ММ.ГГГГ:",
        parse_mode='Markdown'
    )

async def handle_partner2_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    birth_date = update.message.text.strip()
    
    if not user_stats.can_make_calculation(user.id):
        keyboard = [
            [InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ *Лимит расчетов исчерпан!*\n\n"
            "Вы использовали все доступные расчетов. "
            "Чтобы получить больше расчетов:\n\n"
            "1. Перейдите в *Личный кабинет*\n"
            "2. Поделитесь своей реферальной ссылкой\n"
            "3. За каждого друга получите +3 расчета\n\n"
            "Бонусы начисляются автоматически!",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
        
    is_valid, error_message, formatted_date = validate_birth_date(birth_date)
    
    if not is_valid:
        print(f"   ❌ Ошибка валидации даты: {error_message}")
        await update.message.reply_text(
            f"{error_message}\n\n"
            "📝 Пример правильного формата: 15.09.1990\n"
            "Попробуйте еще раз:"
        )
        return
    
    print(f"   ✅ Дата успешно валидирована: {formatted_date}")
    
    partner1_name = context.user_data['partner1_name']
    partner1_date = context.user_data['partner1_date']
    partner2_name = context.user_data['partner2_name']
    partner2_date = formatted_date
        
    try:
        print(f"🔍 ОБРАБОТКА ДАТЫ ВТОРОГО ПАРТНЕРА:")
        print(f"   👤 Пользователь: {user.id}")
        print(f"   📅 Введенная дата: {birth_date}")
        
        birth_date = birth_date.replace(' ', '')
        
        if '.' in birth_date:
            parts = birth_date.split('.')
        elif '/' in birth_date:
            parts = birth_date.split('/')
        elif '-' in birth_date:
            parts = birth_date.split('-')
        else:
            print(f"   ❌ Неверный разделитель в дате: {birth_date}")
            await update.message.reply_text(
                "❌ Неверный формат! Используйте ДД.ММ.ГГГГ (например: 15.09.1990)\n"
                "Попробуйте еще раз:"
            )
            return
        
        if len(parts) != 3:
            print(f"   ❌ Неверное количество частей в дате: {parts}")
            await update.message.reply_text(
                "❌ Неверный формат! Должно быть три части: день, месяц, год\n"
                "Пример: 15.09.1990\n"
                "Попробуйте еще раз:"
            )
            return
        
        day, month, year = parts
        
        formatted_date = f"{int(day):02d}.{int(month):02d}.{year}"
        
        datetime.strptime(formatted_date, '%d.%m.%Y')
        
        print(f"   ✅ Дата успешно разобрана: {formatted_date}")
        
    except (ValueError, Exception) as e:
        print(f"   ❌ Ошибка валидации даты: {e}")
        await update.message.reply_text(
            "❌ Неверный формат даты или несуществующая дата!\n"
            "Используйте ДД.ММ.ГГГГ\n"
            "Пример: 15.09.1990\n"
            "Попробуйте еще раз:"
        )
        return
    
    partner1_name = context.user_data['partner1_name']
    partner1_date = context.user_data['partner1_date']
    partner2_name = context.user_data['partner2_name']
    partner2_date = formatted_date

    user_stats.add_user(user.id, user.username)
    user_stats.add_calculation(user.id, "compatibility")
    
    progress_message_id = await show_progress_bar(
        update, 
        context, 
        "💞 *РАСЧЕТ СОВМЕСТИМОСТИ*",
        total_steps=6,
        delay=1.0
    )
    
    cube1 = PythagorasCube(partner1_date)
    psychomatrix1 = cube1.calculate()
    
    cube2 = PythagorasCube(partner2_date)
    psychomatrix2 = cube2.calculate()
    
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id, 
            message_id=progress_message_id
        )
    except Exception as e:
        print(f"⚠️ Не удалось удалить прогресс-бар: {e}")
    
    try:
        temp_filename1 = f"temp_psychomatrix_{user.id}_1.png"
        viz_img1 = psychomatrix_viz.create_psychomatrix_image(psychomatrix1, partner1_name, partner1_date)
        
        if viz_img1:
            viz_img1.save(temp_filename1)
            with open(temp_filename1, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"🔮 *Психоматрица {partner1_name}*\n"
                           f"📅 Дата: {partner1_date}",
                    parse_mode='Markdown'
                )
            os.remove(temp_filename1)
         
        temp_filename2 = f"temp_psychomatrix_{user.id}_2.png"
        viz_img2 = psychomatrix_viz.create_psychomatrix_image(psychomatrix2, partner2_name, partner2_date)
        
        if viz_img2:
            viz_img2.save(temp_filename2)
            with open(temp_filename2, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"🔮 *Психоматрица {partner2_name}*\n"
                           f"📅 Дата: {partner2_date}",
                    parse_mode='Markdown'
                )
            os.remove(temp_filename2)
            
        print(f"✅ Изображения психоматриц совместимости отправлены для пользователя {user.id}")
            
    except Exception as e:
        print(f"⚠️ Не удалось создать изображения психоматриц совместимости: {e}")
    
    result = cube2.calculate_compatibility(psychomatrix1, psychomatrix2, partner1_name, partner2_name)
    
    try:
        calculation_info = f"Совместимость: {partner1_name} и {partner2_name}"
        combined_psychomatrix = {
            'partner1': psychomatrix1,
            'partner2': psychomatrix2
        }
        save_calculation_history(user.id, "compatibility", calculation_info, 
                               f"{partner1_date} + {partner2_date}", result, combined_psychomatrix)
        print(f"✅ История совместимости с психоматрицами сохранена")
    except Exception as e:
        print(f"⚠️ Не удалось сохранить историю совместимости: {e}")
    
    keyboard = [
        [InlineKeyboardButton("🔄 Новый расчет", callback_data="new_calculation")],
        [InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(result, parse_mode='Markdown', reply_markup=reply_markup)
    user_states[user.id] = MAIN_MENU

async def handle_broadcast_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user    
    if user.id not in ADMIN_IDS:
        return
    
    if context.user_data.get('waiting_for_broadcast'):
        photo_file_id = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        
        context.user_data['pending_broadcast'] = {
            'text': caption,
            'photo_file_id': photo_file_id,
            'user_id': user.id
        }

        keyboard = [
            [InlineKeyboardButton("✅ Да, отправить", callback_data=f"confirm_send_{update.message.message_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_send")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        confirmation_text = (
            f"📤 *ПОДТВЕРЖДЕНИЕ РАССЫЛКИ*\n\n"
            f"🖼️ *Будет отправлено изображение*\n"
        )
        
        if caption:
            confirmation_text += f"*Текст сообщения:*\n{caption}\n\n"
            
        confirmation_text += f"❓ *Вы уверены, что хотите отправить это сообщение всем пользователям?*"
        
        await update.message.reply_text(
            confirmation_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        context.user_data['waiting_for_broadcast'] = False

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'waiting_for_broadcast' in context.user_data:
        context.user_data['waiting_for_broadcast'] = False
        await update.message.reply_text("❌ Рассылка отменена")
    else:
        await update.message.reply_text("❌ Нечего отменять")
 
@admin_only
async def send_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Эта команда только для администраторов")
        return
    
    has_photo = update.message.photo
    
    if not context.args and not has_photo:
        await update.message.reply_text(
            "📝 *Использование команды:*\n"
            "`/send сообщение для рассылки`\n\n"
            "*Или отправьте картинку с подписью:*\n"
            "1. Отправьте картинку\n"
            "2. В подписи напишите `/send ваш текст`\n\n"
            "*Пример:*\n"
            "`/send Всем привет! Новое обновление бота!`",
            parse_mode='Markdown'
        )
        return
    
    message_text = ' '.join(context.args) if context.args else ""
    
    photo_file_id = None
    if has_photo:
        photo_file_id = update.message.photo[-1].file_id
        if not message_text and update.message.caption:
            message_text = update.message.caption.replace('/send ', '').strip()
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, отправить", callback_data=f"confirm_send_{update.message.message_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_send")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    confirmation_text = f"📤 *ПОДТВЕРЖДЕНИЕ РАССЫЛКИ*\n\n"
    
    if photo_file_id:
        confirmation_text += f"🖼️ *Будет отправлено изображение*\n"
    
    if message_text:
        confirmation_text += f"*Текст сообщения:*\n{message_text}\n\n"
    
    confirmation_text += f"❓ *Вы уверены, что хотите отправить это сообщение всем пользователям?*"
    
    if photo_file_id:
        await update.message.reply_photo(
            photo=photo_file_id,
            caption=confirmation_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            confirmation_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    context.user_data['pending_broadcast'] = {
        'text': message_text,
        'photo_file_id': photo_file_id,
        'user_id': user.id
    }

async def handle_broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    if user.id not in ADMIN_IDS:
        await query.message.reply_text("❌ Эта команда только для администраторов")
        return
    
    if query.data == "cancel_send":
        await query.message.edit_text("❌ Рассылка отменена")
        return
    
    if query.data.startswith("confirm_send_"):
        broadcast_data = context.user_data.get('pending_broadcast')
        if not broadcast_data:
            await query.message.edit_text("❌ Данные рассылки не найдены")
            return
        
        message_text = broadcast_data['text']
        photo_file_id = broadcast_data.get('photo_file_id')
        
        status_text = f"🔄 *НАЧИНАЮ РАССЫЛКУ...*\n\n"
        
        if photo_file_id:
            status_text += f"🖼️ *С изображением*\n"
        
        if message_text:
            status_text += f"Сообщение: {message_text}\n\n"
        
        status_text += f"⏳ Это может зануть несколько минут..."
        
        if photo_file_id:
            await query.message.edit_caption(caption=status_text, parse_mode='Markdown')
        else:
            await query.message.edit_text(status_text, parse_mode='Markdown')
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
        conn.close()
        
        sent_count = 0
        failed_count = 0
        
        for user_tuple in users:
            user_id = user_tuple[0]
            try:
                if photo_file_id:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=photo_file_id,
                        caption=f"📢 *СООБЩЕНИЕ ОТ АДМИНИСТРАТОРА:*\n\n{message_text}" if message_text else "📢 *СООБЩЕНИЕ ОТ АДМИНИСТРАТОРА*",
                        parse_mode='Markdown'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"📢 *СООБЩЕНИЕ ОТ АДМИНИСТРАТОРА:*\n\n{message_text}",
                        parse_mode='Markdown'
                    )
                sent_count += 1
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"❌ Не удалось отправить сообщение пользователю {user_id}: {e}")
                failed_count += 1
        
        result_text = (
            f"✅ *РАССЫЛКА ЗАВЕРШЕНА*\n\n"
            f"📊 *Статистика:*\n"
            f"• ✅ Успешно: {sent_count}\n"
            f"• ❌ Ошибок: {failed_count}\n"
            f"• 📨 Всего: {sent_count + failed_count}"
        )
        
        if photo_file_id:
            await query.message.edit_caption(caption=result_text, parse_mode='Markdown')
        else:
            await query.message.edit_text(result_text, parse_mode='Markdown')
        if 'pending_broadcast' in context.user_data:
            del context.user_data['pending_broadcast']

@admin_only
async def activate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "💎 *АКТИВАЦИЯ ПОДПИСКИ*\n\n"
            "❌ Использование: `/activate user_id`\n"
            "📝 Пример: `/activate 123456789`\n\n"
            "🔄 *Для сброса подписки:*\n"
            "`/reset_subscription user_id`\n\n"
            "⚠️ *Для сброса ВСЕХ подписок:*\n"
            "`/reset_subscription all`\n\n"
            "🔍 *Посмотреть подписки:* `/admin`\n\n"
            "🔄 *Для отмены активации:*\n"
            "`/cancel_activation user_id`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        
        subscription_manager.create_subscription(target_user_id)

        if payment_tracker.confirm_payment(target_user_id):
            await update.message.reply_text(
                f"✅ *ПОДПИСКА АКТИВИРОВАНА!*\n\n"
                f"👤 Пользователь: `{target_user_id}`\n"
                f"💰 Статус: ✅ Активная подписка (30 дней)\n"
                f"💳 Платеж: ✅ Подтвержден\n\n"
                f"Пользователь получил полный доступ ко всем функциям!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"✅ *ПОДПИСКА АКТИВИРОВАНА!*\n\n"
                f"👤 Пользователь: `{target_user_id}`\n"
                f"💰 Статус: ✅ Активная подписка (30 дней)\n"
                f"💳 Платеж: 🆓 Бесплатная активация\n\n"
                f"Пользователь получил полный доступ ко всем функциям!",
                parse_mode='Markdown'
            )
            
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id. Должен быть числом.")
        
@admin_only
async def cancel_activation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ *ОТМЕНА АКТИВАЦИИ*\n\n"
            "❌ Использование: `/cancel_activation user_id`\n"
            "📝 Пример: `/cancel_activation 123456789`\n\n"
            "💡 *Эта команда:*\n"
            "• Удаляет ожидающий платеж из системы\n"
            "• Отправляет уведомление пользователю\n"
            "• Очищает историю платежей\n\n"
            "🔍 *Посмотреть ожидающие оплаты:* `/admin`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        
        # Проверяем, есть ли ожидающий платеж
        pending_payments = payment_tracker.get_pending_list()
        
        if target_user_id not in pending_payments:
            await update.message.reply_text(
                f"❌ *ПЛАТЕЖ НЕ НАЙДЕН*\n\n"
                f"👤 Пользователь: `{target_user_id}`\n"
                f"💰 Статус: ❌ Нет ожидающих платежей\n\n"
                f"Возможно платеж уже обработан или не создавался.",
                parse_mode='Markdown'
            )
            return
        
        user_info = pending_payments[target_user_id]['user_info']
        
        # Удаляем из ожидающих платежей
        if target_user_id in payment_tracker.pending_payments:
            del payment_tracker.pending_payments[target_user_id]
        
        # Помечаем как отменено в БД
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE payments 
            SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP, admin_id = ?
            WHERE user_id = ? AND status = 'pending'
        ''', (user.id, target_user_id))
        conn.commit()
        conn.close()
        
        # Отправляем уведомление пользователю
        try:
            keyboard = [
                [InlineKeyboardButton("💎 Купить подписку", callback_data="buy_subscription")],
                [InlineKeyboardButton("📞 Поддержка", url=f"https://t.me/{YOUR_TELEGRAM.replace('@', '')}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ *АКТИВАЦИЯ ОТМЕНЕНА*\n\n"
                     "⏰ Ваш запрос на активацию подписки был отменен администратором.\n\n"
                     "💡 *Возможные причины:*\n"
                     "• Платеж не поступил на счет\n"
                     "• Неверная сумма перевода\n"
                     "• Истекло время ожидания\n\n"
                     "📝 *Что делать:*\n"
                     "1. Проверьте правильность перевода\n"
                     "2. Убедитесь, что сумма соответствует указанной\n"
                     "3. Повторите оплату и уведомление\n"
                     "4. При проблемах свяжитесь с поддержкой\n\n"
                     "Мы готовы помочь! 🤝",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            await update.message.reply_text(
                f"✅ *АКТИВАЦИЯ ОТМЕНЕНА!*\n\n"
                f"👤 Пользователь: {user_info}\n"
                f"💰 Статус: ❌ Платеж отменен\n"
                f"📨 Уведомление: ✅ Отправлено\n\n"
                f"Пользователь получил уведомление об отмене.",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            error_msg = str(e)
            if "bot was blocked" in error_msg.lower():
                await update.message.reply_text(
                    f"✅ *АКТИВАЦИЯ ОТМЕНЕНА!*\n\n"
                    f"👤 Пользователь: {user_info}\n"
                    f"💰 Статус: ❌ Платеж отменен\n"
                    f"📨 Уведомление: ❌ Пользователь заблокировал бота\n\n"
                    f"Данные очищены из системы.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"✅ *АКТИВАЦИЯ ОТМЕНЕНА!*\n\n"
                    f"👤 Пользователь: {user_info}\n"
                    f"💰 Статус: ❌ Платеж отменен\n"
                    f"📨 Уведомление: ❌ Ошибка отправки: {error_msg}\n\n"
                    f"Данные очищены из системы.",
                    parse_mode='Markdown'
                )
            
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id. Должен быть числом.")
 
@admin_only 
async def list_subscriptions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, start_date, end_date 
        FROM subscriptions 
        WHERE is_active = TRUE 
        ORDER BY end_date DESC
    ''')
    active_subs = cursor.fetchall()
    conn.close()
    
    if not active_subs:
        await update.message.reply_text(
            "📋 *АКТИВНЫЕ ПОДПИСКИ*\n\n"
            "❌ Нет активных подписок",
            parse_mode='Markdown'
        )
        return
    
    text = "📋 *АКТИВНЫЕ ПОДПИСКИ*\n\n"
    
    for i, (user_id, start_date, end_date) in enumerate(active_subs[:10], 1):
        text += f"{i}. 👤 `{user_id}`\n"
        text += f"   📅 До: {end_date[:10]}\n\n"
    
    if len(active_subs) > 10:
        text += f"📊 ... и еще {len(active_subs) - 10} подписок\n\n"
    
    text += f"📈 Всего активных подписок: {len(active_subs)}"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def check_manual_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"💰 *НОВЫЙ ЗАПРОС ПРОВЕРКИ ОПЛАТЫ*\n\n"
                     f"👤 Пользователь: {user.first_name}\n"
                     f"🆔 ID: `{user.id}`\n"
                     f"📛 Username: @{user.username if user.username else 'нет'}\n"
                     f"⏰ Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}\n\n"
                     f"Для активации используйте команду:\n"
                     f"`/activate {user.id}`",
                parse_mode='Markdown'
            )
            print(f"✅ Уведомление отправлено админу {admin_id}")
        except Exception as e:
            print(f"❌ Не удалось отправить уведомление админу {admin_id}: {e}")
    
    if subscription_manager.check_subscription(user.id):
        await query.message.reply_text(
            "🎉 *Ваша подписка активирована!*\n\n"
            "Теперь у вас неограниченный доступ ко всем функциям бота!\n\n"
            "✨ Можете делать неограниченное количество расчетов!",
            parse_mode='Markdown'
        )
        return
    
    pending_payments = payment_tracker.get_pending_list()
    
    if user.id in pending_payments:
        text = (
            "⏳ *ПЛАТЕЖ НА ПРОВЕРКЕ*\n\n"
            "✅ *Мы получили ваше уведомление об оплате!*\n\n"
            "💰 *Что происходит сейчас:*\n"
            "• Администратор получил уведомление\n"
            "• Проверяется ваш платеж\n"
            "• Обычно это занимает до 5 минут\n\n"
            "📞 *Если прошло больше 10 минут:*\n"
            f"Свяжитесь с поддержкой: {YOUR_TELEGRAM}\n\n"
            "🔄 *Обновите статус через пару минут*"
        )
    else:
        text = (
            "❌ *ЗАПРОС НЕ НАЙДЕН*\n\n"
            "Ваш запрос на оплату не найден в системе.\n"
            "Пожалуйста, начните процесс заново через Личный кабинет.\n\n"
            "📝 *Что делать:*\n"
            "1. Вернитесь в Личный кабинет\n"
            "2. Нажмите '💎 Купить подписку'\n"
            "3. Следуйте инструкциям"
        )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Проверить снова", callback_data="check_manual_payment")],
        [InlineKeyboardButton("🔙 В кабинет", callback_data="personal_cabinet")],
        [InlineKeyboardButton("📞 Поддержка", url=f"https://t.me/{YOUR_TELEGRAM.replace('@', '')}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
async def handle_telegram_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    payment_tracker.add_payment_request(user.id, user.username, SUBSCRIPTION_PRICE_TELEGRAM, "telegram")
    
    text = (
        "📱 *ОПЛАТА ЧЕРЕЗ TELEGRAM*\n\n"
        f"💎 Подписка на 30 дней: *{SUBSCRIPTION_PRICE_TELEGRAM} руб.*\n"
        "💰 *ВНИМАНИЕ!!!: цена выше из-за комиссии Telegram*\n\n"
        "📋 *Инструкция:*\n"
        f"1. Нажмите на кнопку '💎 Оплатить {SUBSCRIPTION_PRICE_TELEGRAM} руб.' ниже\n"
        "2. В открывшемся окне завершите оплату\n"
        "3. После успешной оплаты нажмите '✅ Я оплатил(а)'\n"
        "4. Мы активируем подписку в рабочее время с 9.00 до 20.00 по МСК в течение 1 часа\n\n"
        "💡 *Преимущества:*\n"
        "• Быстрая и безопасная оплата\n"
        "• Можно оплатить картой или 🌟 Stars\n"
        "• Встроенная система Telegram\n\n"
        "📞 *При проблемах:* " + YOUR_TELEGRAM
    )
    
    keyboard = [
        [InlineKeyboardButton(f"💎 Оплатить {SUBSCRIPTION_PRICE_TELEGRAM} руб", url=TELEGRAM_PAYMENT_LINK)],
        [InlineKeyboardButton("✅ Я оплатил(а)", callback_data="check_manual_payment")],
        [InlineKeyboardButton("🔙 Выбор оплаты", callback_data="choose_payment")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
async def handle_tbank_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    payment_tracker.add_payment_request(user.id, user.username, "tbank")
    
    text = (
        "🏦 *ОПЛАТА ЧЕРЕЗ Т-БАНК*\n\n"
        f"💎 Подписка на 30 дней: *{SUBSCRIPTION_PRICE} руб.*\n\n"
        "📋 *Инструкция:*\n"
        f"1. Переведите *{SUBSCRIPTION_PRICE} руб.* на карту:\n"
        f"   `{TBANK_CARD_NUMBER}`\n"
        f"2. Или через СБП по номеру телефона на Т-Банк:\n"
        f"   `{TBANK_PHONE}`\n\n"
        "3. После перевода нажмите кнопку ниже\n"
        "4. Мы активируем подписку в рабочее время с 9.00 до 20.00 по МСК в течение 1 часа\n\n"
        "📞 *При проблемах:* " + YOUR_TELEGRAM
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил(а)", callback_data="check_manual_payment")],
        [InlineKeyboardButton("🔙 Выбор оплаты", callback_data="choose_payment")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)    
    
async def choose_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    text = (
        "💎 *ПОДПИСКА НА 30 ДНЕЙ*\n\n"
        "💰 *Выберите способ оплаты:*\n\n"
        
        f"🏦 *Т-Банк (ручной перевод)* - {SUBSCRIPTION_PRICE} руб.\n"
        "   • Перевод на карту или по СБП\n"
        "   • Подтверждение вручную администратором\n"
        "   • Обычно до 1 часа\n\n"
        
        f"📱 *Оплата в Telegram* - {SUBSCRIPTION_PRICE_TELEGRAM} руб.\n"
        "   • 💰 *Из-за комиссии Telegram дороже 😔*\n"
        "   • Оплата через встроенную систему\n"
        "   • Подтверждение вручную администратором\n"
        "   • Обычно до 1 часа\n\n"
        
        "📞 *При проблемах:* " + YOUR_TELEGRAM
    )
    
    keyboard = [
        [InlineKeyboardButton(f"🏦 Т-Банк ({SUBSCRIPTION_PRICE} руб)", callback_data="pay_tbank")],
        [InlineKeyboardButton(f"📱 Telegram ({SUBSCRIPTION_PRICE_TELEGRAM} руб)", callback_data="pay_telegram")],
        [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    if subscription_manager.check_subscription(user.id):
        await show_success_message(query.message, context)
        return
    
    import random
    payment_successful = random.random() < 0.8
    
    if payment_successful:
        subscription_manager.create_subscription(user.id)
        await notify_admin_about_payment(context, user, "auto")
        await show_success_message(query.message, context)
    else:
        await show_pending_message(query.message, context, user.id)

async def show_success_message(message, context):
    success_text = (
        "🎉 *ОПЛАТА ПРОШЛА УСПЕШНО!*\n\n"
        "✅ Ваша подписка активирована на 30 дней!\n\n"
        "✨ *Теперь у вас:*\n"
        "• 🔮 Неограниченные расчеты\n"
        "• 💞 Неограниченная совместимость\n"
        "• 📊 Приоритетная поддержка\n\n"
        "Приятного использования! 🚀"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Главное меню", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.edit_text(success_text, parse_mode='Markdown', reply_markup=reply_markup)

async def show_pending_message(message, context, user_id):
    pending_text = (
        "⏳ *ОЖИДАЕМ ПОДТВЕРЖДЕНИЕ ОПЛАТЫ*\n\n"
        "Мы получили ваше уведомление об оплате!\n\n"
        "💡 *Что происходит сейчас:*\n"
        "• Администратор получил уведомление\n" 
        "• Проверяется ваш платеж\n"
        "• Обычно это занимает 10 минут\n\n"
        "📞 *Если прошло больше 1 часа:*\n"
        f"Свяжитесь с поддержкой: {YOUR_TELEGRAM}\n\n"
        "🔄 *Обновите статус через пару минут*"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Проверить снова", callback_data="check_manual_payment")],
        [InlineKeyboardButton("📞 Поддержка", url=f"https://t.me/{YOUR_TELEGRAM.replace('@', '')}")],
        [InlineKeyboardButton("🔙 В кабинет", callback_data="personal_cabinet")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.edit_text(pending_text, parse_mode='Markdown', reply_markup=reply_markup)
    
async def notify_admin_about_payment(context, user, payment_type="auto"):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"💰 *НОВАЯ АВТОМАТИЧЕСКАЯ ОПЛАТА*\n\n"
                     f"👤 Пользователь: {user.first_name}\n"
                     f"🆔 ID: `{user.id}`\n"
                     f"📛 Username: @{user.username if user.username else 'нет'}\n"
                     f"💳 Тип: {payment_type}\n"
                     f"⏰ Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}\n\n"
                     f"✅ Подписка активирована автоматически",
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"❌ Не удалось уведомить админа {admin_id}: {e}")
            
async def activate_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    subscription_manager.create_subscription(user.id)
    
    await update.message.reply_text(
        "🎉 *ПОДПИСКА АКТИВИРОВАНА!*\n\n"
        "✅ Вам предоставлен полный доступ на 30 дней!\n\n"
        "Теперь вы можете делать неограниченное количество расчетов!",
        parse_mode='Markdown'
    )
    await notify_admin_about_payment(context, user, "manual_command")
    
@admin_only
async def cancel_activation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ *ОТМЕНА АКТИВАЦИИ*\n\n"
            "❌ Использование: `/cancel_activation user_id`\n"
            "📝 Пример: `/cancel_activation 123456789`\n\n"
            "💡 *Эта команда:*\n"
            "• Удаляет ожидающий платеж из системы\n"
            "• Отправляет уведомление пользователю\n"
            "• Очищает историю платежей\n\n"
            "🔍 *Посмотреть ожидающие оплаты:* `/admin`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        
        # Проверяем, есть ли ожидающий платеж
        pending_payments = payment_tracker.get_pending_list()
        
        if target_user_id not in pending_payments:
            await update.message.reply_text(
                f"❌ *ПЛАТЕЖ НЕ НАЙДЕН*\n\n"
                f"👤 Пользователь: `{target_user_id}`\n"
                f"💰 Статус: ❌ Нет ожидающих платежей\n\n"
                f"Возможно платеж уже обработан или не создавался.",
                parse_mode='Markdown'
            )
            return
        
        user_info = pending_payments[target_user_id]['user_info']
        
        # Удаляем из ожидающих платежей
        if target_user_id in payment_tracker.pending_payments:
            del payment_tracker.pending_payments[target_user_id]
        
        # Помечаем как отменено в БД
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE payments 
            SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP, admin_id = ?
            WHERE user_id = ? AND status = 'pending'
        ''', (user.id, target_user_id))
        conn.commit()
        conn.close()
        
        # Отправляем уведомление пользователю
        try:
            keyboard = [
                [InlineKeyboardButton("💎 Купить подписку", callback_data="buy_subscription")],
                [InlineKeyboardButton("📞 Поддержка", url=f"https://t.me/{YOUR_TELEGRAM.replace('@', '')}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ *АКТИВАЦИЯ ОТМЕНЕНА*\n\n"
                     "⏰ Ваш запрос на активацию подписки был отменен администратором.\n\n"
                     "💡 *Возможные причины:*\n"
                     "• Платеж не поступил на счет\n"
                     "• Неверная сумма перевода\n"
                     "• Истекло время ожидания\n\n"
                     "📝 *Что делать:*\n"
                     "1. Проверьте правильность перевода\n"
                     "2. Убедитесь, что сумма соответствует указанной\n"
                     "3. Повторите оплату и уведомление\n"
                     "4. При проблемах свяжитесь с поддержкой\n\n"
                     "Мы готовы помочь! 🤝",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            await update.message.reply_text(
                f"✅ *АКТИВАЦИЯ ОТМЕНЕНА!*\n\n"
                f"👤 Пользователь: {user_info}\n"
                f"💰 Статус: ❌ Платеж отменен\n"
                f"📨 Уведомление: ✅ Отправлено\n\n"
                f"Пользователь получил уведомление об отмене.",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            error_msg = str(e)
            if "bot was blocked" in error_msg.lower():
                await update.message.reply_text(
                    f"✅ *АКТИВАЦИЯ ОТМЕНЕНА!*\n\n"
                    f"👤 Пользователь: {user_info}\n"
                    f"💰 Статус: ❌ Платеж отменен\n"
                    f"📨 Уведомление: ❌ Пользователь заблокировал бота\n\n"
                    f"Данные очищены из системы.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"✅ *АКТИВАЦИЯ ОТМЕНЕНА!*\n\n"
                    f"👤 Пользователь: {user_info}\n"
                    f"💰 Статус: ❌ Платеж отменен\n"
                    f"📨 Уведомление: ❌ Ошибка отправки: {error_msg}\n\n"
                    f"Данные очищены из системы.",
                    parse_mode='Markdown'
                )
            
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id. Должен быть числом.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text

    if context.user_data.get('waiting_for_broadcast') and update.message.photo:
        if user.id in ADMIN_IDS:
            photo_file_id = update.message.photo[-1].file_id
            caption = update.message.caption or ""
            
            context.user_data['pending_broadcast'] = {
                'text': caption,
                'photo_file_id': photo_file_id,
                'user_id': user.id
            }
            
            keyboard = [
                [InlineKeyboardButton("✅ Да, отправить", callback_data=f"confirm_send_{update.message.message_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_send")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            confirmation_text = (
                f"📤 *ПОДТВЕРЖДЕНИЕ РАССЫЛКИ*\n\n"
                f"🖼️ *Будет отправлено изображение*\n"
            )
            
            if caption:
                confirmation_text += f"*Текст сообщения:*\n{caption}\n\n"
                
            confirmation_text += f"❓ *Вы уверены, что хотите отправить это сообщение всем пользователям?*"
            
            await update.message.reply_text(
                confirmation_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            context.user_data['waiting_for_broadcast'] = False
            return
    
    if context.user_data.get('waiting_for_broadcast'):
        if user.id in ADMIN_IDS:
            context.user_data['pending_broadcast'] = {
                'text': message_text,
                'photo_file_id': None,
                'user_id': user.id
            }
            
            keyboard = [
                [InlineKeyboardButton("✅ Да, отправить", callback_data=f"confirm_send_{update.message.message_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_send")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            confirmation_text = (
                f"📤 *ПОДТВЕРЖДЕНИЕ РАССЫЛКИ*\n\n"
                f"*Текст сообщения:*\n{message_text}\n\n"
                f"❓ *Вы уверены, что хотите отправить это сообщение всем пользователям?*"
            )
            
            await update.message.reply_text(
                confirmation_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            context.user_data['waiting_for_broadcast'] = False
            return

    print(f"🔍 ПОЛУЧЕНО СООБЩЕНИЕ:")
    print(f"   👤 Пользователь: {user.id} ({user.first_name})")
    print(f"   📝 Текст: {message_text}")
    print(f"   🏷️ Текущее состояние: {user_states.get(user.id, 'не установлено')}")
    
    if user.id not in user_states:
        user_states[user.id] = MAIN_MENU
        print(f"   ⚡ Установлено состояние MAIN_MENU для пользователя {user.id}")
    
    current_state = user_states[user.id]
    print(f"   🎯 Обработка состояния: {current_state}")
    
    try:
        if current_state == WAITING_SELF_NAME:
            print("   🚀 Переход к обработке имени для самоанализа")
            await handle_self_name(update, context)
        elif current_state == WAITING_SELF_DATE:
            print("   🚀 Переход к обработке даты для самоанализа")
            await handle_self_date(update, context)
        elif current_state == WAITING_PARTNER1_NAME:
            print("   🚀 Переход к обработке имени первого партнера")
            await handle_partner1_name(update, context)
        elif current_state == WAITING_PARTNER1_DATE:
            print("   🚀 Переход к обработке даты первого партнера")
            await handle_partner1_date(update, context)
        elif current_state == WAITING_PARTNER2_NAME:
            print("   🚀 Переход к обработке имени второго партнера")
            await handle_partner2_name(update, context)
        elif current_state == WAITING_PARTNER2_DATE:
            print("   🚀 Переход к обработке даты второго партнера")
            await handle_partner2_date(update, context)
        else:
            print("   🔄 Состояние не распознано, переход в главное меню")
            await start(update, context)
    except Exception as e:
        print(f"   ❌ ОШИБКА при обработке сообщения: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте еще раз или начните заново с /start")

def main():
    init_db()
        
    application = Application.builder().token(BOT_TOKEN).build()
    
    global subscription_manager
    subscription_manager = SubscriptionManager(bot=application.bot)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("send", send_message_command))
    application.add_handler(MessageHandler(
        filters.PHOTO & filters.CaptionRegex(r'^/send'), 
        send_message_command
    ))
    application.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE, 
        handle_broadcast_photo
    ))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_refresh$"))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^back_to_admin$"))
    application.add_handler(CommandHandler("activate", activate_command))
    application.add_handler(CommandHandler("subs", list_subscriptions_command))
    application.add_handler(CommandHandler("activate_my_sub", activate_subscription_command))
    application.add_handler(CommandHandler("payments", payments_command))
    application.add_handler(CommandHandler("refstats", check_referral_stats))
    application.add_handler(CommandHandler("debug_ref", debug_referral_system))
    application.add_handler(CommandHandler("debug", debug_admin))
    application.add_handler(CommandHandler("test_msg", test_message))
    application.add_handler(CommandHandler("cancel_activation", cancel_activation_command))
    
    print("🤖 БОТ ЗАПУЩЕН!")
    print(f"💎 Стоимость подписки: {SUBSCRIPTION_PRICE} руб.")
    print("🏦 Оплата через Т-Банк (ручное подтверждение)")
    print("🚀 Всё готово к работе!")
    
    application.run_polling()

if __name__ == '__main__':
    main()