import hashlib
from forum_db import create_user, get_user_by_username, get_user_by_id

def hash_password(password: str) -> str:
    """SHA-256 хеширование пароля (для простоты)."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hash_val: str) -> bool:
    return hash_password(password) == hash_val

def register_user(username: str, password: str, display_name: str = None, is_expert: bool = False):
    if get_user_by_username(username):
        return None
    user_id = create_user(username, hash_password(password), display_name, is_expert)
    return {"id": user_id, "username": username, "is_expert": is_expert}

def login_user(username: str, password: str):
    user = get_user_by_username(username)
    if user and verify_password(password, user["password_hash"]):
        return {"id": user["id"], "username": user["username"], "display_name": user["display_name"], "is_expert": user["is_expert"]}
    return None

# Для удобства, можно также экспортировать get_user_by_id из forum_db,
# но лучше не дублировать, а импортировать в web_api.py из forum_db напрямую.