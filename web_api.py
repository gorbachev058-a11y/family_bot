import sqlite3
import os
import logging
import re
from collections import defaultdict
from typing import Optional, List, Dict
from config import ROLE_AVATARS
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from auth_db import init_db, hash_password, activate_premium
from datetime import datetime, timedelta
from yookassa import Configuration, Payment

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "test")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "test")
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# Старые импорты
from rag import generate_answer, is_refusal
from knowledge_base import KnowledgeBase
from mood import save_mood, get_mood_history
from advice import get_daily_advice

# Новые импорты для форума (расширенные функции)
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

# Обновление базы знаний
from kb_updater import add_chunk_to_kb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Доктор Хауз Web API")

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
# Pydantic модели
# ========================
class RegisterRequest(BaseModel):
    email: str
    password: str
    username: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str

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

# ========================
# Эндпоинты регистрации и входа
# ========================
@app.post("/auth/register")
async def register(request: RegisterRequest):
    init_db()
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=?", (request.email,))
    if c.fetchone():
        conn.close()
        raise HTTPException(400, "Email уже используется")
    pwd = hash_password(request.password)
    c.execute("INSERT INTO users (email, password_hash, username) VALUES (?,?,?)",
              (request.email, pwd, request.username))
    user_id = c.lastrowid
    # Активация триального Premium на 30 дней
    trial_end = (datetime.now() + timedelta(days=30)).isoformat()
    c.execute("UPDATE users SET premium_until=? WHERE id=?", (trial_end, user_id))
    conn.commit()
    conn.close()
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

# ========================
# Создание премиум-платежа
# ========================

@app.post("/create_premium_payment")
async def create_premium_payment(user_id: int):
    # Проверим, что пользователь существует
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    c.execute("SELECT id, email FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        raise HTTPException(404, "Пользователь не найден")

    payment = Payment.create({
        "amount": {"value": "490.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://doctorhauz.ru/success"},
        "capture": True,
        "description": "Premium подписка на 1 месяц",
        "metadata": {"user_id": user_id}
    })

    # Сохраним платёж в БД
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
            # Обновим статус в таблице payments
            conn = sqlite3.connect("data/users.db")
            c = conn.cursor()
            c.execute("UPDATE payments SET status='succeeded' WHERE yookassa_id=?", (payment_id,))
            conn.commit()
            conn.close()
    return {"status": "ok"}

# Донат произвольная сумма
class DonateRequest(BaseModel):
    amount: float  # минимум 50 руб
    user_id: int = None  # необязательно

@app.post("/create_donation")
async def create_donation(request: DonateRequest):
    amount = max(50.0, request.amount)
    payment = Payment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://doctorhauz.ru/thanks"},
        "capture": True,
        "description": "Добровольное пожертвование на развитие проекта",
        "metadata": {"user_id": request.user_id or 0}
    })
    return {"confirmation_url": payment.confirmation.confirmation_url}
@app.get("/donate")
async def donate_page():
    from fastapi.responses import FileResponse
    return FileResponse("static/donate.html")

# ========================
# Функции для работы с историей
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
# Функции для работы с именем
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
        return ("Извините, в моей базе знаний пока нет информации. "
                "Обратитесь к психологу или по телефону доверия 8-800-2000-122.")
    answer_parts = []
    if user_name:
        answer_parts.append(f"{user_name}, я не могу дать полноценный ответ через интернет, но вот что нашёл в базе знаний:\n")
    else:
        answer_parts.append("Я не могу дать развёрнутый ответ через интернет, но вот что нашёл в базе знаний:\n")
    for i, chunk in enumerate(chunks[:3], 1):
        clean = chunk
        if clean.startswith('#'):
            lines = clean.split('\n', 1)
            if len(lines) > 1:
                clean = lines[1]
        answer_parts.append(f"**{i}.** {clean}\n")
    if is_sensitive_topic(query):
        answer_parts.append(
            "\n\n⚠️ **Если вы или близкие в сложной ситуации, помощь рядом:**\n"
            "- **112** (служба спасения)\n"
            "- **8-800-2000-122** (детский телефон доверия)\n"
            "- **051** (горячая линия для участников СВО)\n"
            "- Центр социальной поддержки семьи\n\n"
            "Вы не одни, обратитесь за помощью."
        )
    return "\n".join(answer_parts)

# ========================
# Генерация ответа
# ========================
async def run_async_generate(query: str, role: str, user_id: str) -> str:
    try:
        user_name = extract_and_store_name(user_id, query)
        if user_name:
            query_with_name = f"Меня зовут {user_name}. {query}"
        else:
            query_with_name = query
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

    except Exception as e:
        logger.exception("Ошибка при генерации ответа")
        return f"Произошла ошибка: {str(e)}"

# ========================
# Эндпоинты чата и дневника
# ========================
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info(f"Получен запрос: user={request.user_id}, role={request.role}")
    try:
        answer = await run_async_generate(request.message, request.role, request.user_id)
        return ChatResponse(response=answer)
    except Exception as e:
        logger.exception("Ошибка в /chat")
        raise HTTPException(status_code=500, detail=str(e))

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
    avatar = ROLE_AVATARS.get(role, ROLE_AVATARS["Муж"])
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
# Эндпоинты форума (оставлены как были, используют старую auth)
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
# Статика
# ========================
app.mount("/docs", StaticFiles(directory="static/docs"), name="docs")
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)