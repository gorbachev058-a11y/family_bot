# mood.py
import sqlite3
import os

DB_PATH = "data/mood.db"

def init_mood_db():
    """Создаёт таблицу для записей настроения."""
    os.makedirs("data", exist_ok=True)
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # noinspection SqlDialectInspection,SqlNoDataSourceInspection
        c.execute('''
            CREATE TABLE IF NOT EXISTS moods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                mood INTEGER,
                note TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    except Exception as e:
        print(f"Ошибка инициализации БД настроения: {e}")
    finally:
        if conn:
            conn.close()

def save_mood(user_id: str, mood: int, note: str = ""):
    """Сохраняет запись настроения."""
    init_mood_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # noinspection SqlDialectInspection,SqlNoDataSourceInspection
        c.execute("INSERT INTO moods (user_id, mood, note) VALUES (?, ?, ?)",
                  (user_id, mood, note))
        conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения настроения: {e}")
    finally:
        if conn:
            conn.close()

def get_mood_history(user_id: str, limit: int = 10):
    """Возвращает последние записи настроения пользователя."""
    init_mood_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # noinspection SqlDialectInspection,SqlNoDataSourceInspection
        c.execute('''
            SELECT date, mood, note FROM moods
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT ?
        ''', (user_id, limit))
        rows = c.fetchall()
        return [{"date": row["date"], "mood": row["mood"], "note": row["note"]} for row in rows]
    except Exception as e:
        print(f"Ошибка получения истории настроения: {e}")
        return []
    finally:
        if conn:
            conn.close()