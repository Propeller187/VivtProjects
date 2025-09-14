import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext
from telegram.error import ChatMigrated
import time
import os
import requests
import tempfile
import datetime
import pytz

start_time = time.time()

TOKEN = '7906769555:AAFARmJoyucIAWo5_BcQqLWeG1VtKOscWRI'

db_config = {
    'host': 'krutskna.beget.tech',
    'user': 'krutskna_baza',
    'password': 'AnosVoldigod0',
    'database': 'krutskna_baza'
}

# Создаем пул соединений
pool = MySQLConnectionPool(pool_name="mypool", pool_size=5, **db_config)
print('Подключение к базе успешно')

# Фиксированный chat_id для отправки рецепта по расписанию
SCHEDULED_CHAT_ID = -1002384200352

def get_connection():
    try:
        return pool.get_connection()
    except mysql.connector.Error as err:
        print(f"Ошибка получения соединения: {err}")
        raise


def get_recipe_with_min_count():
    """
    Находит рецепт с минимальным значением count.
    Если таких несколько, выбирается случайный.
    Перед возвратом увеличивается count выбранного рецепта на 1.
    """
    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Находим минимальное значение count
        cursor.execute("SELECT MIN(count) FROM recipes")
        result = cursor.fetchone()
        if result and result[0] is not None:
            min_count = result[0]
        else:
            cursor.close()
            connection.close()
            return None

        # Выбираем один рецепт с минимальным count (если их несколько, выбираем случайный)
        cursor.execute(
            "SELECT id, title, description, image, link FROM recipes WHERE count = %s ORDER BY RAND() LIMIT 1",
            (min_count,)
        )
        recipe = cursor.fetchone()
        if not recipe:
            cursor.close()
            connection.close()
            return None

        recipe_id = recipe[0]
        # Увеличиваем count выбранного рецепта на 1
        cursor.execute("UPDATE recipes SET count = count + 1 WHERE id = %s", (recipe_id,))
        connection.commit()

        cursor.close()
        connection.close()
        return recipe  # (id, title, description, image)

    except mysql.connector.Error as err:
        print(f"Ошибка работы с базой данных: {err}")
        return None


# Словарь для хранения количества сообщений по каждому чату
message_count = {}

# Переменная, которая будет хранить состояние активации бота (по умолчанию включён)
is_bot_active = True

# Глобальная переменная для хранения последнего chat_id, из которого приходили сообщения (используется только для приветствия/3 сообщений)
last_chat_id = None


async def welcome_new_member(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    new_user = update.message.new_chat_members[0].first_name

    welcome_message = f"Привет, {new_user}! Добро пожаловать в наш чат!"

    try:
        await context.bot.send_message(chat_id=chat_id, text=welcome_message)
    except ChatMigrated as e:
        new_chat_id = e.migrate_to_chat_id
        await context.bot.send_message(chat_id=new_chat_id, text=welcome_message)


async def download_and_send_image(image_url, chat_id, context):
    try:
        # Скачиваем изображение
        response = requests.get(image_url)
        response.raise_for_status()  # Проверяем, что запрос успешен

        # Сохраняем изображение во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(response.content)
            temp_file.close()

            # Отправляем картинку (await для асинхронного метода)
            with open(temp_file.name, 'rb') as img_file:
                await context.bot.send_photo(chat_id=chat_id, photo=img_file)

            # Удаляем временный файл
            os.remove(temp_file.name)

    except requests.RequestException as e:
        print(f"Ошибка при скачивании картинки: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Не удалось скачать изображение.")


async def track_messages(update: Update, context: CallbackContext):
    global start_time, is_bot_active, last_chat_id
    if not is_bot_active:
        return  # Если бот не активен, не отслеживаем сообщения

    if (time.time() - start_time) < 3:
        return

    chat_id = update.message.chat.id
    last_chat_id = chat_id  # Сохраняем актуальный chat_id для использования при приветствии

    # Игнорируем сообщения от ботов
    if update.message.from_user.is_bot:
        return

    if chat_id not in message_count:
        message_count[chat_id] = 0
    message_count[chat_id] += 1

    # При достижении 3-х сообщений выбираем рецепт с минимальным count
    if message_count[chat_id] == 3:
        print(f"Chat ID после 3 сообщений: {chat_id}")
        recipe_data = get_recipe_with_min_count()
        if recipe_data:
            recipe_id, recipe_title, recipe_description, image_url, link = recipe_data
            message_text = f"Случайный рецепт:\n{recipe_title}\n\nОписание: {recipe_description}\n Ссылка: {link}"
            await context.bot.send_message(chat_id=chat_id, text=message_text)

            if image_url and image_url != 'Изображение отсутствует':
                await download_and_send_image(image_url, chat_id, context)
            else:
                await context.bot.send_message(chat_id=chat_id, text="Изображение отсутствует.")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Не удалось найти рецепт.")

        # Сброс счетчика для этого чата
        message_count[chat_id] = 0


async def toggle_bot(update: Update, context: CallbackContext):
    global is_bot_active

    if is_bot_active:
        is_bot_active = False
        await update.message.reply_text("Бот теперь не отслеживает сообщения.")
    else:
        is_bot_active = True
        await update.message.reply_text("Бот теперь отслеживает сообщения.")
        message_count.clear()


async def scheduled_recipe(context: CallbackContext):
    """
    Функция для отправки рецепта по расписанию.
    Отправляет рецепт в чат с фиксированным ID SCHEDULED_CHAT_ID.
    """
    recipe_data = get_recipe_with_min_count()
    if recipe_data:
        recipe_id, recipe_title, recipe_description, image_url, link = recipe_data
        message_text = f"Случайный рецепт (по расписанию):\n{recipe_title}\n\nОписание: {recipe_description}\n Ссылка: {link}"
        await context.bot.send_message(chat_id=SCHEDULED_CHAT_ID, text=message_text)

        if image_url and image_url != 'Изображение отсутствует':
            await download_and_send_image(image_url, SCHEDULED_CHAT_ID, context)
        else:
            await context.bot.send_message(chat_id=SCHEDULED_CHAT_ID, text="Изображение отсутствует.")
    else:
        await context.bot.send_message(chat_id=SCHEDULED_CHAT_ID, text="Не удалось найти рецепт.")


def main():
    application = Application.builder().token(TOKEN).build()

    # Обработчик для приветствия новых участников
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

    # Обработчик для отслеживания сообщений
    application.add_handler(MessageHandler(filters.TEXT, track_messages))

    # Обработчик для команды включения/выключения бота
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^/toggle_bot$'), toggle_bot))

    # Настройка планировщика (JobQueue) для отправки рецепта по расписанию.
    # Отправка происходит ежедневно в указанное время (например, 12:57 по МСК).
    moscow_tz = pytz.timezone("Europe/Moscow")
    scheduled_time = datetime.time(hour=13, minute=16, second=0, tzinfo=moscow_tz)
    application.job_queue.run_daily(scheduled_recipe, time=scheduled_time)

    # Запуск бота
    application.run_polling()


if __name__ == '__main__':
    main()