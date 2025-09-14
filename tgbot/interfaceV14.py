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
import datetime
import pytz
import asyncio
import time
import requests
import tempfile
import nest_asyncio
from telegram import Bot, Update
import subprocess
import emoji

DB_CONFIG = None

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
def paste_text(widget, event=None):
    try:
        text = widget.clipboard_get()
        print("Вставляем текст:", text)  # для отладки
        widget.insert(tk.INSERT, text)
    except Exception as e:
        print("Ошибка при вставке:", e)
    return "break"




# Добавление контекстного меню с копированием и вставкой
def add_context_menu(widget):
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Копировать", command=lambda: copy_text(widget))
    menu.add_command(label="Вставить", command=lambda: paste_text(widget))

    def show_menu(event):
        menu.tk_popup(event.x_root, event.y_root)

    widget.bind("<Button-3>", show_menu)  # Правая кнопка мыши
    widget.bind("<Control-c>", lambda event: copy_text(widget))  # Ctrl+C
    widget.bind("<Control-v>", lambda event: paste_text(widget, event))  # Ctrl+V



DB_CONFIG = None
is_db_working = 1
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
    global DB_CONFIG, is_db_working
    if not DB_CONFIG:
        DB_CONFIG = load_db_config()
        if not DB_CONFIG:
            raise Exception("Ошибка: DB_CONFIG не загружен, сначала выполните авторизацию!")
    try:
        conn = pymysql.connect(
            host=DB_CONFIG.get("host", "localhost"),
            user=DB_CONFIG.get("user", "root"),
            password=DB_CONFIG.get("password", ""),
            db=DB_CONFIG.get("db", "test"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
        is_db_working = 1
        return conn
    except Exception as e:
        print(f"Ошибка подключения с новыми настройками: {e}")
        is_db_working = 0
        # Фолбэк-подключение
        return pymysql.connect(
            host='ilyasiux.beget.tech',
            user='ilyasiux_prop',
            password='Propeller187',
            db='ilyasiux_prop',
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Создание таблицы categories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE
        )
    """)

    # Создание таблицы subcategories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subcategories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            category_id INT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        )
    """)

    # Создание таблицы modules
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS modules (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            file_path TEXT NOT NULL,
            category_id INT NOT NULL,
            subcategory_id INT NOT NULL,
            start_time TIME DEFAULT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
            FOREIGN KEY (subcategory_id) REFERENCES subcategories(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()

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
def update_bot_settings(token, chat_id):
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
DB_CONFIG = {}
TOKEN = ""
SCHEDULED_CHAT_ID = 0


BOT_PROCESS = None
BOT_STATUS = False  # Флаг состояния бота (True — работает, False — выключен)

class BotSettingsTab(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.create_widgets()
        self.refresh_bot_settings()


    def create_widgets(self):
        ttk.Label(self, text="Настройки бота", font=("Arial", 14)).pack(pady=10)

        # Поле для ввода токена + кнопка "Вставить"
        token_frame = ttk.Frame(self)
        token_frame.pack(pady=5, fill="x")
        ttk.Label(token_frame, text="Токен бота:").pack(side="left")
        self.token_var = tk.StringVar(value=TOKEN)
        self.token_entry = ttk.Entry(token_frame, textvariable=self.token_var, width=40)
        self.token_entry.pack(side="left", padx=(5, 5))
        add_context_menu(self.token_entry)
        ttk.Button(token_frame, text="Вставить", command=self.insert_clipboard_token).pack(side="left")

        # Индикатор состояния бота
        self.status_label = ttk.Label(self, text="🔴 Бот выключен", foreground="red", font=("Arial", 12))
        self.status_label.pack(pady=5)

        # Кнопка Включить/Выключить бота
        self.toggle_button = ttk.Button(self, text="Включить бота", command=self.toggle_bot)
        self.toggle_button.pack(pady=5)

        # Список чатов
        ttk.Label(self, text="Список чатов:").pack(pady=5)
        frame_chat_list = ttk.Frame(self)
        frame_chat_list.pack(fill="both", expand=True, padx=10, pady=5)

        # Создаём Listbox для чатов
        self.chat_listbox = tk.Listbox(frame_chat_list, height=8)
        self.chat_listbox.pack(side="left", fill="both", expand=True)

        # Вертикальный скроллбар для списка чатов
        chat_scrollbar = ttk.Scrollbar(frame_chat_list, orient="vertical", command=self.chat_listbox.yview)
        chat_scrollbar.pack(side="right", fill="y")
        self.chat_listbox.config(yscrollcommand=chat_scrollbar.set)

        # Кнопка "Получить список чатов"
        ttk.Button(self, text="Получить список чатов", command=self.get_chat_list).pack(pady=5)

        # Кнопка "Проверить права"
        ttk.Button(self, text="Проверить права", command=self.check_admin_rights).pack(pady=5)

        # Кнопка "Сохранить"
        ttk.Button(self, text="Сохранить", command=self.save_bot_settings).pack(pady=10)

    def refresh_bot_settings(self):
        # Перечитываем настройки из базы
        bot_settings = load_bot_settings()
        # Обновляем поле токена и другие настройки
        self.token_var.set(bot_settings.get("token", "Введите токен"))
        # Если нужно, обновите и список чатов или другие данные

    def insert_clipboard_token(self):
        """Вставляет текст из буфера обмена в поле токена."""
        try:
            text = self.clipboard_get()
            self.token_var.set(text)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось получить текст из буфера: {e}")

    def insert_clipboard_token(self):
        try:
            text = self.clipboard_get()
            self.token_var.set(text)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось получить текст из буфера: {e}")

    def get_chat_list(self):
        token = self.token_var.get()
        if BOT_STATUS:  # Если бот уже запущен, предупредить пользователя
            messagebox.showerror("Ошибка", "Остановите бота перед получением списка чатов!")
            return
        if not token:
            messagebox.showerror("Ошибка", "Введите токен бота!")
            return
        asyncio.run(self.fetch_chat_list(token))

    async def fetch_chat_list(self, token):
        bot = Bot(token=token)
        try:
            updates = await bot.get_updates(timeout=10)
            chats = {}
            for update in updates:
                if update.message:
                    chat_id = update.message.chat.id
                    chat_title = update.message.chat.title or f"Личный чат {chat_id}"
                    chats[chat_id] = chat_title

            self.chat_listbox.delete(0, tk.END)
            for chat_id, title in chats.items():
                self.chat_listbox.insert(tk.END, f"{chat_id} - {title}")

            if not chats:
                messagebox.showinfo("Информация", "Бот не был активен ни в одном чате.\n"
                                    "Если бот уже работает в чате, отправьте новое сообщение и попробуйте снова.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при получении списка чатов: {e}")

    def check_admin_rights(self):
        """Асинхронно проверяет, является ли бот администратором в выбранном чате."""
        selection = self.chat_listbox.curselection()
        if not selection:
            messagebox.showerror("Ошибка", "Выберите чат из списка!")
            return
        token = self.token_var.get()
        chat_str = self.chat_listbox.get(selection[0])
        chat_id = chat_str.split(" - ")[0].strip()  # Убираем лишние пробелы
        asyncio.run(self.fetch_admin_rights(token, chat_id))

    async def fetch_admin_rights(self, token, chat_id):
        try:
            chat_id = int(chat_id)  # Преобразуем chat_id в число
            bot = Bot(token=token)
            await bot.initialize()  # Явно инициализируем бота перед запросом

            admins = await bot.get_chat_administrators(chat_id)
            for admin in admins:
                if admin.user.id == bot.id:
                    messagebox.showinfo("Результат", f"✅ Бот является администратором в чате {chat_id}.")
                    return

            messagebox.showwarning("Результат", f"⚠️ Бот НЕ является администратором в чате {chat_id}.")
        except ValueError:
            messagebox.showerror("Ошибка", "❌ Ошибка: Chat ID должен быть числом.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при проверке прав: {e}")
            print(e)

    def save_bot_settings(self):
        selection = self.chat_listbox.curselection()
        if not selection:
            messagebox.showerror("Ошибка", "Выберите чат перед сохранением!")
            return
        token = self.token_var.get()
        chat_str = self.chat_listbox.get(selection[0])
        try:
            chat_id = int(chat_str.split(" - ")[0].strip())
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат Chat ID!")
            return
        update_bot_settings(token, chat_id)
        messagebox.showinfo("Успех", "Настройки бота сохранены!")

    def toggle_bot(self):
        global BOT_PROCESS, BOT_STATUS
        if BOT_STATUS:
            if BOT_PROCESS is not None:
                print("🛑 Остановка текущего процесса бота...")
                BOT_PROCESS.terminate()
                BOT_PROCESS.join(timeout=5)
                BOT_PROCESS = None
            BOT_STATUS = False
            self.status_label.config(text="🔴 Бот выключен", foreground="red")
            self.toggle_button.config(text="Включить бота")
            print("✅ Бот успешно остановлен.")
        else:
            token = self.token_var.get()
            if token in ("0", 0, "", "Введите токен"):
                messagebox.showerror("Ошибка", "Введите корректный токен!")
                return

            if BOT_PROCESS is not None:
                print("🛑 Остановка старого процесса перед запуском нового...")
                BOT_PROCESS.terminate()
                BOT_PROCESS.join(timeout=5)
                BOT_PROCESS = None

            print("🚀 Запуск бота...")
            # Запускаем run_bot напрямую:
            BOT_PROCESS = multiprocessing.Process(target=run_bot, args=(token,))
            BOT_PROCESS.start()

            BOT_STATUS = True
            self.status_label.config(text="🟢 Бот работает", foreground="green")
            self.toggle_button.config(text="Выключить бота")
            print("✅ Бот успешно запущен.")


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
            emoji VARCHAR(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT '✅',
            selection_mode VARCHAR(20) NOT NULL DEFAULT 'рандом'
        ) CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()
    cursor.close()
    conn.close()





# ================= ФУНКЦИИ ТЕЛЕГРАМ-БОТА =================

def get_active_task():
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().time()
    query = """
        SELECT id, category, subcategory, start_time, end_time, emoji, selection_mode
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
        print("⚠️ Бот выключен, сообщения не обрабатываются.")
        return

    if (time.time() - start_time_bot) < 3:
        print("🕒 Бот только что запустился, игнорируем сообщение.")
        return

    chat_id = update.message.chat.id
    user_name = update.message.from_user.first_name

    if update.message.from_user.is_bot:
        print(f"🤖 Игнорируем сообщение от бота {user_name}.")
        return

    # Отслеживание сообщений
    if chat_id not in message_count:
        message_count[chat_id] = 0
    message_count[chat_id] += 1

    print(f"📩 {user_name} написал в чате {chat_id}. Количество сообщений: {message_count[chat_id]}")

    # Если в чате набралось 3 сообщения
    if message_count[chat_id] == 3:
        print("🚀 Достигнут лимит сообщений, отправляем товар!")

        task = get_active_task()
        print(f"🔍 Активная задача: {task}")

        if not task:
            await context.bot.send_message(chat_id=chat_id, text="Нет активной задачи.")
            return

        # Проверяем наличие ключа selection_mode
        if 'selection_mode' not in task:
            print("❌ Нет поля 'selection_mode' в задаче.")
            await context.bot.send_message(chat_id=chat_id, text="Задача не имеет выбранного режима.")
            return

        # Выбираем товар в зависимости от режима
        if task['selection_mode'] == "по порядку":
            product = get_product_for_task_order(task)
        else:
            product = get_product_for_task_random(task)

        print(f"📦 Найден товар: {product}")

        if not product:
            await context.bot.send_message(chat_id=chat_id, text="Нет товара для активной задачи.")
            return

        # Формируем сообщение
        data1 = product.get('title', '')
        data2 = product.get('description', '')
        data3 = product.get('image_url', '')
        data4 = product.get('link', '')
        emoji = task.get('emoji', '✅')

        message_parts = [data1, data2, data4]
        message_text = "\n\n".join(filter(None, message_parts))  # Убираем пустые строки

        image_url = data3 if data3 and data3 != 'Изображение отсутствует' else None

        # Отправка сообщения
        try:
            await send_product_message(chat_id, context, message_text, image_url, emoji)
            print("✅ Сообщение с товаром отправлено!")
        except Exception as e:
            print(f"❌ Ошибка при отправке сообщения: {e}")

        message_count[chat_id] = 0


def get_product_for_task_order(task):
    category_id, subcategory_id = get_category_and_subcategory_ids(task['category'], task['subcategory'])

    conn = get_db_connection()
    cursor = conn.cursor()

    # Запрос без фильтрации по subcategory_id, если subcategory_id == None
    if subcategory_id is None:
        cursor.execute("SELECT * FROM parsed_data WHERE category_id = %s", (category_id,))
    else:
        cursor.execute("SELECT * FROM parsed_data WHERE category_id = %s AND subcategory_id = %s",
                       (category_id, subcategory_id))

    products = cursor.fetchall()

    if not products:
        conn.close()
        return None

    order_indexes = [p['order_index'] for p in products]
    if len(set(order_indexes)) == 1:
        chosen_product = min(products, key=lambda p: p['id'])
    else:
        chosen_product = min(products, key=lambda p: p['order_index'])

    new_order = chosen_product['order_index'] + 1

    cursor.execute("UPDATE parsed_data SET order_index = %s WHERE id = %s",
                   (new_order, chosen_product['id']))
    conn.commit()
    conn.close()

    return chosen_product



def get_category_and_subcategory_ids(category_name, subcategory_name):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем category_id по имени категории
    cursor.execute("SELECT id FROM categories WHERE name = %s", (category_name,))
    category = cursor.fetchone()
    if not category:
        conn.close()
        raise ValueError(f"Категория {category_name} не найдена.")

    if subcategory_name is None:
        return category['id'], None  # Если выбраны все подкатегории, передаём None вместо ID

    # Получаем subcategory_id по имени подкатегории
    cursor.execute("""
        SELECT id FROM subcategories WHERE name = %s AND category_id = %s
    """, (subcategory_name, category['id']))
    subcategory = cursor.fetchone()
    conn.close()

    if not subcategory:
        raise ValueError(f"Подкатегория {subcategory_name} не найдена для категории {category_name}.")

    return category['id'], subcategory['id']


async def toggle_bot(update: Update, context: CallbackContext):
    global is_bot_active, message_count
    is_bot_active = not is_bot_active
    status = "включен" if is_bot_active else "выключен"
    await update.message.reply_text(f"Бот теперь {status}.")
    message_count.clear()


def get_product_for_task_random(task):
    category_id, subcategory_id = get_category_and_subcategory_ids(task['category'], task['subcategory'])

    conn = get_db_connection()
    cursor = conn.cursor()

    if subcategory_id is None:
        cursor.execute("SELECT * FROM parsed_data WHERE category_id = %s ORDER BY status ASC, RAND() LIMIT 1",
                       (category_id,))
    else:
        cursor.execute("SELECT * FROM parsed_data WHERE category_id = %s AND subcategory_id = %s ORDER BY status ASC, RAND() LIMIT 1",
                       (category_id, subcategory_id))

    product = cursor.fetchone()

    if product:
        new_status = product['status'] + 1
        cursor.execute("UPDATE parsed_data SET status = %s WHERE id = %s",
                       (new_status, product['id']))
        conn.commit()

    conn.close()
    return product



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
    await app.run_polling()

def run_bot(token):
    global TOKEN
    TOKEN = token  # Обновляем глобальный токен
    if token in ("0", 0, "", "Введите токен"):
        print("❌ Невалидный токен. Бот не запускается.")
        return
    try:
        asyncio.run(bot_main())
    except Exception as e:
        print(f"⚠️ Ошибка в работе телеграм-бота: {e}")





def start_telegram_bot_process(token):
    global BOT_PROCESS
    BOT_PROCESS = multiprocessing.Process(target=run_bot, args=(token,), daemon=True)
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

        # Выбор категории
        ttk.Label(frame, text="Категория:").grid(row=0, column=0, sticky="w")
        self.category_var = tk.StringVar()
        self.category_cb = ttk.Combobox(frame, textvariable=self.category_var, state="readonly")
        self.category_cb.grid(row=0, column=1, sticky="ew", padx=5)
        self.category_cb.bind("<<ComboboxSelected>>", self.refresh_subcategories)

        # Выбор подкатегории
        ttk.Label(frame, text="Подкатегория:").grid(row=1, column=0, sticky="w")
        self.subcategory_var = tk.StringVar()
        self.subcategory_cb = ttk.Combobox(frame, textvariable=self.subcategory_var, state="readonly")
        self.subcategory_cb.grid(row=1, column=1, sticky="ew", padx=5)

        # Выбор режима: рандом или по порядку
        ttk.Label(frame, text="Режим выбора:").grid(row=2, column=0, sticky="w")
        self.mode_var = tk.StringVar(value="рандом")
        self.mode_cb = ttk.Combobox(frame, textvariable=self.mode_var, state="readonly")
        self.mode_cb['values'] = ["рандом", "по порядку"]
        self.mode_cb.grid(row=2, column=1, sticky="ew", padx=5)

        # Выбор эмодзи
        ttk.Label(frame, text="Эмодзи:").grid(row=3, column=0, sticky="w")
        self.emoji_var = tk.StringVar(value="✅")
        self.emoji_cb = ttk.Combobox(frame, textvariable=self.emoji_var, state="readonly")
        self.emoji_cb['values'] = ["✅", "🔥", "🌟", "🍕", "🎁", "💥", "💎", "⚡", "📦", "📣", "Пользовательский ввод..."]
        self.emoji_cb.grid(row=3, column=1, sticky="ew", padx=5)
        self.emoji_cb.bind("<<ComboboxSelected>>", self.emoji_selection)

        self.custom_emoji_var = tk.StringVar()
        self.custom_emoji_entry = ttk.Entry(frame, textvariable=self.custom_emoji_var)
        self.custom_emoji_entry.grid(row=4, column=1, sticky="ew", padx=5)
        self.custom_emoji_entry.grid_remove()

        # Время начала
        ttk.Label(frame, text="Время начала (ЧЧ:ММ):").grid(row=5, column=0, sticky="w")
        self.start_time_var = tk.StringVar(value="08:00")
        ttk.Entry(frame, textvariable=self.start_time_var, width=10).grid(row=5, column=1, sticky="w", padx=5)

        # Время окончания
        ttk.Label(frame, text="Время окончания (ЧЧ:ММ):").grid(row=6, column=0, sticky="w")
        self.end_time_var = tk.StringVar(value="12:00")
        ttk.Entry(frame, textvariable=self.end_time_var, width=10).grid(row=6, column=1, sticky="w", padx=5)

        # Кнопка добавления задачи
        ttk.Button(self, text="Добавить задачу", command=self.add_task).pack(pady=5)

        # Фрейм для списка задач с прокруткой
        ttk.Label(self, text="Список задач:").pack(anchor="w", padx=10, pady=(10, 0))
        frame_tasks_list = ttk.Frame(self)
        frame_tasks_list.pack(fill="both", expand=True, padx=10, pady=5)

        # Создаём Listbox для задач
        self.tasks_listbox = tk.Listbox(frame_tasks_list, height=8)
        self.tasks_listbox.pack(side="left", fill="both", expand=True)

        # Вертикальный скроллбар для списка задач
        tasks_scrollbar = ttk.Scrollbar(frame_tasks_list, orient="vertical", command=self.tasks_listbox.yview)
        tasks_scrollbar.pack(side="right", fill="y")
        self.tasks_listbox.config(yscrollcommand=tasks_scrollbar.set)

        # Кнопка удаления выбранной задачи
        ttk.Button(self, text="Удалить выбранную задачу", command=self.delete_task).pack(pady=5)

    def refresh_categories(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories")
        categories = [row['name'] for row in cursor.fetchall()]
        conn.close()
        self.category_cb['values'] = categories
        if categories:
            # Устанавливаем первое значение из нового списка
            self.category_var.set(categories[0])
            self.refresh_subcategories()
        else:
            self.category_var.set('')
            self.subcategory_cb['values'] = []
            self.subcategory_var.set('')

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

    def emoji_selection(self, event):
        if self.emoji_var.get() == "Пользовательский ввод...":
            self.custom_emoji_entry.grid()
        else:
            self.custom_emoji_entry.grid_remove()

    def add_task(self):
        category = self.category_var.get()
        subcategory = self.subcategory_var.get()
        selection_mode = self.mode_var.get()
        emoji_choice = self.emoji_var.get()
        start_time = self.start_time_var.get()
        end_time = self.end_time_var.get()

        if emoji_choice == "Пользовательский ввод...":
            emoji_input = self.custom_emoji_var.get().strip()
            # Преобразуем введённое значение в эмодзи, используя алиасы.
            converted = emoji.emojize(emoji_input, language='alias')
            # Если результат не изменился, значит, алиас некорректен.
            if converted == emoji_input:
                messagebox.showerror("Ошибка", "Введено некорректное эмодзи.")
                return
            emoji_final = converted
        else:
            emoji_final = emoji_choice
        print(f"selection_mode: {selection_mode}")  # Выводим значение для отладки

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
            INSERT INTO bot_tasks (category, subcategory, start_time, end_time, emoji, selection_mode)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (category, subcategory, start_time, end_time, emoji_final, selection_mode))
        conn.commit()
        conn.close()
        messagebox.showinfo("Успех", "Задача добавлена.")
        self.refresh_tasks()

    def refresh_tasks(self):
        """Обновляет список задач, загружая актуальные данные из базы."""
        self.tasks_listbox.delete(0, tk.END)  # Очищаем список перед обновлением

        conn = get_db_connection()
        cursor = conn.cursor()

        # Загружаем актуальные задачи из базы
        cursor.execute(
            "SELECT id, category, subcategory, start_time, end_time, emoji, selection_mode FROM bot_tasks ORDER BY id ASC")
        tasks = cursor.fetchall()

        valid_tasks = []
        for row in tasks:
            # Проверяем, существует ли подкатегория (если она указана)
            if row['subcategory']:
                cursor.execute("SELECT COUNT(*) as cnt FROM subcategories WHERE name = %s", (row['subcategory'],))
                res = cursor.fetchone()
                if res['cnt'] == 0:
                    continue  # Пропускаем, если подкатегория была удалена
            valid_tasks.append(row)

        conn.close()

        # Добавляем задачи в список
        for row in valid_tasks:
            subcat_display = row['subcategory'] if row['subcategory'] else "Все подкатегории"
            task_str = (f"{row['id']}: {row['emoji']} {row['category']} - {subcat_display} "
                        f"({row['start_time']} - {row['end_time']}) режим: {row.get('selection_mode', 'рандом')}")
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












def save_parsed_data_worker(cat_name, subcat_name, parsed_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM categories WHERE name = %s", (cat_name,))
        cat_row = cursor.fetchone()
        if not cat_row:
            print(f"❌ Ошибка: Категория '{cat_name}' не найдена.")
            return f"Категория '{cat_name}' не найдена."
        cat_id = cat_row['id']

        cursor.execute("SELECT id FROM subcategories WHERE name = %s AND category_id = %s", (subcat_name, cat_id))
        subcat_row = cursor.fetchone()
        if not subcat_row:
            print(f"❌ Ошибка: Подкатегория '{subcat_name}' не найдена.")
            return f"Подкатегория '{subcat_name}' не найдена."
        subcat_id = subcat_row['id']

        # Проверяем, есть ли данные
        if not parsed_data:
            print("❌ Ошибка: Пустые данные, ничего не сохраняем.")
            return "Нет данных для сохранения."

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
                status INT DEFAULT 0,
                order_index INT DEFAULT 0
            )
        """)

        insert_sql = """
            INSERT INTO parsed_data 
            (category_id, subcategory_id, title, description, image_url, link, sub_description, `current_date`, status, order_index)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        inserted_count = 0
        for row in parsed_data:
            cursor.execute(insert_sql, (
                cat_id,
                subcat_id,
                row.get('data1', ''),
                row.get('data2', ''),
                row.get('data3', ''),
                row.get('data4', ''),
                row.get('sub_description', ''),
                row.get('current_date', datetime.datetime.now()),
                0,
                0
            ))
            inserted_count += 1

        conn.commit()  # ✅ Добавил коммит, чтобы сохранить изменения
        print(f"✅ Успешно сохранено {inserted_count} записей.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка при вставке данных в базу: {e}")
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
    def __init__(self, master, modules_tab, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.modules_tab = modules_tab  # Ссылка на ModulesTab
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

        # Фрейм для списка категорий с прокруткой
        frame_cat_list = ttk.Frame(self)
        frame_cat_list.pack(fill="both", expand=True, pady=5)

        # Создаём Listbox для категорий
        self.cat_listbox = tk.Listbox(frame_cat_list, height=8)
        self.cat_listbox.pack(side="left", fill="both", expand=True)
        self.cat_listbox.bind("<<ListboxSelect>>", self.on_category_select)

        # Вертикальный скроллбар для категорий
        cat_scrollbar = ttk.Scrollbar(frame_cat_list, orient="vertical", command=self.cat_listbox.yview)
        cat_scrollbar.pack(side="right", fill="y")
        self.cat_listbox.config(yscrollcommand=cat_scrollbar.set)

        # Кнопка удаления категории
        ttk.Button(self, text="Удалить выбранную категорию", command=self.delete_category).pack(pady=2)

        frame_add_subcat = ttk.Frame(self)
        frame_add_subcat.pack(fill='x', pady=5)
        self.subcat_var = tk.StringVar()
        ttk.Label(frame_add_subcat, text="Название подкатегории:").pack(side='left')
        ttk.Entry(frame_add_subcat, textvariable=self.subcat_var).pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(frame_add_subcat, text="Добавить подкатегорию", command=self.add_subcategory).pack(side='left')

        # Фрейм для списка подкатегорий с прокруткой
        frame_subcat_list = ttk.Frame(self)
        frame_subcat_list.pack(fill="both", expand=True, pady=5)

        # Создаём Listbox для подкатегорий
        self.subcat_listbox = tk.Listbox(frame_subcat_list, height=5)
        self.subcat_listbox.pack(side="left", fill="both", expand=True)

        # Вертикальный скроллбар для подкатегорий
        subcat_scrollbar = ttk.Scrollbar(frame_subcat_list, orient="vertical", command=self.subcat_listbox.yview)
        subcat_scrollbar.pack(side="right", fill="y")
        self.subcat_listbox.config(yscrollcommand=subcat_scrollbar.set)

        # Кнопка удаления подкатегории
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
        """Удаление категории с проверкой активного модуля"""
        if self.modules_tab.current_process is not None and self.modules_tab.current_process.is_alive():
            messagebox.showerror("Ошибка", "Нельзя удалить категорию, пока работает модуль!")
            return

        selection = self.cat_listbox.curselection()
        if not selection:
            messagebox.showerror("Ошибка", "Выберите категорию для удаления.")
            return

        category_name = self.cat_listbox.get(selection[0])

        confirm = messagebox.askyesno("Подтверждение", f"Вы уверены, что хотите удалить категорию '{category_name}'?")
        if not confirm:
            return

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM categories WHERE name = %s", (category_name,))
        category = cursor.fetchone()
        if not category:
            messagebox.showerror("Ошибка", "Категория не найдена.")
            conn.close()
            return

        category_id = category['id']

        cursor.execute("DELETE FROM modules WHERE category_id = %s", (category_id,))
        cursor.execute("DELETE FROM subcategories WHERE category_id = %s", (category_id,))
        cursor.execute("DELETE FROM categories WHERE id = %s", (category_id,))

        conn.commit()
        conn.close()

        self.refresh_categories()
        messagebox.showinfo("Удаление", f"Категория '{category_name}' удалена.")

    def on_category_select(self, event):
        selection = self.cat_listbox.curselection()
        if selection:
            index = selection[0]
            category_name = self.cat_listbox.get(index)
            self.selected_category = category_name
            self.refresh_subcategories()

    def delete_subcategory(self):
        """Удаление подкатегории с проверкой активного модуля"""
        if self.modules_tab.current_process is not None and self.modules_tab.current_process.is_alive():
            messagebox.showerror("Ошибка", "Нельзя удалить подкатегорию, пока работает модуль!")
            return

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
        cursor.execute("DELETE FROM subcategories WHERE id = %s", (subcat_id,))

        conn.commit()
        conn.close()

        self.refresh_subcategories()
        messagebox.showinfo("Удаление", f"Подкатегория '{sub_name}' удалена.")


def run_module_worker(q, file_path, cat_name, subcat_name, use_subprocess=True):
    output_capture = io.StringIO()
    with contextlib.redirect_stdout(output_capture):
        try:
            if use_subprocess:
                result = subprocess.run(
                    [sys.executable, file_path],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
                output_capture.write(result.stdout)
                print('Проверка')
            else:
                spec = importlib.util.spec_from_file_location("dynamic_module", file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # 🔍 Проверяем, есть ли данные
                parsed_data = None
                if hasattr(module, "parsing"):
                    parsed_data = module.parsing()
                elif hasattr(module, "data"):
                    parsed_data = module.data

                if parsed_data is None:
                    print("❌ Ошибка: не найдены 'data' или 'parsing()' в модуле.")
                else:
                    print(f"✅ Данные успешно получены: {len(parsed_data)} записей")
                    result = save_parsed_data_worker(cat_name, subcat_name, parsed_data)
                    print(f"📥 Результат сохранения: {result}")
        except Exception as e:
            print(f"❌ Ошибка при запуске модуля: {e}")

    q.put(output_capture.getvalue())

class ModulesTab(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.current_process = None
        self.active_module_name = None  # Имя текущего запущенного модуля
        self.scheduled_tasks = {}       # Храним планировщики
        self.create_widgets()
        self.refresh_category_dropdown()
        self.refresh_modules_list()
        self.schedule_all_modules()     # Автопланирование при запуске

    def dynamic_import(self, module_name):
        try:
            return importlib.import_module(module_name)
        except ImportError as e:
            messagebox.showerror("Ошибка", f"Модуль {module_name} не найден. Ошибка: {e}")
            return None

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
        self.category_dropdown = ttk.Combobox(frame_add_module, textvariable=self.selected_category_var, state="readonly")
        self.category_dropdown.grid(row=2, column=1, sticky="ew", padx=5)
        self.category_dropdown.bind("<<ComboboxSelected>>", self.update_subcategory_dropdown)

        ttk.Label(frame_add_module, text="Подкатегория:").grid(row=3, column=0, sticky="w")
        self.selected_subcategory_var = tk.StringVar()
        self.subcategory_dropdown = ttk.Combobox(frame_add_module, textvariable=self.selected_subcategory_var, state="readonly")
        self.subcategory_dropdown.grid(row=3, column=1, sticky="ew", padx=5)

        ttk.Label(frame_add_module, text="Время запуска (ЧЧ:ММ, опционально):").grid(row=4, column=0, sticky="w")
        self.start_time_var = tk.StringVar()
        ttk.Entry(frame_add_module, textvariable=self.start_time_var).grid(row=4, column=1, sticky="ew", padx=5)

        frame_add_module.columnconfigure(1, weight=1)
        ttk.Button(frame_add_module, text="Добавить модуль", command=self.add_module).grid(row=5, column=0, columnspan=3, pady=5)

        ttk.Label(self, text="Подключённые модули:").pack(anchor="w", padx=5)
        frame_modules_list = ttk.Frame(self)
        frame_modules_list.pack(fill="both", expand=True, padx=5, pady=5)

        self.modules_listbox = tk.Listbox(frame_modules_list, height=8)
        self.modules_listbox.pack(side="left", fill="both", expand=True)
        self.modules_listbox.bind("<<ListboxSelect>>", self.on_module_select)

        modules_scrollbar = ttk.Scrollbar(frame_modules_list, orient="vertical", command=self.modules_listbox.yview)
        modules_scrollbar.pack(side="right", fill="y")
        self.modules_listbox.config(yscrollcommand=modules_scrollbar.set)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill='x', pady=5)
        ttk.Button(button_frame, text="Удалить модуль", command=self.delete_selected_module).pack(side="left", padx=5)
        self.run_button = ttk.Button(button_frame, text="Запустить модуль", command=self.run_selected_module)
        self.run_button.pack(side="left", padx=5)
        self.stop_button = ttk.Button(button_frame, text="Остановить модуль", command=self.stop_selected_module)
        self.stop_button.pack(side="left", padx=5)

        console_frame = ttk.Frame(self)
        console_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.output_text = tk.Text(console_frame, height=10, state='disabled', bg="black", fg="lime", wrap="word")
        self.output_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(console_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_text.config(yscrollcommand=scrollbar.set)

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
                # Если модуль запущен, кнопка "Остановить" доступна только для него
                if self.current_process is not None:
                    if module['module_name'] == self.active_module_name:
                        self.run_button.config(state="disabled")
                        self.stop_button.config(state="normal")
                    else:
                        self.run_button.config(state="disabled")
                        self.stop_button.config(state="disabled")
                else:
                    self.run_button.config(state="normal")
                    self.stop_button.config(state="disabled")

    def add_module(self):
        module_name = self.module_name_var.get().strip()
        module_path = self.module_path_var.get().strip()
        category_name = self.selected_category_var.get().strip()
        subcategory_name = self.selected_subcategory_var.get().strip()
        start_time = self.start_time_var.get().strip() or None

        if not module_name or not module_path or not category_name or not subcategory_name:
            messagebox.showerror("Ошибка", "Все поля должны быть заполнены.")
            return

        if start_time:
            try:
                datetime.datetime.strptime(start_time, "%H:%M")
            except ValueError:
                messagebox.showerror("Ошибка", "Формат времени: ЧЧ:ММ")
                return

        conn = self.get_db_connection()
        cursor = conn.cursor()

        # Проверяем, существует ли уже модуль с таким названием
        cursor.execute("SELECT COUNT(*) FROM modules WHERE name = %s", (module_name,))
        existing_module = cursor.fetchone()
        if existing_module and existing_module["COUNT(*)"] > 0:
            messagebox.showerror("Ошибка", f"Модуль с названием '{module_name}' уже существует.")
            conn.close()
            return

        # Получаем category_id и subcategory_id
        cursor.execute("SELECT id FROM categories WHERE name=%s", (category_name,))
        category_row = cursor.fetchone()
        if not category_row:
            messagebox.showerror("Ошибка", f"Категория '{category_name}' не найдена.")
            conn.close()
            return
        category_id = category_row['id']

        cursor.execute("SELECT id FROM subcategories WHERE name=%s AND category_id=%s", (subcategory_name, category_id))
        subcategory_row = cursor.fetchone()
        if not subcategory_row:
            messagebox.showerror("Ошибка", f"Подкатегория '{subcategory_name}' не найдена.")
            conn.close()
            return
        subcategory_id = subcategory_row['id']

        # Добавляем новый модуль
        cursor.execute("""
            INSERT INTO modules (name, file_path, category_id, subcategory_id, start_time) 
            VALUES (%s, %s, %s, %s, %s)
        """, (module_name, module_path, category_id, subcategory_id, start_time))
        conn.commit()
        conn.close()

        self.refresh_modules_list()
        self.schedule_module(module_name, start_time)
        messagebox.showinfo("Успех", "Модуль успешно добавлен.")
        self.refresh_modules_list()
        self.refresh_category_dropdown()

    def run_module_by_name(self, module_name):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        query = """
            SELECT m.name as module_name, m.file_path, c.name as category, s.name as subcategory, m.start_time 
            FROM modules m
            JOIN categories c ON m.category_id = c.id
            JOIN subcategories s ON m.subcategory_id = s.id
            WHERE m.name = %s
        """
        cursor.execute(query, (module_name,))
        module = cursor.fetchone()
        conn.close()

        if module:
            self.start_process(module['file_path'], module['category'], module['subcategory'], module['module_name'])
            if module.get('start_time'):
                self.schedule_module(module_name, module['start_time'])

    def schedule_module(self, module_name, start_time):
        if not start_time:
            return

        if self.current_process is not None and self.current_process.is_alive():
            print(
                f"Запланированный модуль '{module_name}' не будет запущен, так как уже выполняется '{self.active_module_name}'")
            return  # Блокируем запуск модуля по расписанию

        now = datetime.datetime.now()

        # Обработка возможных типов start_time
        if isinstance(start_time, str):
            run_time = datetime.datetime.strptime(start_time, "%H:%M").time()
        elif isinstance(start_time, datetime.time):
            run_time = start_time
        elif isinstance(start_time, datetime.timedelta):
            run_time = (now + start_time).time()
        else:
            print(f"Ошибка: неподдерживаемый тип start_time ({type(start_time)}) для модуля {module_name}")
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
        cursor.execute("SELECT id, name FROM modules ORDER BY id")
        modules = cursor.fetchall()
        conn.close()

        if index < len(modules):
            module_id = modules[index]['id']
            module_name = modules[index]['name']

            if self.active_module_name == module_name:
                if self.current_process is not None and self.current_process.is_alive():
                    self.current_process.terminate()
                    self.current_process.join(timeout=2)
                    self.current_process = None
                    self.active_module_name = None
                    self.refresh_modules_list()
                    self.run_button.config(state="normal")
                    self.stop_button.config(state="disabled")

            confirm = messagebox.askyesno("Подтверждение", "Вы уверены, что хотите удалить выбранный модуль?")
            if confirm:
                conn = self.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM modules WHERE id = %s", (module_id,))
                conn.commit()
                conn.close()
                messagebox.showinfo("Успех", "Модуль успешно удалён.")
                self.refresh_modules_list()

    def run_selected_module(self):
        if self.current_process is not None and self.current_process.is_alive():
            messagebox.showerror("Ошибка",
                                 f"Модуль '{self.active_module_name}' уже запущен. Остановите его перед запуском другого.")
            return

        selection = self.modules_listbox.curselection()
        if not selection:
            messagebox.showerror("Ошибка", "Сначала выберите модуль.")
            return

        index = selection[0]
        conn = self.get_db_connection()
        cursor = conn.cursor()
        query = """
           SELECT m.name as module_name, m.file_path, c.name as category, s.name as subcategory
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
            self.start_process(module_record['file_path'], module_record['category'], module_record['subcategory'],
                               module_record['module_name'])

    def start_process(self, file_path, cat_name, subcat_name, module_name, use_subprocess=False):
        if self.current_process is not None and self.current_process.is_alive():
            print(f"Не удалось запустить '{module_name}', так как уже выполняется '{self.active_module_name}'")
            return

        q = multiprocessing.Queue()
        self.active_module_name = module_name
        self.current_process = multiprocessing.Process(target=run_module_worker,
                                                       args=(q, file_path, cat_name, subcat_name, use_subprocess))
        self.current_process.start()
        self.refresh_modules_list()

        def check_output():
            if not q.empty():
                output = q.get()
                self.display_output(output)
                self.current_process = None
                self.active_module_name = None
                self.refresh_modules_list()
                self.run_button.config(state="normal")
                self.stop_button.config(state="disabled")
            else:
                if self.current_process is not None and self.current_process.is_alive():
                    self.after(100, check_output)
                else:
                    self.run_button.config(state="normal")
                    self.stop_button.config(state="disabled")
                    self.current_process = None
                    self.active_module_name = None
                    self.refresh_modules_list()

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
            display_text = module['name']
            if self.active_module_name and module['name'] == self.active_module_name:
                display_text += " [Выполняется]"
            if module['start_time']:
                display_text += f" ({module['start_time']})"
            self.modules_listbox.insert(tk.END, display_text)
        conn.close()

    def stop_selected_module(self):
        selection = self.modules_listbox.curselection()
        if not selection:
            messagebox.showerror("Ошибка", "Сначала выберите модуль для остановки.")
            return
        index = selection[0]
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM modules ORDER BY id")
        modules = cursor.fetchall()
        conn.close()
        if index < len(modules):
            selected_module_name = modules[index]['name']
            if self.current_process is None or selected_module_name != self.active_module_name:
                messagebox.showinfo("Информация", "Выбранный модуль не запущен.")
                return
            self.current_process.terminate()
            self.current_process.join(timeout=2)
            if self.current_process.is_alive():
                print("Не удалось завершить процесс принудительно")
            else:
                print("Процесс успешно завершен")
            self.current_process = None
            self.active_module_name = None
            self.refresh_modules_list()
            self.run_button.config(state="normal")
            self.stop_button.config(state="disabled")

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
    def __init__(self, master, on_success_callback=None, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.on_success_callback = on_success_callback
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
        global DB_CONFIG
        if not DB_CONFIG and os.path.exists("db_config.json"):
            with open("db_config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            DB_CONFIG.update(config)  # Обновляем глобальные настройки
        for key, var in self.db_params.items():
            var.set(DB_CONFIG.get(key, ""))

    def save_db_settings(self):
        config = {key: var.get() for key, var in self.db_params.items()}
        try:
            # Пытаемся установить соединение с новыми параметрами
            conn = pymysql.connect(
                host=config["host"],
                user=config["user"],
                password=config["password"],
                db=config["db"],
                charset="utf8mb4",
                connect_timeout=3,  # Таймаут подключения 3 секунды
                cursorclass=pymysql.cursors.DictCursor
            )
            conn.close()
        except Exception as e:
            # Если соединение не удалось, выводим сообщение об ошибке и не сохраняем данные
            messagebox.showerror("Ошибка", f"Параметры подключения неверны:\n{e}")
            return

        # Если соединение успешно – сохраняем настройки в файл и обновляем глобальную переменную
        with open("db_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        global DB_CONFIG
        DB_CONFIG.clear()
        DB_CONFIG.update(config)

        if self.on_success_callback:
            self.on_success_callback()
        messagebox.showinfo("Успех", "Настройки базы данных сохранены и применены!")


class DBAuthWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Авторизация базы данных")
        self.geometry("400x250")
        self.resizable(False, False)
        # Загружаем DB_CONFIG при запуске окна
        global DB_CONFIG
        if not DB_CONFIG:  # Загружаем только если он пуст
            DB_CONFIG = load_db_config()
        self.create_widgets()

    def create_widgets(self):
        frame = ttk.Frame(self)
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        ttk.Label(frame, text="Host:").grid(row=0, column=0, sticky="w", pady=5)
        self.host_var = tk.StringVar(value=DB_CONFIG.get("host", "localhost"))
        host_entry = ttk.Entry(frame, textvariable=self.host_var)
        host_entry.grid(row=0, column=1, pady=5)
        add_context_menu(host_entry)

        ttk.Label(frame, text="User:").grid(row=1, column=0, sticky="w", pady=5)
        self.user_var = tk.StringVar(value=DB_CONFIG.get("user", "Anos"))
        user_entry = ttk.Entry(frame, textvariable=self.user_var)
        user_entry.grid(row=1, column=1, pady=5)
        add_context_menu(user_entry)

        ttk.Label(frame, text="Password:").grid(row=2, column=0, sticky="w", pady=5)
        self.password_var = tk.StringVar(value=DB_CONFIG.get("password", "AnosVoldigod0"))
        password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*")
        password_entry.grid(row=2, column=1, pady=5)
        add_context_menu(password_entry)

        ttk.Label(frame, text="Database:").grid(row=3, column=0, sticky="w", pady=5)
        self.db_var = tk.StringVar(value=DB_CONFIG.get("db", "test"))
        db_entry = ttk.Entry(frame, textvariable=self.db_var)
        db_entry.grid(row=3, column=1, pady=5)
        add_context_menu(db_entry)

        ttk.Button(frame, text="Подключиться", command=self.test_connection).grid(row=4, column=0, columnspan=2, pady=15)

    def test_connection(self):
        config = {
            "host": self.host_var.get().strip(),
            "user": self.user_var.get().strip(),
            "password": self.password_var.get().strip(),
            "db": self.db_var.get().strip()
        }
        try:
            conn = pymysql.connect(
                host=config["host"],
                user=config["user"],
                password=config["password"],
                db=config["db"],
                charset="utf8mb4",
                connect_timeout=3,
                cursorclass=pymysql.cursors.DictCursor
            )
            conn.close()

            create_tables()
            create_tasks_table()

            # Обновляем глобальную переменную DB_CONFIG
            global DB_CONFIG
            DB_CONFIG.clear()  # Очищаем старые значения
            DB_CONFIG.update(config)  # Загружаем новые

            # Сохраняем данные в файл
            with open("db_config.json", "w", encoding="utf-8") as f:
                json.dump(DB_CONFIG, f, ensure_ascii=False, indent=4)

            print("Обновлённый DB_CONFIG:", DB_CONFIG)  # Проверка, что обновился

            messagebox.showinfo("Успех", "Подключение успешно!")
            self.destroy()
            app = App()
            app.mainloop()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подключиться к базе данных:\n{e}")
            print(e)


class ParsedDataTab(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.create_widgets()
        self.load_categories()
        self.load_parsed_data()

    def create_widgets(self):
        # Фрейм для добавления записи
        add_frame = ttk.LabelFrame(self, text="Добавить запись в parsed_data")
        add_frame.pack(fill="x", padx=10, pady=5)

        # Выбор категории
        ttk.Label(add_frame, text="Категория:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.category_var = tk.StringVar()
        self.category_cb = ttk.Combobox(add_frame, textvariable=self.category_var, state="readonly")
        self.category_cb.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.category_cb.bind("<<ComboboxSelected>>", self.load_subcategories)

        # Выбор подкатегории
        ttk.Label(add_frame, text="Подкатегория:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.subcategory_var = tk.StringVar()
        self.subcategory_cb = ttk.Combobox(add_frame, textvariable=self.subcategory_var, state="readonly")
        self.subcategory_cb.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        # Поле для названия
        ttk.Label(add_frame, text="Название:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.title_entry = ttk.Entry(add_frame)
        self.title_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        # Поле для описания (многострочное)
        ttk.Label(add_frame, text="Описание:").grid(row=3, column=0, sticky="nw", padx=5, pady=5)
        self.description_text = tk.Text(add_frame, height=4, wrap="word")
        self.description_text.grid(row=3, column=1, sticky="ew", padx=5, pady=5)

        # Поле для ссылки на картинку
        ttk.Label(add_frame, text="Ссылка на картинку:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.image_url_entry = ttk.Entry(add_frame)
        self.image_url_entry.grid(row=4, column=1, sticky="ew", padx=5, pady=5)

        # Поле для ссылки
        ttk.Label(add_frame, text="Ссылка:").grid(row=5, column=0, sticky="w", padx=5, pady=5)
        self.link_entry = ttk.Entry(add_frame)
        self.link_entry.grid(row=5, column=1, sticky="ew", padx=5, pady=5)

        # Кнопка добавления записи
        self.add_button = ttk.Button(add_frame, text="Добавить запись", command=self.add_record)
        self.add_button.grid(row=6, column=0, columnspan=2, pady=10)
        add_frame.columnconfigure(1, weight=1)

        # Фрейм для отображения записей
        list_frame = ttk.LabelFrame(self, text="Список записей parsed_data")
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Создание таблицы (Treeview)
        columns = ("id", "category", "subcategory", "title", "description", "image_url", "link", "current_date", "status", "order_index")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col)
            if col in ("id", "status", "order_index"):
                self.tree.column(col, width=50, anchor="center")
            elif col in ("category", "subcategory"):
                self.tree.column(col, width=100)
            else:
                self.tree.column(col, width=150)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Вертикальная полоса прокрутки
        v_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=v_scrollbar.set)
        v_scrollbar.grid(row=0, column=1, sticky="ns")

        # Горизонтальная полоса прокрутки (всегда занимает место)
        h_scrollbar = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=h_scrollbar.set)
        h_scrollbar.grid(row=1, column=0, sticky="ew", padx=5)

        # Настройка сетки в list_frame: строка с горизонтальной полосой всегда будет иметь минимальную высоту
        list_frame.rowconfigure(0, weight=1)
        list_frame.rowconfigure(1, minsize=20)
        list_frame.columnconfigure(0, weight=1)

        # Фрейм для кнопок управления записями
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=10, pady=5)
        self.delete_button = ttk.Button(action_frame, text="Удалить выбранную запись", command=self.delete_selected)
        self.delete_button.pack(side="left", padx=5)
        self.delete_all_button = ttk.Button(action_frame, text="Удалить все записи", command=self.delete_all)
        self.delete_all_button.pack(side="left", padx=5)
        self.refresh_button = ttk.Button(action_frame, text="Обновить список", command=self.load_parsed_data)
        self.refresh_button.pack(side="left", padx=5)

    def load_categories(self):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM categories")
            categories = [row["name"] for row in cursor.fetchall()]
            conn.close()
            self.category_cb["values"] = categories
            if categories:
                self.category_var.set(categories[0])
                self.load_subcategories()  # обновляем подкатегории
            else:
                self.category_var.set("")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить категории: {e}")

    def load_subcategories(self, event=None):
        category = self.category_var.get()
        if not category:
            self.subcategory_cb["values"] = []
            self.subcategory_var.set("")
            return
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT s.name FROM subcategories s JOIN categories c ON s.category_id = c.id WHERE c.name=%s", (category,))
            subcategories = [row["name"] for row in cursor.fetchall()]
            conn.close()
            self.subcategory_cb["values"] = subcategories
            if subcategories:
                self.subcategory_var.set(subcategories[0])
            else:
                self.subcategory_var.set("")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить подкатегории: {e}")

    def add_record(self):
        category_name = self.category_var.get()
        subcategory_name = self.subcategory_var.get()
        title = self.title_entry.get().strip()
        description = self.description_text.get("1.0", "end").strip()
        image_url = self.image_url_entry.get().strip()
        link = self.link_entry.get().strip()
        current_date = datetime.datetime.now()
        sub_description = ""
        status = 0
        order_index = 0

        if not category_name:
            messagebox.showerror("Ошибка", "Выберите категорию.")
            return
        if not subcategory_name:
            messagebox.showerror("Ошибка", "Выберите подкатегорию.")
            return

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM categories WHERE name=%s", (category_name,))
            category_row = cursor.fetchone()
            if not category_row:
                messagebox.showerror("Ошибка", "Категория не найдена в базе.")
                conn.close()
                return
            category_id = category_row["id"]

            cursor.execute("SELECT id FROM subcategories WHERE name=%s AND category_id=%s", (subcategory_name, category_id))
            subcategory_row = cursor.fetchone()
            if not subcategory_row:
                messagebox.showerror("Ошибка", "Подкатегория не найдена в базе.")
                conn.close()
                return
            subcategory_id = subcategory_row["id"]

            insert_sql = """
            INSERT INTO parsed_data 
            (category_id, subcategory_id, title, description, image_url, link, sub_description, `current_date`, status, order_index)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (category_id, subcategory_id, title, description, image_url, link, sub_description, current_date, status, order_index))
            conn.commit()
            conn.close()
            messagebox.showinfo("Успех", "Запись добавлена в parsed_data.")
            self.clear_inputs()
            self.load_parsed_data()
        except Exception as e:
            print("Ошибка при добавлении записи:", e)
            messagebox.showerror("Ошибка", f"Ошибка при добавлении записи: {e}")

    def clear_inputs(self):
        self.title_entry.delete(0, tk.END)
        self.description_text.delete("1.0", tk.END)
        self.image_url_entry.delete(0, tk.END)
        self.link_entry.delete(0, tk.END)

    def load_parsed_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
            SELECT pd.id, c.name as category, s.name as subcategory, pd.title, pd.description, pd.image_url, pd.link, pd.current_date, pd.status, pd.order_index
            FROM parsed_data pd
            LEFT JOIN categories c ON pd.category_id = c.id
            LEFT JOIN subcategories s ON pd.subcategory_id = s.id
            ORDER BY pd.id ASC
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            for row in rows:
                self.tree.insert("", tk.END, values=(
                    row["id"],
                    row["category"],
                    row["subcategory"],
                    row["title"],
                    row["description"],
                    row["image_url"],
                    row["link"],
                    row["current_date"],
                    row["status"],
                    row["order_index"]
                ))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при загрузке данных: {e}")

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Ошибка", "Выберите запись для удаления.")
            return
        item = selected[0]
        record = self.tree.item(item, "values")
        record_id = record[0]
        confirm = messagebox.askyesno("Подтверждение", f"Удалить запись с ID {record_id}?")
        if confirm:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM parsed_data WHERE id=%s", (record_id,))
                conn.commit()
                conn.close()
                messagebox.showinfo("Успех", "Запись удалена.")
                self.load_parsed_data()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка при удалении записи: {e}")

    def delete_all(self):
        confirm = messagebox.askyesno("Подтверждение", "Удалить все записи из parsed_data?")
        if confirm:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM parsed_data")
                conn.commit()
                conn.close()
                messagebox.showinfo("Успех", "Все записи удалены.")
                self.load_parsed_data()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка при удалении записей: {e}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Интерфейс парсинга")
        self.geometry("700x700")
        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.modules_tab = ModulesTab(self.notebook)  # Сначала создаём ModulesTab
        self.categories_tab = CategoriesTab(self.notebook, self.modules_tab)  # Передаём modules_tab в CategoriesTab
        self.tasks_tab = TasksTab(self.notebook)
        self.bot_settings_tab = BotSettingsTab(self.notebook)
        self.db_settings_tab = DatabaseSettingsTab(self.notebook, on_success_callback=self.reload_all_tabs)
        self.parsed_data_tab = ParsedDataTab(self.notebook)

        # Добавляем вкладки в интерфейс
        self.notebook.add(self.categories_tab, text="Категории")
        self.notebook.add(self.modules_tab, text="Модули")
        self.notebook.add(self.tasks_tab, text="Задачи")
        self.notebook.add(self.bot_settings_tab, text="Настройки")
        self.notebook.add(self.db_settings_tab, text="База данных")
        self.notebook.add(self.parsed_data_tab, text="Parsed Data")

        self.categories_tab.set_update_callback(lambda: (
            self.parsed_data_tab.load_categories(),
            self.modules_tab.refresh_category_dropdown(),
            self.modules_tab.refresh_modules_list(),
            self.tasks_tab.refresh_categories(),
            self.tasks_tab.refresh_tasks()
        ))

    def reload_all_tabs(self):
        self.categories_tab.refresh_categories()
        self.modules_tab.refresh_category_dropdown()
        self.modules_tab.refresh_modules_list()
        self.tasks_tab.refresh_categories()
        self.tasks_tab.refresh_tasks()
        self.bot_settings_tab.refresh_bot_settings()

    def on_closing(self):
        # Остановка фонового телеграм-бота, если он запущен
        global BOT_PROCESS
        if BOT_PROCESS is not None:
            try:
                BOT_PROCESS.terminate()
                BOT_PROCESS.join(timeout=5)
            except Exception as e:
                print(f"Ошибка при завершении BOT_PROCESS: {e}")
        # Остановка таймеров в ModulesTab
        if hasattr(self, "modules_tab") and hasattr(self.modules_tab, "scheduled_tasks"):
            for timer in self.modules_tab.scheduled_tasks.values():
                timer.cancel()
        self.destroy()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    auth_window = DBAuthWindow()
    auth_window.mainloop()
