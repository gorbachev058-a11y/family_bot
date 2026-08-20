import sqlite3
import os
import logging
import re
from collections import defaultdict
from typing import Optional, List, Dict
from config import ROLE_AVATARS
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime, timedelta

# ЮKassa
from yookassa import Configuration, Payment

# Ваши модули
from auth_db import init_db, hash_password, activate_premium
from auth_telegram import verify_telegram_auth, create_jwt, decode_jwt
from rag import generate_answer, is_refusal
from knowledge_base import KnowledgeBase
from mood import save_mood, get_mood_history
from advice import get_daily_advice
from forum_db import (
    init_forum_db,
    create_topic,
    get_topics_paginated,
    get_topic,
    add_comment,
    get_comments_with_likes,
    get_comment_by_id,
    mark_expert_pick,
    is_already_picked,
    update_topic,
    delete_topic,
    update_comment,
    delete_comment,
    toggle_like,
    get_like_count,
    is_user_expert,
    get_user_by_id
)
from kb_updater import add_chunk_to_kb

# Импортируем функции для тестов (если они есть в test_handlers)
try:
    from test_handlers import (
        test_registry,
        calculate_anxiety,
        calculate_compatibility,
        calculate_parenting_style,
        calculate_self_acceptance,
        calculate_self_esteem,
        calculate_self_esteem as calculate_self_esteem_alias  # если имя другое
    )
    TEST_HANDLERS_AVAILABLE = True
except ImportError:
    TEST_HANDLERS_AVAILABLE = False
    logging.warning("test_handlers.py не найден, тесты будут работать в режиме заглушки")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация ЮKassa из переменных окружения
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "test")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "test")
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# Инициализация приложения
app = FastAPI(title="Доктор Хауз Web API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================
# База знаний
# ========================
KB_PATH = "data/family_advice.txt"
knowledge_base = KnowledgeBase(KB_PATH)

# ========================
# Хранилище истории диалогов и имён
# ========================
conversation_history: Dict[str, List[Dict[str, str]]] = defaultdict(list)
user_names: Dict[str, str] = {}
MAX_HISTORY_LENGTH = 20
proactive_shown: Dict[str, bool] = defaultdict(bool)

# ========================
# SQLite для долгосрочного хранения диалогов
# ========================
def init_dialogues_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/dialogues.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS dialogues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            role TEXT,
            question TEXT,
            answer TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_dialogue(user_id: str, role: str, question: str, answer: str):
    conn = sqlite3.connect("data/dialogues.db")
    c = conn.cursor()
    c.execute("INSERT INTO dialogues (user_id, role, question, answer) VALUES (?, ?, ?, ?)",
              (user_id, role, question, answer))
    conn.commit()
    conn.close()

init_dialogues_db()
init_forum_db()

# ========================
# Миграция: добавляем колонку guest_id в users, если её нет
# ========================
def migrate_users():
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    # Проверяем, существует ли таблица users
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if c.fetchone():
        # Таблица существует, проверяем колонку
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        if "guest_id" not in columns:
            c.execute("ALTER TABLE users ADD COLUMN guest_id TEXT")
            logger.info("Добавлена колонка guest_id в таблицу users")
    else:
        logger.info("Таблица users ещё не создана, пропускаем миграцию")
    conn.commit()
    conn.close()
# ========================
# Бесплатный лимит сообщений для незарегистрированных
# ========================
FREE_MESSAGE_LIMIT = 10  # бесплатных сообщений

def init_free_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/free_usage.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS free_usage (
            user_id TEXT PRIMARY KEY,
            message_count INTEGER DEFAULT 0,
            first_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_free_count(user_id: str) -> int:
    conn = sqlite3.connect("data/free_usage.db")
    c = conn.cursor()
    c.execute("SELECT message_count FROM free_usage WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def increment_free_count(user_id: str):
    conn = sqlite3.connect("data/free_usage.db")
    c = conn.cursor()
    c.execute("INSERT INTO free_usage (user_id, message_count) VALUES (?, 1) "
              "ON CONFLICT(user_id) DO UPDATE SET message_count = message_count + 1", (user_id,))
    conn.commit()
    conn.close()

async def check_free_limit(user_id: str) -> bool:
    # Проверяем, есть ли у пользователя активная подписка (premium)
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    # Проверяем по user_id (может быть как числовой id, так и текстовый guest_id)
    c.execute("SELECT premium_until FROM users WHERE id=? OR guest_id=?", (user_id, user_id))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        premium_until = datetime.fromisoformat(row[0])
        if premium_until > datetime.now():
            return True  # есть активная подписка – безлимит

    # Проверяем бесплатный лимит
    count = get_free_count(user_id)
    if count < FREE_MESSAGE_LIMIT:
        increment_free_count(user_id)
        return True
    return False

init_free_db()
from auth_db import init_db
init_db()
migrate_users()

# ========================
# Авторизация через Telegram (Bearer JWT) – используется для защищённых эндпоинтов
# ========================
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

# ========================
# Pydantic модели
# ========================
class RegisterRequest(BaseModel):
    email: str
    password: str
    username: str = ""
    guest_id: Optional[str] = None  # добавлено для синхронизации

class LoginRequest(BaseModel):
    email: str
    password: str
    guest_id: Optional[str] = None  # можно тоже передавать для синхронизации

class ChatRequest(BaseModel):
    message: str
    role: str
    user_id: str

class ChatResponse(BaseModel):
    response: str

class MoodRequest(BaseModel):
    user_id: str
    mood: int
    note: Optional[str] = ""

class MoodHistoryResponse(BaseModel):
    entries: List[dict]

class AdviceResponse(BaseModel):
    advice: str

class ClearHistoryResponse(BaseModel):
    status: str
    message: str

class DonateRequest(BaseModel):
    amount: float
    user_id: Optional[int] = None

class TestSubmitRequest(BaseModel):
    test_id: str
    answers: List[int]
    user_id: str

# ========================
# Эндпоинты регистрации и входа
# ========================
@app.post("/auth/register")
async def register(request: RegisterRequest):
    init_db()
    migrate_users()  # убедимся, что колонка есть
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=?", (request.email,))
    if c.fetchone():
        conn.close()
        raise HTTPException(400, "Email уже используется")
    pwd = hash_password(request.password)
    c.execute("INSERT INTO users (email, password_hash, username, guest_id) VALUES (?,?,?,?)",
              (request.email, pwd, request.username, request.guest_id))
    user_id = c.lastrowid
    # Активация триального Premium на 30 дней
    trial_end = (datetime.now() + timedelta(days=10)).isoformat()
    c.execute("UPDATE users SET premium_until=? WHERE id=?", (trial_end, user_id))
    conn.commit()
    conn.close()
    # Здесь можно было бы перенести диалоги из guest_id в новый user_id, но оставим для будущего
    return {"user_id": user_id, "email": request.email}

@app.post("/auth/login")
async def login(request: LoginRequest):
    init_db()
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    pwd = hash_password(request.password)
    c.execute("SELECT id, email, username, telegram_id FROM users WHERE email=? AND password_hash=?",
              (request.email, pwd))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(401, "Неверные учетные данные")
    return {"user_id": row[0], "email": row[1], "username": row[2], "telegram_id": row[3]}

@app.post("/auth/telegram")
async def auth_telegram(data: dict):
    verified = verify_telegram_auth(data.copy())
    if not verified:
        raise HTTPException(401, "Telegram auth failed")
    telegram_id = verified['id']
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    if not row:
        username = verified.get('first_name', '') + ' ' + verified.get('last_name', '')
        c.execute("INSERT INTO users (username, telegram_id) VALUES (?, ?)", (username.strip(), telegram_id))
        user_id = c.lastrowid
    else:
        user_id = row[0]
    conn.commit()
    conn.close()
    token = create_jwt(user_id, telegram_id)
    return {"token": token, "user_id": user_id, "telegram_id": telegram_id}

# ========================
# Платежи (Premium и Донаты)
# ========================
@app.post("/create_premium_payment")
async def create_premium_payment(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(400, "user_id обязателен")
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE id=?", (user_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Пользователь не найден")
    conn.close()

    payment = Payment.create({
        "amount": {"value": "490.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://doctorhauz.ru/success.html"},
        "capture": True,
        "description": "Premium подписка на 1 месяц",
        "metadata": {"user_id": user_id}
    })

    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    c.execute("INSERT INTO payments (user_id, amount, yookassa_id, status) VALUES (?, ?, ?, ?)",
              (user_id, 490.00, payment.id, "pending"))
    conn.commit()
    conn.close()
    return {"payment_id": payment.id, "confirmation_url": payment.confirmation.confirmation_url}

@app.post("/yookassa_webhook")
async def yookassa_webhook(request: Request):
    data = await request.json()
    if data.get("event") == "payment.succeeded":
        payment_id = data["object"]["id"]
        metadata = data["object"].get("metadata", {})
        user_id = metadata.get("user_id")
        if user_id:
            activate_premium(int(user_id), days=30)
            conn = sqlite3.connect("data/users.db")
            c = conn.cursor()
            c.execute("UPDATE payments SET status='succeeded' WHERE yookassa_id=?", (payment_id,))
            conn.commit()
            conn.close()
    return {"status": "ok"}

@app.post("/create_donation")
async def create_donation(request: DonateRequest):
    amount = max(50.0, request.amount)
    payment = Payment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://doctorhauz.ru/thanks.html"},
        "capture": True,
        "description": "Добровольное пожертвование на развитие проекта",
        "metadata": {"user_id": request.user_id or 0}
    })
    return {"confirmation_url": payment.confirmation.confirmation_url}

@app.get("/premium_status")
async def premium_status(user_id: int):
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    c.execute("SELECT premium_until FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Пользователь не найден")
    premium_until = row[0]
    if premium_until and datetime.fromisoformat(premium_until) > datetime.now():
        return {"active": True, "until": premium_until}
    return {"active": False}

# ========================
# Функции для работы с историей диалогов
# ========================
def get_conversation_context(user_id: str, max_messages: int = 4) -> str:
    history = conversation_history.get(user_id, [])
    if not history:
        return ""
    recent = history[-max_messages:]
    lines = ["Краткая предыстория:"]
    for msg in recent:
        if msg["role"] == "user":
            lines.append(f"- Пользователь: {msg['content']}")
    return "\n".join(lines)

def add_to_history(user_id: str, user_message: str, bot_response: str):
    history = conversation_history[user_id]
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": bot_response})
    if len(history) > MAX_HISTORY_LENGTH:
        conversation_history[user_id] = history[-MAX_HISTORY_LENGTH:]

def clear_history(user_id: str):
    if user_id in conversation_history:
        conversation_history[user_id] = []
        return True
    return False

# ========================
# Функции для извлечения имени пользователя
# ========================
def extract_and_store_name(user_id: str, message: str) -> str:
    stop_words = {"внимание", "привет", "здравствуй"}
    patterns = [
        r"меня зовут\s+([А-Яа-яёЁ\-]+)",
        r"меня звать\s+([А-Яа-яёЁ\-]+)",
        r"я\s+([А-Яа-яёЁ\-]+)$",
        r"зовут\s+([А-Яа-яёЁ\-]+)"
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            name = match.group(1).capitalize()
            if name.lower() in stop_words:
                continue
            user_names[user_id] = name
            logger.info(f"Сохранили имя {name} для user_id {user_id}")
            return name
    return user_names.get(user_id, "")

# ========================
# Определение "опасных" тем
# ========================
SENSITIVE_KEYWORDS = [
    "сво", "война", "военный", "боец", "птср", "насили", "бьёт", "побои",
    "алкогол", "пьёт", "агресси", "рукоприклад", "ветеран", "стрельба",
    "убил", "погиб", "контузи", "вооруж"
]

def is_sensitive_topic(query: str) -> bool:
    low = query.lower()
    return any(kw in low for kw in SENSITIVE_KEYWORDS)

def build_fallback_from_chunks(query: str, chunks: list, role: str, user_name: str = "") -> str:
    if not chunks:
        return ("Слушай, в моей базе знаний пока нет точного ответа на этот вопрос. "
                "Но я рядом. Расскажи, что у тебя на душе? Если чувствуешь, что нужна срочная помощь — звони 112 или 8-800-2000-122.")
    if role == "Мужчина":
        prefix = "Слушай, у меня нет готового ответа, но вот что я знаю и что может тебе помочь:\n\n"
    else:
        prefix = "Вот информация, которая может быть полезна:\n\n"
    cleaned_chunks = []
    for chunk in chunks[:3]:
        clean = chunk.strip()
        if clean.startswith('#'):
            lines = clean.split('\n', 1)
            clean = lines[1] if len(lines) > 1 else clean
        cleaned_chunks.append(f"• {clean}")
    answer = prefix + "\n\n".join(cleaned_chunks)
    if role == "Мужчиа":
        answer += "\n\nЭто не всё, что можно сказать. Давай продолжим разговор — расскажи, что тебя сильнее всего цепляет из написанного?"
    else:
        answer += "\n\nЕсли нужно прояснить что-то из этого, просто спросите."
    return answer

# ========================
# Генерация ответа
# ========================
async def run_async_generate(query: str, role: str, user_id: str) -> str:
    try:
        # Извлекаем имя, если пользователь представился
        user_name = extract_and_store_name(user_id, query)
        if not user_name:
            # Проверяем, не сохранено ли имя ранее
            user_name = user_names.get(user_id, '')

        # Если имя есть, вставляем обращение в начало ответа
        greeting_prefix = f"{user_name}, " if user_name else ""

        logger.info(f"Генерация для роли: {role}")
        context_chunks = knowledge_base.search(query, top_k=10)
        logger.info(f"Поиск завершён, найдено чанков: {len(context_chunks)}")

        if is_sensitive_topic(query):
            logger.info("Чувствительная тема, используем fallback без GPT")
            answer = build_fallback_from_chunks(query, context_chunks, role, user_name)
            add_to_history(user_id, query, answer)
            save_dialogue(user_id, role, query, answer)
            return answer

        conversation_context = get_conversation_context(user_id, max_messages=6)
        enhanced_query = query_with_name
        if conversation_context:
            enhanced_query = f"{conversation_context}\n\nНовый вопрос: {query_with_name}"
            logger.info(f"Добавлен контекст истории для user_id={user_id}")

        user_id_int = hash(user_id) % 1000000
        answer = await generate_answer(
            query=enhanced_query,
            context_chunks=context_chunks,
            role=role,
            user_id=user_id_int
        )

        if is_refusal(answer):
            logger.warning("YandexGPT отказался, используем fallback")
            answer = build_fallback_from_chunks(query, context_chunks, role, user_name)

        add_to_history(user_id, query, answer)
        save_dialogue(user_id, role, query, answer)
        return answer

        final_answer = greeting_prefix + answer
        return final_answer

    except Exception as e:
        logger.exception("Ошибка при генерации ответа")
        return f"Произошла ошибка: {str(e)}"

# ========================
# Основные эндпоинты чата и дневника
# ========================

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    # user_id передаётся с фронтенда (генерируется в localStorage)
    actual_user_id = request.user_id
    if not actual_user_id:
        actual_user_id = f"guest_{datetime.now().timestamp()}"

    # Проверяем лимит бесплатных сообщений
    if not await check_free_limit(actual_user_id):
        return ChatResponse(
            response="🔒 Вы исчерпали бесплатный лимит сообщений. Зарегистрируйтесь, чтобы продолжить пользоваться Доктором Хаузом без ограничений! 👉 /register"
        )

    answer = await run_async_generate(request.message, request.role, actual_user_id)
    return ChatResponse(response=answer)

@app.post("/clear_history")
async def clear_history_endpoint(user_id: str):
    clear_history(user_id)
    proactive_shown[user_id] = False
    if user_id in user_names:
        del user_names[user_id]
    return ClearHistoryResponse(status="ok", message="История диалога и имя очищены")

@app.post("/mood")
async def mood_endpoint(request: MoodRequest):
    try:
        save_mood(request.user_id, request.mood, request.note)
        return {"status": "ok"}
    except Exception as e:
        logger.exception("Ошибка сохранения настроения")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/mood_history/{user_id}")
async def mood_history_endpoint(user_id: str):
    try:
        history = get_mood_history(user_id)
        return MoodHistoryResponse(entries=history)
    except Exception as e:
        logger.exception("Ошибка получения истории настроений")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/advice", response_model=AdviceResponse)
async def advice_endpoint():
    try:
        advice = get_daily_advice()
        return AdviceResponse(advice=advice)
    except Exception as e:
        logger.exception("Ошибка получения совета")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/greeting/{role}")
async def get_greeting(role: str):
    avatar = ROLE_AVATARS.get(role, ROLE_AVATARS["Мужчина"])
    return {"greeting": avatar["greeting"]}

@app.get("/dialogues/{user_id}")
async def get_dialogues(user_id: str, limit: int = 20):
    conn = sqlite3.connect("data/dialogues.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT question, answer, timestamp FROM dialogues
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"question": row["question"], "answer": row["answer"], "timestamp": row["timestamp"]} for row in rows]

# ========================
# Эндпоинты форума
# ========================
@app.get("/forum/topics")
async def forum_topics(page: int = 1, per_page: int = 10):
    return get_topics_paginated(page, per_page)

@app.post("/forum/topic")
async def create_topic_endpoint(user_id: int, title: str, content: str):
    if not title or not content:
        raise HTTPException(400, "Заголовок и содержание обязательны")
    topic_id = create_topic(str(user_id), title, content)
    return {"topic_id": topic_id}

@app.get("/forum/topic/{topic_id}")
async def get_topic_endpoint(topic_id: int, user_id: Optional[int] = None):
    topic = get_topic(topic_id)
    if not topic:
        raise HTTPException(404, "Тема не найдена")
    comments = get_comments_with_likes(topic_id, user_id)
    return {"topic": topic, "comments": comments}

@app.put("/forum/topic/{topic_id}")
async def edit_topic(topic_id: int, title: str, content: str, user_id: int):
    if not title or not content:
        raise HTTPException(400, "Заголовок и содержание обязательны")
    ok = update_topic(topic_id, title, content, user_id)
    if not ok:
        raise HTTPException(403, "Нет прав или тема не найдена")
    return {"status": "updated"}

@app.delete("/forum/topic/{topic_id}")
async def delete_topic_endpoint(topic_id: int, user_id: int):
    ok = delete_topic(topic_id, user_id)
    if not ok:
        raise HTTPException(403, "Нет прав или тема не найдена")
    return {"status": "deleted"}

@app.post("/forum/comment")
async def add_comment_endpoint(topic_id: int, user_id: int, content: str):
    if not content:
        raise HTTPException(400, "Комментарий не может быть пустым")
    topic = get_topic(topic_id)
    if not topic:
        raise HTTPException(404, "Тема не найдена")
    is_expert = is_user_expert(user_id)
    comment_id = add_comment(topic_id, user_id, content, is_expert)
    return {"comment_id": comment_id, "is_expert": is_expert}

@app.put("/forum/comment/{comment_id}")
async def edit_comment(comment_id: int, content: str, user_id: int):
    if not content:
        raise HTTPException(400, "Текст комментария обязателен")
    ok = update_comment(comment_id, content, user_id)
    if not ok:
        raise HTTPException(403, "Нет прав или комментарий не найден")
    return {"status": "updated"}

@app.delete("/forum/comment/{comment_id}")
async def delete_comment_endpoint(comment_id: int, user_id: int):
    ok = delete_comment(comment_id, user_id)
    if not ok:
        raise HTTPException(403, "Нет прав или комментарий не найден")
    return {"status": "deleted"}

@app.post("/forum/like/{comment_id}")
async def like_comment(comment_id: int, user_id: int):
    liked = toggle_like(user_id, comment_id)
    like_count = get_like_count(comment_id)
    return {"liked": liked, "like_count": like_count}

@app.post("/forum/add-to-kb")
async def add_comment_to_kb(comment_id: int, user_id: int, tags: List[str]):
    if not is_user_expert(user_id):
        raise HTTPException(403, "Только эксперты могут добавлять в базу знаний")
    comment = get_comment_by_id(comment_id)
    if not comment:
        raise HTTPException(404, "Комментарий не найден")
    add_chunk_to_kb(comment["content"], tags, knowledge_base)
    if not is_already_picked(comment_id):
        mark_expert_pick(comment["topic_id"], comment_id)
    return {"status": "added", "message": "Чанк добавлен в базу знаний и индекс обновлён"}

# ========================
# НОВЫЕ ЭНДПОИНТЫ ДЛЯ ПСИХОЛОГИЧЕСКИХ ТЕСТОВ
# ========================

@app.get("/tests/list")
async def get_tests_list():
    """Возвращает список доступных тестов"""
    tests = [
        {"id": "anxiety", "name": "Краткий опросник тревожности", "questions_count": 5},
        {"id": "compatibility", "name": "Совместимость пары", "questions_count": 5},
        {"id": "parenting", "name": "Стиль воспитания", "questions_count": 5},
        {"id": "self_acceptance", "name": "Самопринятие", "questions_count": 5},
        {"id": "self_esteem", "name": "Лесенка (самооценка)", "questions_count": 5},
    ]
    return {"tests": tests}

@app.get("/tests/{test_id}/questions")
async def get_test_questions(test_id: str):
    """Возвращает вопросы для конкретного теста"""
    questions_map = {
        "anxiety": [
            "Я часто испытываю беспокойство без видимой причины.",
            "Мне трудно заснуть из-за тревожных мыслей.",
            "Я легко раздражаюсь по пустякам.",
            "Мне кажется, что окружающие относятся ко мне негативно.",
            "Я часто чувствую внутреннее напряжение."
        ],
        "compatibility": [
            "Мы с партнёром легко находим общий язык в спорных вопросах.",
            "Наши взгляды на жизнь совпадают.",
            "Мы поддерживаем друг друга в трудных ситуациях.",
            "Нам нравится проводить время вместе.",
            "Мы уважаем личные границы друг друга."
        ],
        "parenting": [
            "Я часто объясняю ребёнку, почему его поведение неправильно.",
            "Я редко хвалю ребёнка, чтобы он не зазнавался.",
            "Я всегда прислушиваюсь к мнению ребёнка.",
            "Я строго контролирую, с кем дружит мой ребёнок.",
            "Я поощряю ребёнка за любые успехи."
        ],
        "self_acceptance": [
            "Я принимаю себя таким, какой я есть.",
            "Мне трудно прощать себе ошибки.",
            "Я считаю себя достойным любви и уважения.",
            "Я часто критикую себя за недостатки.",
            "Я доволен своей внешностью."
        ],
        "self_esteem": [
            "Поставьте себе оценку от 1 до 10, как вы оцениваете свою уверенность в себе.",
            "Поставьте оценку своей способности достигать целей.",
            "Оцените свою социальную привлекательность.",
            "Оцените, насколько вы довольны своей профессией.",
            "Оцените свою способность справляться со стрессом."
        ]
    }
    if test_id not in questions_map:
        raise HTTPException(404, "Тест не найден")
    return {"test_id": test_id, "questions": questions_map[test_id], "scale": "1-5"}

@app.post("/tests/submit")
async def submit_test(request: TestSubmitRequest):
    """Принимает ответы и возвращает результат"""
    if not TEST_HANDLERS_AVAILABLE:
        # Заглушка: просто суммируем баллы и даём интерпретацию
        total = sum(request.answers)
        avg = total / len(request.answers)
        if request.test_id == "anxiety":
            if avg <= 2:
                result = "Низкий уровень тревожности. Вы спокойны и уравновешены."
            elif avg <= 3.5:
                result = "Средний уровень тревожности. Рекомендуется обратить внимание на методы релаксации."
            else:
                result = "Высокий уровень тревожности. Рекомендуется обратиться к психологу."
        elif request.test_id == "compatibility":
            if avg >= 4:
                result = "Высокая совместимость. У вас гармоничные отношения."
            elif avg >= 3:
                result = "Средняя совместимость. Есть зоны для роста."
            else:
                result = "Низкая совместимость. Рекомендуется работа над отношениями."
        elif request.test_id == "parenting":
            if avg >= 4:
                result = "Демократичный стиль воспитания. Вы создаёте здоровую атмосферу."
            elif avg >= 3:
                result = "Смешанный стиль. Обратите внимание на баланс контроля и поддержки."
            else:
                result = "Авторитарный стиль. Возможно, стоит больше прислушиваться к ребёнку."
        elif request.test_id == "self_acceptance":
            if avg >= 4:
                result = "Высокий уровень самопринятия. Вы уверены в себе."
            elif avg >= 3:
                result = "Средний уровень. Работайте над любовью к себе."
            else:
                result = "Низкий уровень самопринятия. Рекомендуется консультация психолога."
        elif request.test_id == "self_esteem":
            if avg >= 8:
                result = "Высокая самооценка. Вы адекватно оцениваете свои возможности."
            elif avg >= 5:
                result = "Средняя самооценка. Есть над чем работать."
            else:
                result = "Низкая самооценка. Важно развивать уверенность."
        else:
            result = "Спасибо за прохождение теста!"
        return {"result": result}

    # Если test_handlers доступны, используем их
    try:
        if request.test_id == "anxiety":
            result = calculate_anxiety(request.answers)
        elif request.test_id == "compatibility":
            result = calculate_compatibility(request.answers)
        elif request.test_id == "parenting":
            result = calculate_parenting_style(request.answers)
        elif request.test_id == "self_acceptance":
            result = calculate_self_acceptance(request.answers)
        elif request.test_id == "self_esteem":
            result = calculate_self_esteem(request.answers)
        else:
            raise HTTPException(404, "Тест не найден")
        # Можно сохранить результат в БД
        return {"result": result}
    except Exception as e:
        logger.exception("Ошибка при расчёте теста")
        raise HTTPException(500, str(e))

# ========================
# Статика
# ========================
app.mount("/docs", StaticFiles(directory="static/docs"), name="docs")
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)