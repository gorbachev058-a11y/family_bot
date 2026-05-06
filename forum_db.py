import sqlite3
import os

DB_PATH = "data/forum.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_forum_db():
    """Создаёт все таблицы: topics, comments, expert_picks, users, likes."""
    os.makedirs("data", exist_ok=True)
    conn = get_db_connection()

    # Таблица тем
    conn.execute('''
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'published'
        )
    ''')

    # Таблица комментариев
    conn.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_expert_answer INTEGER DEFAULT 0,
            FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE
        )
    ''')

    # Таблица экспертных выборок
    conn.execute('''
        CREATE TABLE IF NOT EXISTS expert_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            comment_id INTEGER NOT NULL,
            added_to_kb_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(topic_id) REFERENCES topics(id),
            FOREIGN KEY(comment_id) REFERENCES comments(id)
        )
    ''')

    # Таблица пользователей (для аутентификации)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            is_expert INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица лайков
    conn.execute('''
        CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER NOT NULL,
            comment_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, comment_id),
            FOREIGN KEY(comment_id) REFERENCES comments(id) ON DELETE CASCADE
        )
    ''')

    # Добавляем колонку updated_at, если её нет (миграция для старых БД)
    try:
        conn.execute("ALTER TABLE topics ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE comments ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE comments ADD COLUMN user_id INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# ------------------------------------------------------------
# Пользователи
# ------------------------------------------------------------
def create_user(username: str, password_hash: str, display_name: str = None, is_expert: bool = False) -> int:
    conn = get_db_connection()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, display_name, is_expert) VALUES (?, ?, ?, ?)",
        (username, password_hash, display_name or username, 1 if is_expert else 0)
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def get_user_by_username(username: str):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def is_user_expert(user_id: int) -> bool:
    user = get_user_by_id(user_id)
    return user is not None and user["is_expert"] == 1


# ------------------------------------------------------------
# Темы
# ------------------------------------------------------------
def create_topic(user_id: str, title: str, content: str) -> int:
    conn = get_db_connection()
    cur = conn.execute(
        "INSERT INTO topics (user_id, title, content) VALUES (?, ?, ?)",
        (user_id, title.strip(), content.strip())
    )
    conn.commit()
    topic_id = cur.lastrowid
    conn.close()
    return topic_id


def get_topics_paginated(page: int = 1, per_page: int = 10):
    offset = (page - 1) * per_page
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT id, user_id, title, content, created_at, updated_at, status
        FROM topics
        WHERE status = 'published'
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()
    total = conn.execute("SELECT COUNT(*) as cnt FROM topics WHERE status = 'published'").fetchone()["cnt"]
    conn.close()
    return {
        "topics": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page
    }


def get_topic(topic_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_topic(topic_id: int, title: str, content: str, user_id: int) -> bool:
    conn = get_db_connection()
    topic = conn.execute("SELECT user_id FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return False
    if topic["user_id"] != str(user_id) and not is_user_expert(user_id):
        conn.close()
        return False
    conn.execute(
        "UPDATE topics SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (title.strip(), content.strip(), topic_id)
    )
    conn.commit()
    conn.close()
    return True


def delete_topic(topic_id: int, user_id: int) -> bool:
    conn = get_db_connection()
    topic = conn.execute("SELECT user_id FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return False
    if topic["user_id"] != str(user_id) and not is_user_expert(user_id):
        conn.close()
        return False
    conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()
    return True


# ------------------------------------------------------------
# Комментарии
# ------------------------------------------------------------
def add_comment(topic_id: int, user_id: int, content: str, is_expert: bool = False) -> int:
    conn = get_db_connection()
    cur = conn.execute(
        "INSERT INTO comments (topic_id, user_id, content, is_expert_answer) VALUES (?, ?, ?, ?)",
        (topic_id, user_id, content.strip(), 1 if is_expert else 0)
    )
    conn.commit()
    comment_id = cur.lastrowid
    conn.close()
    return comment_id


def get_comments_with_likes(topic_id: int, current_user_id: int = None):
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT c.*, 
               (SELECT COUNT(*) FROM likes WHERE comment_id = c.id) as like_count
        FROM comments c
        WHERE c.topic_id = ?
        ORDER BY c.created_at ASC
    ''', (topic_id,)).fetchall()

    comments = []
    for row in rows:
        d = dict(row)
        if current_user_id:
            liked = conn.execute(
                "SELECT 1 FROM likes WHERE user_id = ? AND comment_id = ?",
                (current_user_id, d["id"])
            ).fetchone() is not None
            d["liked"] = liked
        else:
            d["liked"] = False
        comments.append(d)
    conn.close()
    return comments


def get_comment_by_id(comment_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_comment(comment_id: int, content: str, user_id: int) -> bool:
    conn = get_db_connection()
    comment = conn.execute("SELECT user_id FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if not comment:
        conn.close()
        return False
    if comment["user_id"] != user_id and not is_user_expert(user_id):
        conn.close()
        return False
    conn.execute(
        "UPDATE comments SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (content.strip(), comment_id)
    )
    conn.commit()
    conn.close()
    return True


def delete_comment(comment_id: int, user_id: int) -> bool:
    conn = get_db_connection()
    comment = conn.execute("SELECT user_id FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if not comment:
        conn.close()
        return False
    if comment["user_id"] != user_id and not is_user_expert(user_id):
        conn.close()
        return False
    conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()
    return True


# ------------------------------------------------------------
# Лайки
# ------------------------------------------------------------
def toggle_like(user_id: int, comment_id: int) -> bool:
    """Возвращает True, если лайк поставлен (после переключения)."""
    conn = get_db_connection()
    existing = conn.execute(
        "SELECT 1 FROM likes WHERE user_id = ? AND comment_id = ?",
        (user_id, comment_id)
    ).fetchone()
    if existing:
        conn.execute("DELETE FROM likes WHERE user_id = ? AND comment_id = ?", (user_id, comment_id))
        liked = False
    else:
        conn.execute("INSERT INTO likes (user_id, comment_id) VALUES (?, ?)", (user_id, comment_id))
        liked = True
    conn.commit()
    conn.close()
    return liked


def get_like_count(comment_id: int) -> int:
    conn = get_db_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM likes WHERE comment_id = ?", (comment_id,)).fetchone()
    conn.close()
    return row["cnt"]


# ------------------------------------------------------------
# Экспертные отметки
# ------------------------------------------------------------
def mark_expert_pick(topic_id: int, comment_id: int):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO expert_picks (topic_id, comment_id) VALUES (?, ?)",
        (topic_id, comment_id)
    )
    conn.commit()
    conn.close()


def is_already_picked(comment_id: int) -> bool:
    conn = get_db_connection()
    row = conn.execute("SELECT 1 FROM expert_picks WHERE comment_id = ?", (comment_id,)).fetchone()
    conn.close()
    return row is not None