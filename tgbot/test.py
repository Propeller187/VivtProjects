import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from datetime import datetime
import pytz
import requests

# Настройка подключения к базе данных (замените параметры на свои)
db_config = {
    'host': 'krutskna.beget.tech',
    'user': 'krutskna_baza',
    'password': 'AnosVoldigod0',
    'database': 'krutskna_baza'
}

# Создаем пул соединений
pool = MySQLConnectionPool(pool_name="mypool", pool_size=5, **db_config)


def get_connection():
    try:
        return pool.get_connection()
    except mysql.connector.Error as err:
        print(f"Ошибка получения соединения: {err}")
        raise


# Предположим, у нас уже есть название рецепта, URL изображения и дата парсинга:
recipe_title = "Салат \"Ёжик\""
description = "Этот сытный салат с колбасой, сыром и кукурузой подойдёт к любому празднику."
sub_description = "Продукты: колбаса копченая, сыр твёрдый, яйца отварные, кукуруза, чеснок, майонез"
image_url = "https://img1.russianfood.com/dycontent/images_upl/281/sm_280021.jpg"
link = "https://www.russianfood.com/recipes/recipe.php?rid=121720"

# Загружаем изображение
response = requests.get(image_url)
if response.status_code == 200:
    image_data = response.content  # бинарные данные изображения
else:
    image_data = None
    print("Ошибка при загрузке изображения")

# Получаем текущую дату в часовом поясе Europe/Moscow
tz = pytz.timezone("Europe/Moscow")
current_date = datetime.now(tz)

# Сохраняем данные в базу данных
try:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        description TEXT NOT NULL,
        sub_description TEXT NOT NULL,
        image LONGBLOB,
        link TEXT NOT NULL,
        date_parsed DATETIME
    )
    ''')
    # Предположим, таблица создана следующим образом:
    #   CREATE TABLE IF NOT EXISTS recipes (
    #    id INT AUTO_INCREMENT PRIMARY KEY,
    #    title VARCHAR(255) NOT NULL,
    #    description TEXT NOT NULL,
    #    sub_description TEXT NOT NULL,
    #    image LONGBLOB,
    #    link TEXT NOT NULL,
    #    date_parsed DATETIME
    # );
    sql = """
    INSERT INTO recipes (title, description, sub_description, image, link, date_parsed)
    VALUES (%s, %s, %s)
    """
    data = (recipe_title, description, sub_description, image_data, link, current_date)
    cursor.execute(sql, data)
    conn.commit()
    print("Данные успешно сохранены в базе данных.")
    cursor.close()
    conn.close()
except mysql.connector.Error as err:
    print(f"Ошибка сохранения данных: {err}")