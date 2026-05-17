# 1. Базовий образ: легкий Linux із готовим Python 3.10
FROM python:3.10-slim

# 2. Налаштування середовища Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Створення робочої папки всередині контейнера
WORKDIR /code

# 4. Спочатку копіюємо requirements і встановлюємо залежності
# (Це робиться окремо, щоб Docker кешував шари і не перевстановлював бібліотеки при кожній зміні коду)
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 5. Копіюємо файл конфігурації лінтера
COPY ./pyproject.toml /code/pyproject.toml

# 6. Копіюємо весь код додатка (папку app)
COPY ./app /code/app

# 7. АВТОМАТИЧНИЙ ЛІНТИНГ: перевірка коду перед деплоєм
# Якщо Ruff знайде помилки — збірка примусово зупиниться
RUN ruff check /code/app

# 8. Відкриваємо порт 8000 для FastAPI
EXPOSE 8000

# 9. Команда для запуску сервера всередині Докера
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]