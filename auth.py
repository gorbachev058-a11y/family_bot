import sqlite3
import hashlib
import os
from datetime import datetime, timedelta

DB_PATH = "data/users.db"

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password_hash TEXT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        premium_until DATETIME,
        premium_auto_renew BOOLEAN DEFAULT 0
    )''')
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()