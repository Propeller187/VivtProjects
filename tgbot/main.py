from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from datetime import datetime
import pytz
import time
import requests
import os
import re


def sanitize_filename(name):
    """
    Удаляет недопустимые символы из имени файла.
    На Windows недопустимы символы: \ / : * ? " < > |
    """
    return re.sub(r'[\\\/:*?"<>|]', '', name)

db_config = {
    'host': 'ilyasiux.beget.tech',
    'user': 'ilyasiux_prop',
    'password': 'Propeller187',
    'database': 'ilyasiux_prop'
}

# Создаем пул соединений
pool = MySQLConnectionPool(pool_name="mypool", pool_size=5, **db_config)


def get_connection():
    try:
        return pool.get_connection()
    except mysql.connector.Error as err:
        print(f"Ошибка получения соединения: {err}")
        raise

conn = get_connection()
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS recipes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sub_category_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    sub_description TEXT NOT NULL,
    image TEXT NOT NULL,
    link TEXT NOT NULL,
    date_parsed DATETIME,
    count INT,
    FOREIGN KEY (sub_category_id) REFERENCES subcategories(id)
)
''')
conn.commit()
cursor.close()
conn.close()

# Настройка для работы с Chrome в headless-режиме
options = webdriver.ChromeOptions()
#options.add_argument('--headless')  # запуск без графического интерфейса
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Получаем текущую дату в часовом поясе Europe/Moscow
tz = pytz.timezone("Europe/Moscow")
current_date = datetime.now(tz)

# URL страницы рецепта
url = "https://www.russianfood.com/recipes/"
driver.get(url)
print('test')
html_content = driver.page_source
soup = BeautifulSoup(html_content, 'lxml')
print('test')

# Задержка для корректной загрузки страницы
time.sleep(10)

# Массив для добавления в базу данных
data = []

# Находим ссылки на категории блюд
dishes_category = soup.find('div', class_='tags_block_all').find('table', class_='rcpf')
category_links = []
for x in dishes_category.find_all('dt'):
    category_links.append(x.find('a', class_='resList')['href'])

category_links = [f'/recipes/bytype/?fid=2']
sub_category_name = 1


for category in category_links:
    print('\n \n Открываем новую категорию \n \n')
    category_url = f"https://www.russianfood.com{category}&page=1#rcp_list"
    print(category_url)
    driver.get(category_url)
    html_content = driver.page_source
    soup = BeautifulSoup(html_content, 'lxml')
    time.sleep(2)

    page = int(category_url[category_url.find('page=') + 5:category_url.find('#')])
    page_confirm = 1

    while page == page_confirm:
        print(f'\n [{datetime.now(tz)}]   Переход на страницу {page}\n')
        dishes = soup.find('div', class_='recipe_list_new recipe_list_new2').find_all('div', class_='in_seen')

        for dish in dishes:
            title = dish.find('div', class_='title').find('h3').text.strip()
            print(title)

            desc = dish.find('div', class_='announce')
            if desc:
                description = dish.find('div', class_='announce').text.strip()
            else:
                description = 'Отсутствует'

            sub = dish.find('div', class_='announce_sub')
            if sub:
                sub_description = dish.find('div', class_='announce_sub').find('span').text.strip()
            else:
                sub_description = 'Отсутствует'

            link = f"https://www.russianfood.com{dish.find('a')['href']}"

            # Ищем тег <img> с атрибутом title, содержащим "Фото к рецепту:"
            image_tag = dish.find('img', class_= 'round shadow')
            if image_tag and image_tag.get('src'):
                image_src = image_tag['src']
                # Если ссылка начинается с //, добавляем протокол https:
                if image_src.startswith("//"):
                    image_url = "https:" + image_src
                else:
                    image_url = image_src
                print("Ссылка на изображение:", image_url)
            else:
                image_url = 'Изображение отсутствует'
                print(image_url)

            data.append((title, description, sub_description, image_url, link, current_date, 0))

        page_confirm += 1
        category_url = f"https://www.russianfood.com{category}&page={page_confirm}#rcp_list"
        driver.get(category_url)
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'lxml')
        current_url = driver.current_url
        print(current_url)
        page = int(current_url[current_url.find('page=') + 5:current_url.find('#')])

try:
    conn = get_connection()
    cursor = conn.cursor()
    sql = """
        INSERT INTO recipes (title, description, sub_description, image, link, date_parsed, count)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
    cursor.executemany(sql, data)
    conn.commit()
    print("Данные успешно сохранены в базе данных.")
    cursor.close()
    conn.close()
except mysql.connector.Error as err:
    print(f"Ошибка сохранения данных: {err}")

driver.quit()