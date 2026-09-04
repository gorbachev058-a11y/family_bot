import asyncio
import logging
import os
import time
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    BOT_TOKEN, KNOWLEDGE_BASE_PATH,
    YC_USE_GPT, TAVILY_USE_SEARCH
)
from knowledge_base import KnowledgeBase
from rag import generate_answer
from utils import recognize_speech
from test_handlers import router as test_router
from test_handlers import get_tests_keyboard
from states import (
    UserRole, TestStates,
    LadderTest, AnxietyTest,
    CompatibilityTest, ParentingStyleTest, SelfAcceptanceTest
)
from token_usage import init_db
from auth_db import init_db as init_auth_db, hash_password
from values_tests import router as values_router

# ================== ДОБАВЛЯЕМ СОСТОЯНИЯ ДЛЯ РЕГИСТРАЦИИ ==================
class RegisterStates(StatesGroup):
    waiting_email = State()
    waiting_password = State()

# ================== НАСТРОЙКА ЛОГИРОВАНИЯ ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ИНИЦИАЛИЗАЦИЯ БОТА ==================
bot = Bot(token=BOT_TOKEN)

# --- Условное создание хранилища FSM ---
if os.getenv("ENV") == "production":
    try:
        from aiogram.fsm.storage.redis import RedisStorage, Redis
        redis = Redis(host='localhost', port=6379, db=0, decode_responses=True)
        storage = RedisStorage(redis)
        logger.info("Используется RedisStorage")
    except Exception as e:
        logger.warning(f"Redis недоступен, переключение на MemoryStorage: {e}")
        from aiogram.fsm.storage.memory import MemoryStorage
        storage = MemoryStorage()
else:
    from aiogram.fsm.storage.memory import MemoryStorage
    storage = MemoryStorage()
    logger.info("Используется MemoryStorage (локальная разработка)")

dp = Dispatcher(storage=storage)

dp.include_router(test_router)
dp.include_router(values_router)

kb = KnowledgeBase(KNOWLEDGE_BASE_PATH)

role_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мужчина")],
        [KeyboardButton(text="Женщина")],
        [KeyboardButton(text="Пара (вместе)")],
        [KeyboardButton(text="Ребёнок")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите вашу роль..."
)

# ================== УСТАНОВКА МЕНЮ КОМАНД ==================
async def set_bot_command():
    commands = [
        types.BotCommand(command="start", description="🚀 Начать работу / выбрать роль"),
        types.BotCommand(command="register", description="📝 Зарегистрироваться"),
        types.BotCommand(command="tariffs", description="💎 Тарифы Premium"),
        types.BotCommand(command="premium", description="⭐ Статус Premium"),
        types.BotCommand(command="donate", description="❤️ Поддержать проект"),
        types.BotCommand(command="tests", description="📋 Психологические тесты"),
        types.BotCommand(command="changerole", description="🔄 Сменить роль"),
        types.BotCommand(command="help", description="❓ Помощь"),
        types.BotCommand(command="legal", description="📄 Юридическая информация"),
    ]
    await bot.set_my_commands(commands)

# ================== ФУНКЦИЯ ОТПРАВКИ ДЛИННЫХ СООБЩЕНИЙ ==================
async def send_long_message(message: types.Message, text: str):
    MAX_LENGTH = 4000
    if len(text) <= MAX_LENGTH:
        await message.answer(text)
    else:
        parts = []
        current_part = ""
        for line in text.split('\n'):
            if len(current_part) + len(line) + 1 <= MAX_LENGTH:
                current_part += line + '\n'
            else:
                if current_part:
                    parts.append(current_part)
                current_part = line + '\n'
        if current_part:
            parts.append(current_part)
        for i, part in enumerate(parts, 1):
            await message.answer(f"📄 Часть {i}/{len(parts)}:\n\n{part}")

# ================== КОМАНДА /START ==================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    init_auth_db()
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    telegram_id = message.from_user.id

    c.execute("SELECT id, premium_until FROM users WHERE telegram_id=?", (telegram_id,))
    user_row = c.fetchone()

    if not user_row:
        c.execute("INSERT INTO users (telegram_id, username) VALUES (?, ?)",
                  (telegram_id, message.from_user.full_name or ""))
        conn.commit()
        trial_end = (datetime.now() + timedelta(days=10)).isoformat()
        c.execute("UPDATE users SET premium_until=? WHERE telegram_id=?", (trial_end, telegram_id))
        conn.commit()
    else:
        if user_row[1] is None:
            trial_end = (datetime.now() + timedelta(days=10)).isoformat()
            c.execute("UPDATE users SET premium_until=? WHERE telegram_id=?", (trial_end, telegram_id))
            conn.commit()
    conn.close()

    welcome_text = (
        "👋 Здравствуйте! Я — **Доктор Хауз**, ваш семейный психолог.\n\n"
        "Перед началом работы ознакомьтесь с важными документами:\n"
        "📄 <a href='https://doctorhauz.ru/docs/privacy_policy.html'>Политика конфиденциальности</a>\n"
        "📄 <a href='https://doctorhauz.ru/docs/user_agreement.html'>Пользовательское соглашение</a>\n"
        "📄 <a href='https://doctorhauz.ru/docs/consent_form.html'>Согласие на обработку данных</a>\n"
        "📄 <a href='https://doctorhauz.ru/docs/public_offer.html'>Публичная оферта</a>\n\n"
        "Нажимая кнопку ниже, вы подтверждаете, что принимаете условия."
    )
    btn_accept = InlineKeyboardButton(text="✅ Принимаю условия", callback_data="accept_terms")
    markup = InlineKeyboardMarkup(inline_keyboard=[[btn_accept]])
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=markup)

# ================== КОМАНДА /REGISTER ==================
@dp.message(Command("register"))
async def cmd_register(message: types.Message, state: FSMContext):
    await message.answer("📝 Введите ваш email (например, user@example.com):")
    await state.set_state(RegisterStates.waiting_email)

@dp.message(RegisterStates.waiting_email)
async def register_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    if "@" not in email or "." not in email:
        await message.answer("❌ Некорректный email. Попробуйте ещё раз:")
        return
    await state.update_data(email=email)
    await message.answer("Теперь введите пароль (минимум 6 символов):")
    await state.set_state(RegisterStates.waiting_password)

@dp.message(RegisterStates.waiting_password)
async def register_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    if len(password) < 6:
        await message.answer("❌ Пароль должен быть не короче 6 символов. Попробуйте ещё раз:")
        return

    data = await state.get_data()
    email = data.get("email")
    telegram_id = message.from_user.id
    username = message.from_user.full_name or ""

    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE email=?", (email,))
    if c.fetchone():
        await message.answer("❌ Этот email уже зарегистрирован. Используйте другой email.")
        conn.close()
        await state.clear()
        return

    c.execute("SELECT id, guest_id FROM users WHERE telegram_id=?", (telegram_id,))
    existing = c.fetchone()
    pwd_hash = hash_password(password)

    if existing:
        user_id, guest_id = existing
        c.execute("UPDATE users SET email=?, password_hash=?, username=? WHERE id=?",
                  (email, pwd_hash, username, user_id))
        await message.answer("✅ Ваш аккаунт обновлён: email привязан к этому Telegram.")
    else:
        c.execute("INSERT INTO users (telegram_id, email, password_hash, username) VALUES (?, ?, ?, ?)",
                  (telegram_id, email, pwd_hash, username))
        user_id = c.lastrowid
        trial_end = (datetime.now() + timedelta(days=10)).isoformat()
        c.execute("UPDATE users SET premium_until=? WHERE id=?", (trial_end, user_id))
        await message.answer("✅ Регистрация успешна! Вы получили 10 дней Premium бесплатно.")

    conn.commit()
    conn.close()
    await state.clear()

# ================== КОМАНДА /TARIFFS ==================
@dp.message(Command("tariffs"))
async def cmd_tariffs(message: types.Message):
    text = (
        "💎 **Тарифы Premium**\n\n"
        "📅 1 месяц  — 490 ₽\n"
        "📅 3 месяца — 1 290 ₽\n"
        "📅 6 месяцев — 2 490 ₽\n"
        "📅 12 месяцев — 3 990 ₽\n\n"
        "🔹 Неограниченные консультации\n"
        "🔹 Все психологические тесты\n"
        "🔹 Дневник настроения\n"
        "🔹 Советы эксперта\n\n"
        "Оформить подписку можно на сайте:"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💳 Перейти к оплате", url="https://doctorhauz.ru/tariffs.html")]
    ])
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")

# ================== КОМАНДА /PREMIUM ==================
@dp.message(Command("premium"))
async def premium_status(message: types.Message):
    telegram_id = message.from_user.id
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    c.execute("SELECT premium_until, email FROM users WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    conn.close()

    if row:
        until, email = row
        if until:
            until_date = datetime.fromisoformat(until)
            if until_date > datetime.now():
                text = f"✅ Ваш Premium активен до {until_date.strftime('%d.%m.%Y')}\n"
                text += f"📧 Email: {email or 'не указан'}"
            else:
                text = "⚠️ Срок Premium истёк. Продлите подписку."
        else:
            text = "У вас нет Premium. Оформите подписку."
    else:
        text = "Вы не зарегистрированы. Используйте /register для создания аккаунта."

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💳 Оформить Premium", url="https://doctorhauz.ru/tariffs.html")]
    ])
    await message.answer(text, reply_markup=markup)

# ================== КОМАНДА /DONATE ==================
@dp.message(Command("donate"))
async def donate(message: types.Message):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("100 ₽", url="https://doctorhauz.ru/donate.html?amount=100")],
        [InlineKeyboardButton("500 ₽", url="https://doctorhauz.ru/donate.html?amount=500")],
        [InlineKeyboardButton("Своя сумма", url="https://doctorhauz.ru/donate.html")]
    ])
    await message.answer("❤️ Поддержите проект. Любое пожертвование поможет нам развиваться.", reply_markup=markup)

# ================== ОБРАБОТКА ПРИНЯТИЯ УСЛОВИЙ ==================
@dp.callback_query(F.data == "accept_terms")
async def accept_terms(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup()
    await call.message.answer(
        "Чтобы я мог давать более точные советы, выберите вашу роль:",
        reply_markup=role_keyboard
    )
    await state.set_state(UserRole.choosing_role)

# ================== ОСТАЛЬНЫЕ КОМАНДЫ ==================
@dp.message(Command("legal"))
async def cmd_legal(message: types.Message):
    legal_text = (
        "📄 <a href='https://doctorhauz.ru/docs/privacy_policy.html'>Политика конфиденциальности</a>\n"
        "📄 <a href='https://doctorhauz.ru/docs/user_agreement.html'>Пользовательское соглашение</a>\n"
        "📄 <a href='https://doctorhauz.ru/docs/consent_form.html'>Согласие на обработку данных</a>\n"
        "📄 <a href='https://doctorhauz.ru/docs/public_offer.html'>Публичная оферта</a>"
    )
    await message.answer(legal_text, parse_mode="HTML")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "🆘 **Помощь**\n"
        "/start - начать работу и выбрать роль\n"
        "/register - зарегистрироваться (email+пароль)\n"
        "/tariffs - тарифы Premium\n"
        "/premium - статус подписки\n"
        "/donate - поддержать проект\n"
        "/tests - психологические тесты\n"
        "/changerole - сменить роль\n"
        "/legal - юридическая информация\n"
        "/help - это сообщение\n\n"
        "Вы можете задавать вопросы текстом или голосом. "
        "Я использую базу знаний по семейной психологии, "
        f"{'а также интернет-поиск' if YC_USE_GPT else 'пока без ИИ'}."
    )

@dp.message(Command("changerole"))
async def cmd_changerole(message: types.Message, state: FSMContext):
    await message.answer(
        "Выберите новую роль:",
        reply_markup=role_keyboard
    )
    await state.set_state(UserRole.choosing_role)

@dp.message(Command("tests"))
async def cmd_tests(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сначала выберите роль через /start")
        return
    if current_state == UserRole.choosing_role:
        await message.answer("Сначала завершите выбор роли через /start")
        return
    await message.answer(
        "📋 **Психологические тесты**\n\nВыберите тест:",
        reply_markup=get_tests_keyboard()
    )
    await state.set_state(TestStates.choosing_test)

# ================== ОБРАБОТКА ВЫБОРА РОЛИ (С АВАТАРОМ СОРАТНИКА) ==================
@dp.message(UserRole.choosing_role)
async def role_chosen(message: types.Message, state: FSMContext):
    role = message.text
    if role not in ["Мужчина", "Женщина", "Пара (вместе)", "Ребёнок"]:
        await message.answer(
            "Пожалуйста, выберите роль, используя кнопки ниже.",
            reply_markup=role_keyboard
        )
        return

    await state.update_data(role=role)
    await state.set_state(UserRole.chatting)

    from config import ROLE_AVATARS
    avatar = ROLE_AVATARS.get(role, {})

    if role == "Мужчина":
        greeting = avatar.get("greeting", "Привет. Я Соратник.")
        welcome_text = (
            f"👊 {greeting}\n\n"
            "✅ Роль 'Мужчина' сохранена. Я, Доктор Хауз, готов помочь.\n"
            "🤖 Отвечаю с использованием своей базы знаний и интернет-поиска.\n"
            "📋 Команды:\n"
            "/tests - психологические тесты\n"
            "/changerole - сменить роль\n"
            "/help - справка\n\n"
            "Помните: я лишь помощник, мои советы не заменяют профессиональную помощь."
        )
    elif role == "Ребёнок":
        welcome_text = (
            f"✅ Привет! Ты выбрал роль '{role}'.\n\n"
            "Я — Доктор Хауз, и я буду отвечать простым и понятным языком. Ты можешь спросить меня о:\n"
            "• друзьях и как с ними дружить\n"
            "• страхах и как их победить\n"
            "• учёбе и школе\n"
            "• отношениях с родителями\n\n"
            "Также у нас есть классные тесты — команда /tests"
        )
    else:
        ai_status = "с использованием своей базы знаний и интернет-поиска" if YC_USE_GPT else "в режиме базы знаний"
        welcome_text = (
            f"✅ Роль '{role}' сохранена. Я, Доктор Хауз, готов помочь.\n"
            f"🤖 Отвечаю {ai_status}.\n"
            "📋 Команды:\n"
            "/tests - психологические тесты\n"
            "/changerole - сменить роль\n"
            "/help - справка\n\n"
            "Помните: я лишь помощник, мои советы не заменяют профессиональную помощь."
        )

    await message.answer(welcome_text, reply_markup=ReplyKeyboardRemove())

# ================== ОБРАБОТКА ВОПРОСОВ ==================
async def process_question(message: types.Message, state: FSMContext, query: str):
    user_data = await state.get_data()
    role = user_data.get('role', 'не указана')

    if YC_USE_GPT:
        thinking = await message.answer("🤔 Анализирую ваш вопрос... (это может занять до 30 секунд)")
    else:
        thinking = await message.answer("🔍 Ищу информацию в базе знаний...")

    start_time = time.time()

    try:
        context_chunks = kb.search(query, top_k=5)
        answer = await generate_answer(query, context_chunks, role, user_id=message.from_user.id)
        elapsed = time.time() - start_time
        logger.info(f"Ответ сгенерирован за {elapsed:.2f} сек для пользователя {message.from_user.id}")
        await thinking.delete()
        await send_long_message(message, answer)
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Ошибка при обработке вопроса за {elapsed:.2f} сек: {e}")
        await thinking.delete()
        await message.answer(
            "❌ Произошла внутренняя ошибка. Пожалуйста, попробуйте позже или напишите вопрос иначе.\n"
            f"Техническая информация: {str(e)}"
        )
        return

    crisis_keywords = [
        "кризис", "насилие", "бить", "избивать", "страх", "суицид",
        "депрессия", "ненавижу", "умереть", "смерть", "покончить",
        "убить", "плохо с собой", "не хочу жить"
    ]
    if any(kw in query.lower() for kw in crisis_keywords):
        await message.answer(
            "⚠️ **Важное предупреждение**\n\n"
            "Если вы или кто-то из ваших близких столкнулись с кризисной ситуацией, "
            "пожалуйста, обратитесь за помощью к специалисту или позвоните на горячую линию:\n"
            "📞 8-800-2000-122 (круглосуточно, анонимно)"
        )

@dp.message(UserRole.chatting, F.text)
async def handle_text(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        return
    await process_question(message, state, message.text)

@dp.message(UserRole.chatting, F.voice)
async def handle_voice(message: types.Message, state: FSMContext):
    processing = await message.answer("🎤 Обрабатываю голосовое сообщение...")
    try:
        file_info = await bot.get_file(message.voice.file_id)
        downloaded = await bot.download_file(file_info.file_path)
        audio_bytes = downloaded.read()
        text = await recognize_speech(audio_bytes)
        await processing.delete()
        if text.startswith("Не удалось") or text.startswith("Ошибка"):
            await message.answer(f"❌ Не удалось распознать речь: {text}. Попробуйте ещё раз или напишите текст.")
            return
        logger.info(f"Распознано от {message.from_user.id}: {text[:100]}...")
        await process_question(message, state, text)
    except Exception as e:
        await processing.delete()
        logger.error(f"Ошибка обработки голоса: {e}")
        await message.answer("❌ Произошла ошибка при обработке голосового сообщения. Попробуйте написать текст.")

# ================== ОБРАБОТКА ВСЕХ ОСТАЛЬНЫХ СООБЩЕНИЙ ==================
@dp.message()
async def handle_other_messages(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Начните с команды /start")
        return
    if current_state == UserRole.choosing_role:
        await message.answer(
            "Пожалуйста, выберите роль с помощью кнопок выше.",
            reply_markup=role_keyboard
        )
        return
    test_states = [
        TestStates.choosing_test,
        LadderTest.waiting_answer,
        AnxietyTest.q1, AnxietyTest.q2, AnxietyTest.q3, AnxietyTest.q4, AnxietyTest.q5,
        CompatibilityTest.q1, CompatibilityTest.q2, CompatibilityTest.q3, CompatibilityTest.q4, CompatibilityTest.q5,
        ParentingStyleTest.q1, ParentingStyleTest.q2, ParentingStyleTest.q3, ParentingStyleTest.q4, ParentingStyleTest.q5,
        SelfAcceptanceTest.q1, SelfAcceptanceTest.q2, SelfAcceptanceTest.q3, SelfAcceptanceTest.q4, SelfAcceptanceTest.q5
    ]
    if current_state in test_states:
        return
    await message.answer("Используйте /start для начала работы")

# ================== ЗАПУСК ==================
async def main():
    logger.info("Бот запускается...")
    # alert bot – закомментировано, т.к. файл alert.py может отсутствовать
    # init_alert_bot()
    logger.info(f"База знаний загружена, {len(kb.chunks)} чанков")
    init_db()
    init_auth_db()
    logger.info(f"YandexGPT: {'Включён' if YC_USE_GPT else 'Выключен'}")
    logger.info(f"Tavily поиск: {'Включён' if TAVILY_USE_SEARCH else 'Выключен'}")
    await set_bot_command()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())