import emoji

# Открываем файл для записи
with open("emoji_list.txt", "w", encoding="utf-8") as file:
    for char, data in emoji.EMOJI_DATA.items():
        if "en" in data:  # Проверяем, есть ли английское название
            line = f"Эмодзи: {char}, Идентификатор: {data['en']}\n"
            print(line.strip())  # Вывод в консоль
            file.write(line)  # Запись в файл
