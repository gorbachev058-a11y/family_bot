# auth_telegram.py
import hashlib
import hmac
import os
import jwt
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Загружаем секрет из переменной окружения, если нет — генерируем при старте (но лучше всегда задавать)
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    # Для разработки можно сгенерировать, но в production обязательно задать в .env
    import secrets
    JWT_SECRET = secrets.token_hex(32)
    # ВАЖНО: В production не полагайтесь на автоматическую генерацию, установите фиксированное значение в .env

def verify_telegram_auth(data: dict):
    if not data.get('hash'):
        return None
    received_hash = data.pop('hash')
    items = [f"{k}={v}" for k, v in sorted(data.items())]
    data_check_string = "\n".join(items)
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if computed_hash == received_hash:
        data['hash'] = received_hash
        return data
    return None

def create_jwt(user_id: int, telegram_id: int) -> str:
    payload = {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_jwt(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except:
        return None