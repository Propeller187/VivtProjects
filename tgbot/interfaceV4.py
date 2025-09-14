import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import threading
import importlib.util
import sys
import pymysql
import pymysql.cursors
import io, contextlib
import multiprocessing
import datetime
import pytz
import asyncio
import time
import requests
import tempfile
import nest_asyncio


BOT_PROCESS = None  # Глобальная переменная для процесса бота
def is_token_valid(token):
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        r = requests.get(url, timeout=5)
        data = r.json()
        return data.get("ok", False)
    except Exception as e:
        print(f"Ошибка проверки токена: {e}")
        return False
def restart_application():
    python = sys.executable
    os.execl(python, python, *sys.argv)
# Применяем патч для поддержки вложенных event loop
nest_asyncio.apply()

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext
from telegram.error import ChatMigrated

# Функция для копирования выделенного текста
def copy_text(widget):
    widget.event_generate("<<Copy>>")

# Функция для вставки текста из буфера обмена
def paste_text(widget):
    widget.event_generate("<<Paste>>")

# Добавление контекстного меню с копированием и вставкой
def add_context_menu(widget):
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Копировать", command=lambda: copy_text(widget))
    menu.add_command(label="Вставить", command=lambda: paste_text(widget))

    def show_menu(event):
        menu.tk_popup(event.x_root, event.y_root)

    widget.bind("<Button-3>", show_menu)  # Правая кнопка мыши
    widget.bind("<Control-c>", lambda event: copy_text(widget))  # Ctrl+C
    widget.bind("<Control-v>", lambda event: paste_text(widget))  # Ctrl+V



# --- Настройки телеграм-бота ---
def load_db_config():
    if os.path.exists("db_config.json"):
        with open("db_config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "host": "ilyasiux.beget.tech",
        "user": "ilyasiux_prop",
        "password": "Propeller187",
        "db": "ilyasiux_prop"
    }

def get_db_connection():
    global is_db_working
    try:
        config = load_db_config()
        test = pymysql.connect(
            host=config.get("host", "localhost"),
            user=config.get("user", "root"),
            password=config.get("password", ""),
            db=config.get("db", "test"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
        is_db_working = 1
        return pymysql.connect(
            host=config.get("host", "localhost"),
            user=config.get("user", "root"),
            password=config.get("password", ""),
            db=config.get("db", "test"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
    except:
        is_db_working = 0
        return pymysql.connect(
            host='ilyasiux.beget.tech',
            user='ilyasiux_prop',
            password='Propeller187',
            db='ilyasiux_prop',
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
# Получение данных из таблицы bot_settings (с автосозданием таблицы)
# Получение данных из таблицы bot_settings (с автосозданием таблицы)
def load_bot_settings():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Создание таблицы, если её нет
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            id INT PRIMARY KEY AUTO_INCREMENT,
            token VARCHAR(255) NOT NULL,
            chat_id BIGINT NOT NULL
        )
    """)

    # Проверка на наличие записей
    cursor.execute("SELECT COUNT(*) AS count FROM bot_settings")
    result = cursor.fetchone()

    # Если данных нет — добавляем начальные данные
    if result['count'] == 0:
        cursor.execute("""
            INSERT INTO bot_settings (token, chat_id)
            VALUES ('Введите токен', 0)
        """)
        conn.commit()

    # Загружаем настройки
    cursor.execute("SELECT token, chat_id FROM bot_settings LIMIT 1")
    bot_settings = cursor.fetchone()

    conn.close()
    return bot_settings if bot_settings else {"token": "Введите токен", "chat_id": 0}


# Сохранение новых данных и обновление глобальных переменных
def save_bot_settings(token, chat_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE bot_settings
        SET token = %s, chat_id = %s
        WHERE id = 1
    """, (token, chat_id))
    conn.commit()
    conn.close()

    # Автоматическое обновление глобальных переменных
    global TOKEN, SCHEDULED_CHAT_ID
    TOKEN = token
    SCHEDULED_CHAT_ID = chat_id
    print(f"Токен и ID чата обновлены: TOKEN={TOKEN}, CHAT_ID={SCHEDULED_CHAT_ID}")

def stop_current_bot():
    global BOT_APPLICATION, BOT_LOOP, BOT_THREAD
    if BOT_APPLICATION is not None and BOT_LOOP is not None:
        try:
            future_stop = asyncio.run_coroutine_threadsafe(BOT_APPLICATION.stop(), BOT_LOOP)
            future_stop.result(timeout=10)
            future_shutdown = asyncio.run_coroutine_threadsafe(BOT_APPLICATION.shutdown(), BOT_LOOP)
            future_shutdown.result(timeout=10)
        except Exception as e:
            print(f"Ошибка при остановке бота: {e}")
        BOT_APPLICATION = None
        # Ждём немного, чтобы getUpdates точно завершился
        time.sleep(1)

bot_settings = load_bot_settings()
TOKEN = bot_settings.get("token", "")
SCHEDULED_CHAT_ID = bot_settings.get("chat_id", 0)


class BotSettingsTab(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.create_widgets()

    def create_widgets(self):
        # Заголовок
        ttk.Label(self, text="Настройки бота", font=("Arial", 14)).pack(pady=10)

        # Токен бота
        ttk.Label(self, text="Токен бота:").pack(pady=5)
        self.token_var = tk.StringVar(value=TOKEN)
        token_entry = ttk.Entry(self, textvariable=self.token_var, width=50)
        token_entry.pack(pady=5)
        add_context_menu(token_entry)

        # ID чата
        ttk.Label(self, text="ID чата для рассылки:").pack(pady=5)
        self.chat_id_var = tk.StringVar(value=str(SCHEDULED_CHAT_ID))
        chat_id_entry = ttk.Entry(self, textvariable=self.chat_id_var, width=50)
        chat_id_entry.pack(pady=5)
        add_context_menu(chat_id_entry)

        # Кнопка для сохранения
        ttk.Button(self, text="Сохранить", command=self.save_bot_settings).pack(pady=10)

    def save_bot_settings(self):
        token = self.token_var.get()
        try:
            chat_id = int(self.chat_id_var.get())
            save_bot_settings(token, chat_id)  # обновляем БД и глобальные переменные TOKEN и SCHEDULED_CHAT_ID
            messagebox.showinfo("Успех", "Настройки бота обновлены и применены! Приложение перезапустит процесс бота.")
            global BOT_PROCESS
            if BOT_PROCESS is not None:
                BOT_PROCESS.terminate()  # завершаем старый процесс
                BOT_PROCESS.join(timeout=5)
            start_telegram_bot_process()  # запускаем новый процесс бота
        except ValueError:
            messagebox.showerror("Ошибка", "ID чата должен быть числом.")


# Глобальные переменные для телеграм-бота
start_time_bot = time.time()
message_count = {}
is_bot_active = True


# --- Создание таблицы задач ---
def create_tasks_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_tasks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category VARCHAR(255) NOT NULL,
            subcategory VARCHAR(255) NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            emoji VARCHAR(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT '✅'
        ) CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()
    cursor.close()
    conn.close()


create_tasks_table()


# ================= ФУНКЦИИ ТЕЛЕГРАМ-БОТА =================

def get_active_task():
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().time()
    query = """
        SELECT category, subcategory, start_time, end_time, emoji 
        FROM bot_tasks 
        WHERE start_time <= %s AND end_time >= %s 
        ORDER BY RAND() LIMIT 1
    """
    cursor.execute(query, (now, now))
    task = cursor.fetchone()
    cursor.close()
    conn.close()
    return task


def get_product_for_task(task):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM categories WHERE name = %s", (task['category'],))
    cat = cursor.fetchone()
    if not cat:
        conn.close()
        return None
    cat_id = cat['id']
    if task['subcategory'] is None:
        cursor.execute("""
            SELECT * FROM parsed_data 
            WHERE category_id = %s 
            ORDER BY RAND() LIMIT 1
        """, (cat_id,))
    else:
        cursor.execute("""
            SELECT id FROM subcategories 
            WHERE name = %s AND category_id = %s
        """, (task['subcategory'], cat_id))
        subcat = cursor.fetchone()
        if not subcat:
            conn.close()
            return None
        subcat_id = subcat['id']
        cursor.execute("""
            SELECT * FROM parsed_data 
            WHERE category_id = %s AND subcategory_id = %s 
            ORDER BY RAND() LIMIT 1
        """, (cat_id, subcat_id))
    product = cursor.fetchone()
    cursor.close()
    conn.close()
    return product


async def download_and_send_image(image_url, chat_id, context):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(response.content)
            temp_file.close()
            with open(temp_file.name, 'rb') as img_file:
                await context.bot.send_photo(chat_id=chat_id, photo=img_file)
            os.remove(temp_file.name)
    except requests.RequestException as e:
        print(f"Ошибка при скачивании картинки: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Не удалось скачать изображение.")


async def welcome_new_member(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    new_user = update.message.new_chat_members[0].first_name
    welcome_message = f"Привет, {new_user}! Добро пожаловать в наш чат!"
    try:
        await context.bot.send_message(chat_id=chat_id, text=welcome_message)
    except ChatMigrated as e:
        new_chat_id = e.migrate_to_chat_id
        await context.bot.send_message(chat_id=new_chat_id, text=welcome_message)


async def send_product_message(chat_id, context, message_text, image_url, emoji):
    message_text = f"{emoji * 3} {message_text}"
    if image_url and image_url != 'Изображение отсутствует':
        try:
            response = requests.get(image_url)
            response.raise_for_status()
            bio = io.BytesIO(response.content)
            bio.name = 'image.jpg'
            await context.bot.send_photo(chat_id=chat_id, photo=bio, caption=message_text)
        except requests.RequestException as e:
            print(f"Ошибка при скачивании картинки: {e}")
            await context.bot.send_message(chat_id=chat_id, text=message_text)
    else:
        await context.bot.send_message(chat_id=chat_id, text=message_text)


async def track_messages(update: Update, context: CallbackContext):
    global start_time_bot, is_bot_active, message_count
    if not is_bot_active:
        return
    if (time.time() - start_time_bot) < 3:
        return
    chat_id = update.message.chat.id
    if update.message.from_user.is_bot:
        return
    if chat_id not in message_count:
        message_count[chat_id] = 0
    message_count[chat_id] += 1
    if message_count[chat_id] == 3:
        task = get_active_task()
        if task:
            product = get_product_for_task(task)
            if product:
                title = product.get('title', 'Нет названия')
                description = product.get('description', 'Нет описания')
                emoji = task.get('emoji', '✅')
                message_text = f"\n{title}\n\nОписание: {description}"
                image_url = product.get('image_url', None)
                await send_product_message(chat_id, context, message_text, image_url, emoji)
            else:
                await context.bot.send_message(chat_id=chat_id, text="Нет товара для активной задачи.")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Нет активной задачи.")
        message_count[chat_id] = 0


async def toggle_bot(update: Update, context: CallbackContext):
    global is_bot_active, message_count
    is_bot_active = not is_bot_active
    status = "включен" if is_bot_active else "выключен"
    await update.message.reply_text(f"Бот теперь {status}.")
    message_count.clear()


async def scheduled_recipe(context: CallbackContext):
    task = get_active_task()
    if task:
        product = get_product_for_task(task)
        if product:
            title = product.get('title', 'Нет названия')
            description = product.get('description', 'Нет описания')
            message_text = f"Товар (по расписанию):\n{title}\n\nОписание: {description}"
            image_url = product.get('image_url', None)
            emoji = task.get('emoji', '✅')
            await send_product_message(SCHEDULED_CHAT_ID, context, message_text, image_url, emoji)
        else:
            await context.bot.send_message(chat_id=SCHEDULED_CHAT_ID, text="Нет товара для активной задачи.")
    else:
        await context.bot.send_message(chat_id=SCHEDULED_CHAT_ID, text="Нет активной задачи.")


# Глобальные переменные для управления ботом
BOT_THREAD = None                   # Ссылка на поток бота
BOT_APPLICATION = None              # Ссылка на экземпляр приложения бота
BOT_LOOP = None                     # Ссылка на event loop бота

async def bot_main():
    if not is_token_valid(TOKEN):
        print("Невалидный токен. Бот не запускается.")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.TEXT, track_messages))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex('^/toggle_bot$'), toggle_bot))
    moscow_tz = pytz.timezone("Europe/Moscow")
    scheduled_time = datetime.time(hour=18, minute=0, second=0, tzinfo=moscow_tz)
    app.job_queue.run_daily(scheduled_recipe, time=scheduled_time)
    await app.run_polling()



def run_bot():
    # Проверяем токен
    if TOKEN in ("0", 0, "", "Введите токен"):
        print("Невалидный токен. Бот не запускается.")
        return
    try:
        asyncio.run(bot_main())
    except Exception as e:
        print(f"Ошибка в работе телеграм-бота: {e}")



def start_telegram_bot_process():
    global BOT_PROCESS
    BOT_PROCESS = multiprocessing.Process(target=run_bot, daemon=True)
    BOT_PROCESS.start()





# ================= КЛАСС TasksTab (интерфейс задач для бота) =================

class TasksTab(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.create_widgets()
        self.refresh_categories()
        self.refresh_tasks()

    def create_widgets(self):
        frame = ttk.Frame(self)
        frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame, text="Категория:").grid(row=0, column=0, sticky="w")
        self.category_var = tk.StringVar()
        self.category_cb = ttk.Combobox(frame, textvariable=self.category_var, state="readonly")
        self.category_cb.grid(row=0, column=1, sticky="ew", padx=5)
        self.category_cb.bind("<<ComboboxSelected>>", self.refresh_subcategories)

        ttk.Label(frame, text="Подкатегория:").grid(row=1, column=0, sticky="w")
        self.subcategory_var = tk.StringVar()
        self.subcategory_cb = ttk.Combobox(frame, textvariable=self.subcategory_var, state="readonly")
        self.subcategory_cb.grid(row=1, column=1, sticky="ew", padx=5)

        ttk.Label(frame, text="Смайлик:").grid(row=2, column=0, sticky="w")
        self.emoji_var = tk.StringVar(value="✅")
        self.emoji_cb = ttk.Combobox(frame, textvariable=self.emoji_var, state="readonly")
        self.emoji_cb['values'] = ["✅", "🔥", "🌟", "🍕", "🎁", "💥", "💎", "⚡", "📦", "📣"]
        self.emoji_cb.grid(row=2, column=1, sticky="ew", padx=5)

        ttk.Label(frame, text="Время начала (ЧЧ:ММ):").grid(row=3, column=0, sticky="w")
        self.start_time_var = tk.StringVar(value="08:00")
        ttk.Entry(frame, textvariable=self.start_time_var, width=10).grid(row=3, column=1, sticky="w", padx=5)

        ttk.Label(frame, text="Время окончания (ЧЧ:ММ):").grid(row=4, column=0, sticky="w")
        self.end_time_var = tk.StringVar(value="12:00")
        ttk.Entry(frame, textvariable=self.end_time_var, width=10).grid(row=4, column=1, sticky="w", padx=5)

        ttk.Button(self, text="Добавить задачу", command=self.add_task).pack(pady=5)

        ttk.Label(self, text="Список задач:").pack(anchor="w", padx=10, pady=(10, 0))
        self.tasks_listbox = tk.Listbox(self, height=8)
        self.tasks_listbox.pack(fill="both", expand=True, padx=10, pady=5)

        ttk.Button(self, text="Удалить выбранную задачу", command=self.delete_task).pack(pady=5)

    def refresh_categories(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories")
        categories = [row['name'] for row in cursor.fetchall()]
        conn.close()
        self.category_cb['values'] = categories
        if categories:
            self.category_var.set(categories[0])
            self.refresh_subcategories()

    def refresh_subcategories(self, event=None):
        category = self.category_var.get()
        if not category:
            self.subcategory_cb['values'] = []
            self.subcategory_var.set('')
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.name FROM subcategories s
            JOIN categories c ON s.category_id = c.id
            WHERE c.name = %s
        """, (category,))
        subcategories = [row['name'] for row in cursor.fetchall()]
        conn.close()
        subcategories.insert(0, "Все подкатегории")
        self.subcategory_cb['values'] = subcategories
        self.subcategory_var.set("Все подкатегории")

    def add_task(self):
        category = self.category_var.get()
        subcategory = self.subcategory_var.get()
        emoji = self.emoji_var.get()
        start_time = self.start_time_var.get()
        end_time = self.end_time_var.get()
        if subcategory == "Все подкатегории":
            subcategory = None
        try:
            datetime.datetime.strptime(start_time, "%H:%M")
            datetime.datetime.strptime(end_time, "%H:%M")
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат времени. Используйте ЧЧ:ММ")
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bot_tasks (category, subcategory, start_time, end_time, emoji)
            VALUES (%s, %s, %s, %s, %s)
        """, (category, subcategory, start_time, end_time, emoji))
        conn.commit()
        conn.close()
        messagebox.showinfo("Успех", "Задача добавлена.")
        self.refresh_tasks()

    def refresh_tasks(self):
        self.tasks_listbox.delete(0, tk.END)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bot_tasks")
        tasks = cursor.fetchall()

        valid_tasks = []
        for row in tasks:
            # Если подкатегория указана, проверим, существует ли она в таблице subcategories
            if row['subcategory']:
                cursor.execute("SELECT COUNT(*) as cnt FROM subcategories WHERE name = %s", (row['subcategory'],))
                res = cursor.fetchone()
                if res['cnt'] == 0:
                    # Если такой подкатегории нет, пропускаем запись (или можно удалить её из базы)
                    continue
            valid_tasks.append(row)

        conn.close()

        for row in valid_tasks:
            subcat_display = row['subcategory'] if row['subcategory'] else "Все подкатегории"
            task_str = f"{row['id']}: {row['emoji']} {row['category']} - {subcat_display} ({row['start_time']} - {row['end_time']})"
            self.tasks_listbox.insert(tk.END, task_str)

    def delete_task(self):
        selection = self.tasks_listbox.curselection()
        if not selection:
            messagebox.showerror("Ошибка", "Выберите задачу для удаления.")
            return
        task_str = self.tasks_listbox.get(selection[0])
        try:
            task_id = task_str.split(":")[0].strip()
        except Exception:
            messagebox.showerror("Ошибка", "Неверный формат задачи.")
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bot_tasks WHERE id = %s", (task_id,))
        conn.commit()
        conn.close()
        messagebox.showinfo("Успех", "Задача удалена.")
        self.refresh_tasks()








def run_module_worker(q, file_path, cat_name, subcat_name):
    """
    Функция выполняется в отдельном процессе.
    Она импортирует модуль, выполняет его parsing() (или берёт data) и сохраняет данные,
    затем кладёт накопленный вывод в очередь.
    """
    output_capture = io.StringIO()
    with contextlib.redirect_stdout(output_capture):
        try:
            spec = importlib.util.spec_from_file_location("dynamic_module", file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "parsing"):
                parsed_data = module.parsing()
            elif hasattr(module, "data"):
                parsed_data = module.data
            else:
                parsed_data = None
            if parsed_data is None:
                print("Не найдена переменная 'data' или функция parsing() в модуле.")
            else:
                result = save_parsed_data_worker(cat_name, subcat_name, parsed_data)
                print(result)
        except Exception as e:
            print(f"Ошибка при запуске модуля: {e}")
    q.put(output_capture.getvalue())

def save_parsed_data_worker(cat_name, subcat_name, parsed_data):
    """
    Функция сохраняет данные в базу данных.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM categories WHERE name = %s", (cat_name,))
        cat_row = cursor.fetchone()
        if not cat_row:
            return f"Категория '{cat_name}' не найдена."
        cat_id = cat_row['id']
        cursor.execute("SELECT id FROM subcategories WHERE name = %s AND category_id = %s", (subcat_name, cat_id))
        subcat_row = cursor.fetchone()
        if not subcat_row:
            return f"Подкатегория '{subcat_name}' не найдена."
        subcat_id = subcat_row['id']
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parsed_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                category_id INT,
                subcategory_id INT,
                title VARCHAR(255),
                description TEXT,
                image_url TEXT,
                link TEXT,
                sub_description TEXT,
                `current_date` DATETIME,
                status INT DEFAULT 0
            )
        """)
        insert_sql = """
            INSERT INTO parsed_data 
            (category_id, subcategory_id, title, description, image_url, link, sub_description, `current_date`, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        inserted_count = 0
        for row in parsed_data:
            cursor.execute(insert_sql, (
                cat_id,
                subcat_id,
                row['title'],
                row['description'],
                row['image_url'],
                row['link'],
                row['sub_description'],
                row['current_date'],
                0
            ))
            inserted_count += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Ошибка при вставке данных в базу: {e}"
    finally:
        conn.close()
    return f"Успешно сохранено {inserted_count} записей."

# Файл для сохранения данных (категории, подкатегории и модули)
DATA_FILE = "data.json"
data = {"categories": []}

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"categories": []}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


class CategoriesTab(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.update_callback = None
        self.create_widgets()
        self.selected_category = None
        self.selected_subcategory = None
        self.refresh_categories()

    def refresh_subcategories(self):
        if not self.selected_category:
            self.subcat_listbox.delete(0, tk.END)
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subcategories WHERE category_id = (SELECT id FROM categories WHERE name = %s)",
                       (self.selected_category,))
        subcategories = cursor.fetchall()
        conn.close()
        self.subcat_listbox.delete(0, tk.END)
        for sub in subcategories:
            self.subcat_listbox.insert(tk.END, sub["name"])

    def set_update_callback(self, callback):
        self.update_callback = callback

    def create_widgets(self):
        frame_add_cat = ttk.Frame(self)
        frame_add_cat.pack(fill='x', pady=5)
        self.cat_name_var = tk.StringVar()
        ttk.Label(frame_add_cat, text="Название категории:").pack(side='left')
        ttk.Entry(frame_add_cat, textvariable=self.cat_name_var).pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(frame_add_cat, text="Добавить категорию", command=self.add_category).pack(side='left')

        self.cat_listbox = tk.Listbox(self, height=8)
        self.cat_listbox.pack(fill='both', expand=True, pady=5)
        self.cat_listbox.bind("<<ListboxSelect>>", self.on_category_select)
        ttk.Button(self, text="Удалить выбранную категорию", command=self.delete_category).pack(pady=2)

        frame_add_subcat = ttk.Frame(self)
        frame_add_subcat.pack(fill='x', pady=5)
        self.subcat_var = tk.StringVar()
        ttk.Label(frame_add_subcat, text="Название подкатегории:").pack(side='left')
        ttk.Entry(frame_add_subcat, textvariable=self.subcat_var).pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(frame_add_subcat, text="Добавить подкатегорию", command=self.add_subcategory).pack(side='left')

        self.subcat_listbox = tk.Listbox(self, height=5)
        self.subcat_listbox.pack(fill='both', expand=True, pady=5)
        ttk.Button(self, text="Удалить выбранную подкатегорию", command=self.delete_subcategory).pack(pady=2)

    def add_subcategory(self):
        category_selection = self.cat_listbox.curselection()
        if not category_selection:
            messagebox.showerror("Ошибка", "Сначала выберите категорию.")
            return
        category_name = self.cat_listbox.get(category_selection[0])
        sub_name = self.subcat_var.get().strip()
        if sub_name:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM subcategories WHERE name = %s AND category_id = (SELECT id FROM categories WHERE name = %s)",
                (sub_name, category_name))
            existing_subcategory = cursor.fetchone()
            if existing_subcategory:
                messagebox.showerror("Ошибка", "Такая подкатегория уже существует.")
                conn.close()
                return
            cursor.execute(
                "INSERT INTO subcategories (name, category_id) VALUES (%s, (SELECT id FROM categories WHERE name = %s))",
                (sub_name, category_name))
            conn.commit()
            conn.close()
            self.subcat_var.set("")
            self.on_category_select(None)
            messagebox.showinfo("Добавление", f"Подкатегория '{sub_name}' успешно добавлена.")
            if self.update_callback:
                self.update_callback()

    def refresh_categories(self):
        self.cat_listbox.delete(0, tk.END)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories")
        categories = cursor.fetchall()
        conn.close()
        for cat in categories:
            self.cat_listbox.insert(tk.END, cat["name"])
        self.subcat_listbox.delete(0, tk.END)

    def add_category(self):
        name = self.cat_name_var.get().strip()
        if not name:
            messagebox.showerror("Ошибка", "Введите название категории.")
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories WHERE name = %s", (name,))
        if cursor.fetchone():
            messagebox.showerror("Ошибка", "Такая категория уже существует.")
            conn.close()
            return
        cursor.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
        conn.commit()
        conn.close()
        self.cat_name_var.set("")
        self.refresh_categories()
        if self.update_callback:
            self.update_callback()
        messagebox.showinfo("Успех", f"Категория '{name}' добавлена.")

    def delete_category(self):
        selection = self.cat_listbox.curselection()
        if not selection:
            messagebox.showerror("Ошибка", "Выберите категорию для удаления.")
            return
        index = selection[0]
        category_name = self.cat_listbox.get(index)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM categories WHERE name = %s", (category_name,))
        category = cursor.fetchone()
        if not category:
            conn.close()
            messagebox.showerror("Ошибка", f"Категория '{category_name}' не найдена.")
            return
        category_id = category['id']
        cursor.execute("""
            DELETE FROM parsed_data
            WHERE category_id = %s OR subcategory_id IN (
                SELECT id FROM subcategories WHERE category_id = %s
            )
        """, (category_id, category_id))
        cursor.execute("""
            DELETE FROM modules
            WHERE category_id = %s OR subcategory_id IN (
                SELECT id FROM subcategories WHERE category_id = %s
            )
        """, (category_id, category_id))
        cursor.execute("DELETE FROM subcategories WHERE category_id = %s", (category_id,))
        cursor.execute("DELETE FROM categories WHERE id = %s", (category_id,))
        conn.commit()
        conn.close()
        self.refresh_categories()
        self.subcat_listbox.delete(0, tk.END)
        self.selected_category = None
        if self.update_callback:
            self.update_callback()
        messagebox.showinfo("Удаление", f"Категория '{category_name}' и связанные данные удалены.")

    def on_category_select(self, event):
        selection = self.cat_listbox.curselection()
        if selection:
            index = selection[0]
            category_name = self.cat_listbox.get(index)
            self.selected_category = category_name
            self.refresh_subcategories()

    def delete_subcategory(self):
        sub_selection = self.subcat_listbox.curselection()
        if not sub_selection:
            messagebox.showerror("Ошибка", "Выберите подкатегорию для удаления.")
            return
        sub_name = self.subcat_listbox.get(sub_selection[0])
        if not self.selected_category:
            messagebox.showerror("Ошибка", "Сначала выберите категорию.")
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM subcategories 
            WHERE name = %s AND category_id = (SELECT id FROM categories WHERE name = %s)
        """, (sub_name, self.selected_category))
        subcat = cursor.fetchone()
        if not subcat:
            conn.close()
            messagebox.showerror("Ошибка", f"Подкатегория '{sub_name}' не найдена.")
            return
        subcat_id = subcat['id']
        cursor.execute("DELETE FROM modules WHERE subcategory_id = %s", (subcat_id,))
        cursor.execute("DELETE FROM parsed_data WHERE subcategory_id = %s", (subcat_id,))
        cursor.execute("DELETE FROM subcategories WHERE id = %s", (subcat_id,))
        conn.commit()
        conn.close()
        self.refresh_subcategories()
        messagebox.showinfo("Удаление", f"Подкатегория '{sub_name}' успешно удалена.")
        if self.update_callback:
            self.update_callback()

class ModulesTab(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.current_process = None
        self.scheduled_tasks = {}  # Храним планировщики
        self.create_widgets()
        self.refresh_category_dropdown()
        self.refresh_modules_list()
        self.schedule_all_modules()  # Автопланирование при запуске

    def schedule_all_modules(self):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, start_time FROM modules WHERE start_time IS NOT NULL")
        for row in cursor.fetchall():
            self.schedule_module(row['name'], row['start_time'])
        conn.close()

    def set_update_callback(self, callback):
        self.update_callback = callback

    def create_widgets(self):
        frame_add_module = ttk.Frame(self)
        frame_add_module.pack(fill='x', pady=5)

        ttk.Label(frame_add_module, text="Название модуля:").grid(row=0, column=0, sticky="w")
        self.module_name_var = tk.StringVar()
        ttk.Entry(frame_add_module, textvariable=self.module_name_var).grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(frame_add_module, text="Путь к файлу:").grid(row=1, column=0, sticky="w")
        self.module_path_var = tk.StringVar()
        ttk.Entry(frame_add_module, textvariable=self.module_path_var).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(frame_add_module, text="Обзор", command=self.browse_file).grid(row=1, column=2, padx=5)

        ttk.Label(frame_add_module, text="Категория:").grid(row=2, column=0, sticky="w")
        self.selected_category_var = tk.StringVar()
        self.category_dropdown = ttk.Combobox(frame_add_module, textvariable=self.selected_category_var,
                                              state="readonly")
        self.category_dropdown.grid(row=2, column=1, sticky="ew", padx=5)
        self.category_dropdown.bind("<<ComboboxSelected>>", self.update_subcategory_dropdown)

        ttk.Label(frame_add_module, text="Подкатегория:").grid(row=3, column=0, sticky="w")
        self.selected_subcategory_var = tk.StringVar()
        self.subcategory_dropdown = ttk.Combobox(frame_add_module, textvariable=self.selected_subcategory_var,
                                                 state="readonly")
        self.subcategory_dropdown.grid(row=3, column=1, sticky="ew", padx=5)

        ttk.Label(frame_add_module, text="Время запуска (ЧЧ:ММ, опционально):").grid(row=4, column=0, sticky="w")
        self.start_time_var = tk.StringVar()
        ttk.Entry(frame_add_module, textvariable=self.start_time_var).grid(row=4, column=1, sticky="ew", padx=5)

        frame_add_module.columnconfigure(1, weight=1)
        ttk.Button(frame_add_module, text="Добавить модуль", command=self.add_module).grid(row=5, column=0,
                                                                                           columnspan=3, pady=5)

        ttk.Label(self, text="Подключённые модули:").pack(anchor="w", padx=5)
        self.modules_listbox = tk.Listbox(self, height=8)
        self.modules_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.modules_listbox.bind("<<ListboxSelect>>", self.on_module_select)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill='x', pady=5)
        ttk.Button(button_frame, text="Удалить модуль", command=self.delete_selected_module).pack(side="left", padx=5)
        self.run_button = ttk.Button(button_frame, text="Запустить модуль", command=self.run_selected_module)
        self.run_button.pack(side="left", padx=5)
        self.stop_button = ttk.Button(button_frame, text="Остановить модуль", command=self.stop_selected_module)
        self.stop_button.pack(side="left", padx=5)

        # Окно для вывода результата работы модуля (интегрировано в эту вкладку)
        self.output_text = tk.Text(self, height=10, state='disabled', bg="black", fg="lime")
        self.output_text.pack(fill="both", expand=True, padx=5, pady=5)

    def display_output(self, text):
        self.output_text.configure(state='normal')
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, text)
        self.output_text.configure(state='disabled')

    def on_module_select(self, event):
        selection = self.modules_listbox.curselection()
        if selection:
            index = selection[0]
            conn = self.get_db_connection()
            cursor = conn.cursor()
            query = """
                SELECT m.id, m.name as module_name, m.file_path, c.name as category, s.name as subcategory
                FROM modules m
                JOIN categories c ON m.category_id = c.id
                JOIN subcategories s ON m.subcategory_id = s.id
                ORDER BY m.id
            """
            cursor.execute(query)
            modules = cursor.fetchall()
            conn.close()
            if index < len(modules):
                module = modules[index]
                self.display_output(f"Выбран модуль:\nНазвание: {module['module_name']}\n"
                                    f"Категория: {module['category']}\nПодкатегория: {module['subcategory']}\n"
                                    f"Путь: {module['file_path']}\n")

    def add_module(self):
        module_name = self.module_name_var.get().strip()
        module_path = self.module_path_var.get().strip()
        category_name = self.selected_category_var.get().strip()
        subcategory_name = self.selected_subcategory_var.get().strip()
        start_time = self.start_time_var.get().strip() or None
        if start_time:
            try:
                datetime.datetime.strptime(start_time, "%H:%M")
            except ValueError:
                messagebox.showerror("Ошибка", "Формат времени: ЧЧ:ММ")
                return

        conn = self.get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM categories WHERE name=%s", (category_name,))
        category_id = cursor.fetchone()['id']

        cursor.execute("SELECT id FROM subcategories WHERE name=%s AND category_id=%s", (subcategory_name, category_id))
        subcategory_id = cursor.fetchone()['id']

        cursor.execute("""
                    INSERT INTO modules (name, file_path, category_id, subcategory_id, start_time) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (module_name, module_path, category_id, subcategory_id, start_time))

        conn.commit()
        conn.close()
        self.refresh_modules_list()
        self.schedule_module(module_name, start_time)

        if not module_name or not module_path or not category_name or not subcategory_name:
            messagebox.showerror("Ошибка", "Все поля должны быть заполнены.")
            return
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM categories WHERE name = %s", (category_name,))
        category = cursor.fetchone()
        if not category:
            messagebox.showerror("Ошибка", f"Категория '{category_name}' не найдена.")
            return
        category_id = category['id']
        cursor.execute("SELECT id FROM subcategories WHERE name = %s AND category_id = %s",
                       (subcategory_name, category_id))
        subcategory = cursor.fetchone()
        if not subcategory:
            messagebox.showerror("Ошибка", f"Подкатегория '{subcategory_name}' не найдена.")
            return
        subcategory_id = subcategory['id']
        messagebox.showinfo("Успех", "Модуль успешно добавлен.")
        self.refresh_modules_list()
        self.refresh_category_dropdown()

    def run_module_by_name(self, module_name):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.file_path, c.name as category, s.name as subcategory, m.start_time 
            FROM modules m
            JOIN categories c ON m.category_id = c.id
            JOIN subcategories s ON m.subcategory_id = s.id
            WHERE m.name = %s
        """, (module_name,))
        module = cursor.fetchone()
        conn.close()

        if module:
            self.start_process(module['file_path'], module['category'], module['subcategory'])
            # Если время запуска задано, планируем на следующий день
            if module.get('start_time'):
                self.schedule_module(module_name, module['start_time'])

    def schedule_module(self, module_name, start_time):
        if not start_time:
            return
        now = datetime.datetime.now()
        # Обработка start_time в зависимости от типа:
        if isinstance(start_time, str):
            run_time = datetime.datetime.strptime(start_time, "%H:%M").time()
        elif isinstance(start_time, datetime.time):
            run_time = start_time
        elif isinstance(start_time, datetime.timedelta):
            run_time = (datetime.datetime.min + start_time).time()
        else:
            # Если тип неизвестен, пропускаем планирование
            return

        run_datetime = datetime.datetime.combine(now.date(), run_time)
        if run_datetime < now:
            run_datetime += datetime.timedelta(days=1)
        delay = (run_datetime - now).total_seconds()
        timer = threading.Timer(delay, self.run_module_by_name, args=(module_name,))
        timer.start()
        self.scheduled_tasks[module_name] = timer

    def delete_selected_module(self):
        selection = self.modules_listbox.curselection()
        if not selection:
            messagebox.showerror("Ошибка", "Сначала выберите модуль для удаления.")
            return
        index = selection[0]
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM modules ORDER BY id")
        modules = cursor.fetchall()
        conn.close()
        if index < len(modules):
            module_id = modules[index]['id']
            confirm = messagebox.askyesno("Подтверждение",
                                          "Вы уверены, что хотите удалить выбранный модуль?\nТовары, запарсенные по этой категории/подкатегории, останутся в базе.")
            if confirm:
                conn = self.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM modules WHERE id = %s", (module_id,))
                conn.commit()
                conn.close()
                messagebox.showinfo("Успех", "Модуль успешно удалён.")
                self.refresh_modules_list()

    def run_selected_module(self):
        selection = self.modules_listbox.curselection()
        if not selection:
            messagebox.showerror("Ошибка", "Сначала выберите модуль.")
            return
        self.run_button.config(state="disabled")
        self.stop_button.config(state="normal")
        index = selection[0]
        conn = self.get_db_connection()
        cursor = conn.cursor()
        query = """
           SELECT m.file_path, c.name as category, s.name as subcategory
           FROM modules m
           JOIN categories c ON m.category_id = c.id
           JOIN subcategories s ON m.subcategory_id = s.id
           ORDER BY m.id
        """
        cursor.execute(query)
        modules = cursor.fetchall()
        conn.close()
        if index < len(modules):
            module_record = modules[index]
            module_path = module_record['file_path']
            cat_name = module_record['category']
            subcat_name = module_record['subcategory']
            self.start_process(module_path, cat_name, subcat_name)

    def start_process(self, file_path, cat_name, subcat_name):
        q = multiprocessing.Queue()
        self.current_process = multiprocessing.Process(target=run_module_worker,
                                                       args=(q, file_path, cat_name, subcat_name))
        self.current_process.start()

        def check_output():
            if not q.empty():
                output = q.get()
                self.display_output(output)
                self.run_button.config(state="normal")
                self.stop_button.config(state="disabled")
                self.current_process = None
            else:
                if self.current_process is not None and self.current_process.is_alive():
                    self.after(100, check_output)
                else:
                    self.run_button.config(state="normal")
                    self.stop_button.config(state="disabled")
                    self.current_process = None

        check_output()

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Выберите файл модуля",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if file_path:
            self.module_path_var.set(file_path)


    def update_subcategory_dropdown(self, event=None):
        category = self.selected_category_var.get()
        if not category:
            self.subcategory_dropdown['values'] = []
            self.selected_subcategory_var.set('')
            return
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM categories WHERE name = %s", (category,))
        cat_row = cursor.fetchone()
        if not cat_row:
            self.subcategory_dropdown['values'] = []
            self.selected_subcategory_var.set('')
            conn.close()
            return
        cat_id = cat_row['id']
        cursor.execute("SELECT name FROM subcategories WHERE category_id = %s", (cat_id,))
        subcategories = [row['name'] for row in cursor.fetchall()]
        conn.close()
        self.subcategory_dropdown['values'] = subcategories
        if subcategories:
            self.selected_subcategory_var.set(subcategories[0])
        else:
            self.selected_subcategory_var.set('')

    def refresh_category_dropdown(self):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories")
        categories = [row['name'] for row in cursor.fetchall()]
        conn.close()
        self.category_dropdown['values'] = categories
        if categories:
            self.selected_category_var.set(categories[0])
        else:
            self.selected_category_var.set('')
        self.update_subcategory_dropdown()

    def refresh_modules_list(self):
        self.modules_listbox.delete(0, tk.END)
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, start_time FROM modules")
        for module in cursor.fetchall():
            time_display = f" ({module['start_time']})" if module['start_time'] else ""
            self.modules_listbox.insert(tk.END, module['name'] + time_display)
        conn.close()

    def stop_selected_module(self):
        if self.current_process is not None and self.current_process.is_alive():
            self.current_process.terminate()
            self.current_process.join(timeout=2)
            if self.current_process.is_alive():
                print("Не удалось завершить процесс принудительно")
            else:
                print("Процесс успешно завершен")
            self.current_process = None
            self.run_button.config(state="normal")
            self.stop_button.config(state="disabled")
        else:
            messagebox.showinfo("Информация", "Нет запущенного модуля для остановки.")

    def get_db_connection(self):
        global is_db_working
        try:
            config = load_db_config()
            test = pymysql.connect(
                host=config.get("host", "localhost"),
                user=config.get("user", "root"),
                password=config.get("password", ""),
                db=config.get("db", "test"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor
            )
            is_db_working = 1
            return pymysql.connect(
                host=config.get("host", "localhost"),
                user=config.get("user", "root"),
                password=config.get("password", ""),
                db=config.get("db", "test"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor
            )
        except:
            is_db_working = 0
            return pymysql.connect(
                host='ilyasiux.beget.tech',
                user='ilyasiux_prop',
                password='Propeller187',
                db='ilyasiux_prop',
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor
            )


class DatabaseSettingsTab(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.create_widgets()
        self.load_db_settings()

    def create_widgets(self):
        ttk.Label(self, text="Настройки базы данных", font=("Arial", 14)).pack(pady=10)

        self.db_params = {}
        fields = ["host", "user", "password", "db"]

        for field in fields:
            ttk.Label(self, text=f"{field.capitalize()}: ").pack(pady=5)
            var = tk.StringVar()
            entry = ttk.Entry(self, textvariable=var, width=50)
            entry.pack(pady=5)
            add_context_menu(entry)
            self.db_params[field] = var

        ttk.Button(self, text="Сохранить", command=self.save_db_settings).pack(pady=10)

        if is_db_working == 0:
            ttk.Label(self, text="Внимание!", font=("Arial", 12)).pack(pady=10)
            ttk.Label(self, text="Подключение к вашей базе данных не было успешно. Сейчас используется стандартная база данных.", font=("Arial", 10)).pack(pady=10)

    def load_db_settings(self):
        if os.path.exists("db_config.json"):
            with open("db_config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            for key, var in self.db_params.items():
                var.set(config.get(key, ""))

    def save_db_settings(self):
        config = {key: var.get() for key, var in self.db_params.items()}
        with open("db_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        messagebox.showinfo("Успех", "Настройки базы данных сохранены. Они вступят в силу при следующем запуске.")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Интерфейс парсинга")
        self.geometry("700x700")
        self.create_widgets()
        start_telegram_bot_process()  # запускаем бот сразу при старте приложения

    def create_widgets(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # Вкладка "Категории"
        self.categories_tab = CategoriesTab(self.notebook)
        self.notebook.add(self.categories_tab, text="Категории")

        # Вкладка "Модули"
        self.modules_tab = ModulesTab(self.notebook)
        self.notebook.add(self.modules_tab, text="Модули")

        # Вкладка "Задачи"
        self.tasks_tab = TasksTab(self.notebook)
        self.notebook.add(self.tasks_tab, text="Задачи")

        # Вкладка "Настройки"
        self.bot_settings_tab = BotSettingsTab(self.notebook)
        self.notebook.add(self.bot_settings_tab, text="Настройки")

        # Вкладка "База данных"
        self.db_settings_tab = DatabaseSettingsTab(self.notebook)
        self.notebook.add(self.db_settings_tab, text="База данных")

        # Обратный вызов для обновлений
        self.categories_tab.set_update_callback(lambda: (
            self.modules_tab.refresh_category_dropdown(),
            self.modules_tab.refresh_modules_list(),
            self.tasks_tab.refresh_categories(),
            self.tasks_tab.refresh_tasks()
        ))




if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    app = App()
    app.mainloop()
