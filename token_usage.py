# token_usage.py
import sqlite3
import datetime
import logging
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

def init_db():
    """Инициализация базы данных, создание таблицы, если её нет."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        # noinspection SqlDialectInspection,SqlNoDataSourceInspection
        c.execute('''CREATE TABLE IF NOT EXISTS token_usage
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT,
                      user_id INTEGER,
                      role TEXT,
                      query TEXT,
                      tokens INTEGER,
                      model TEXT)''')
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка инициализации БД токенов: {e}")
    finally:
        if conn:
            conn.close()

def log_usage(user_id, role, query, tokens, model):
    """Сохраняет запись об использовании токенов."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        # noinspection SqlDialectInspection,SqlNoDataSourceInspection
        c.execute(
            "INSERT INTO token_usage (timestamp, user_id, role, query, tokens, model) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.datetime.now().isoformat(), user_id, role, query[:200], tokens, model)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения токенов: {e}")
    finally:
        if conn:
            conn.close()

# Функция-обёртка для совместимости с web_api.py
def log_token_usage(user_id, prompt_tokens, completion_tokens, model="yandexgpt"):
    """Обёртка для log_usage, суммирует токены."""
    total_tokens = prompt_tokens + completion_tokens
    role = "web_user"
    query = "API call"
    log_usage(user_id, role, query, total_tokens, model)