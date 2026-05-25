import asyncio
import logging
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, \
    InlineKeyboardButton

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
from auth_db import init_db
import sqlite3

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Подключаем роутер тестов (для callback-запросов)
dp.include_router(test_router)

# Инициализация базы знаний
kb = KnowledgeBase(KNOWLEDGE_BASE_PATH)

# Клавиатура выбора роли
role_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Муж")],
        [KeyboardButton(text="Жена")],
        [KeyboardButton(text="Пара (вместе)")],
        [KeyboardButton(text="Ребёнок")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите вашу роль..."
)


# Установка меню команд
async def set_bot_commands():
    commands = [
        types.BotCommand(command="start", description="🚀 Начать работу / выбрать роль"),
        types.BotCommand(command="tests", description="📋 Психологические тесты"),
        types.BotCommand(command="changerole", description="🔄 Сменить роль"),
        types.BotCommand(command="help", description="❓ Помощь")
    ]
    await bot.set_my_commands(commands)


# Функция для отправки длинных сообщений
async def send_long_message(message: types.Message, text: str):
    """Разбивает длинное сообщение на части и отправляет по частям"""
    MAX_LENGTH = 4000
    logger.info(f"send_long_message: длина текста {len(text)} символов")
    logger.info(f"Первые 200 символов ответа: {text[:200]}")

    if len(text) <= MAX_LENGTH:
        logger.info("Отправка короткого сообщения")
        await message.answer(text)
        logger.info("Короткое сообщение отправлено")
    else:
        parts = []
        current_part = ""
        lines = text.split('\n')

        for line in lines:
            if len(current_part) + len(line) + 1 <= MAX_LENGTH:
                current_part += line + '\n'
            else:
                if current_part:
                    parts.append(current_part)
                current_part = line + '\n'

        if current_part:
            parts.append(current_part)

        logger.info(f"Отправка {len(parts)} частей")
        for i, part in enumerate(parts, 1):
            if len(parts) > 1:
                await message.answer(f"📄 Часть {i}/{len(parts)}:\n\n{part}")
            else:
                await message.answer(part)
            logger.info(f"Часть {i} отправлена")


# Команда /start

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    init_db()
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    telegram_id = message.from_user.id
    c.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        # Создаём пользователя без email
        c.execute("INSERT INTO users (telegram_id, username) VALUES (?, ?)",
                  (telegram_id, message.from_user.full_name or ""))
        conn.commit()
    conn.close()
    welcome_text = (
        "👋 Здравствуйте! Я — **Доктор Хауз**, ваш семейный психолог.\n\n"
        "Перед началом работы ознакомьтесь с важными документами:\n"
        "📄 <a href='http://127.0.0.1:8000/docs/privacy_policy.html'>Политика конфиденциальности</a>\n"
        "📄 <a href='http://127.0.0.1:8000/docs/user_agreement.html'>Пользовательское соглашение</a>\n"
        "📄 <a href='http://127.0.0.1:8000/docs/consent_form.html'>Согласие на обработку данных</a>\n\n"
        "📄 <a href='http://127.0.0.1:8000/docs/public_offer.html'>Публичная оферта</a>\n"
        "Нажимая кнопку ниже, вы подтверждаете, что принимаете условия."
    )
    markup = InlineKeyboardMarkup()
    btn_accept = InlineKeyboardButton("✅ Принимаю условия", callback_data="accept_terms")
    markup.add(btn_accept)
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=markup)

    # Состояние выбора роли установим после принятия условий
@dp.callback_query_handler(lambda c: c.data == 'accept_terms')
async def accept_terms(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup()  # убираем кнопку
    await call.message.answer(
        "Чтобы я мог давать более точные советы, выберите вашу роль:",
        reply_markup=role_keyboard
    )
    await state.set_state(UserRole.choosing_role)
# Команда /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "🆘 **Помощь**\n"
        "/start - начать работу и выбрать роль\n"
        "/tests - психологические тесты\n"
        "/changerole - сменить роль\n"
        "/help - это сообщение\n\n"
        "Вы можете задавать вопросы текстом или голосом. "
        "Я использую базу знаний по семейной психологии, "
        f"{'а также интернет-поиск' if YC_USE_GPT else 'пока без ИИ'}."
    )


# Команда /changerole - сменить роль
@dp.message(Command("changerole"))
async def cmd_changerole(message: types.Message, state: FSMContext):
    await message.answer(
        "Выберите новую роль:",
        reply_markup=role_keyboard
    )
    await state.set_state(UserRole.choosing_role)


# Команда /tests - показать тесты
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


# Обработка выбора роли
@dp.message(UserRole.choosing_role)
async def role_chosen(message: types.Message, state: FSMContext):
    role = message.text
    if role not in ["Муж", "Жена", "Пара (вместе)", "Ребёнок"]:
        await message.answer(
            "Пожалуйста, выберите роль, используя кнопки ниже.",
            reply_markup=role_keyboard
        )
        return

    await state.update_data(role=role)
    await state.set_state(UserRole.chatting)

    # Персонализированное приветствие
    if role == "Ребёнок":
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


# Основная функция обработки вопроса
async def process_question(message: types.Message, state: FSMContext, query: str):
    user_data = await state.get_data()
    role = user_data.get('role', 'не указана')

    # Сообщаем, что обрабатываем (если включён ИИ, это может занять время)
    if YC_USE_GPT:
        thinking = await message.answer("🤔 Анализирую ваш вопрос... (это может занять до 30 секунд)")
    else:
        thinking = await message.answer("🔍 Ищу информацию в базе знаний...")

    start_time = time.time()

    try:
        # Поиск по базе знаний
        context_chunks = kb.search(query, top_k=5)

        # Генерация ответа (теперь с YandexGPT и Tavily)
        answer = await generate_answer(query, context_chunks, role, user_id=message.from_user.id)

        elapsed = time.time() - start_time
        logger.info(f"Ответ сгенерирован за {elapsed:.2f} сек для пользователя {message.from_user.id}")

        await thinking.delete()

        # Отправка ответа с разбивкой на части
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

    # Проверка на кризисные ключевые слова (дублируем на всякий случай)
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


# Обработка текстовых сообщений (только когда пользователь в режиме чата)
@dp.message(UserRole.chatting)
async def handle_text(message: types.Message, state: FSMContext):
    # Пропускаем команды (они обрабатываются отдельно)
    if message.text.startswith('/'):
        return
    await process_question(message, state, message.text)


# Обработка голосовых сообщений
@dp.message(UserRole.chatting, lambda message: message.voice is not None)
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


# Обработка всех остальных сообщений (включая состояния тестов)
@dp.message()
async def handle_other_messages(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state is None:
        await message.answer("Начните с команды /start")
        return

    # Если пользователь в процессе выбора роли
    if current_state == UserRole.choosing_role:
        await message.answer(
            "Пожалуйста, выберите роль с помощью кнопок выше.",
            reply_markup=role_keyboard
        )
        return

    # Список всех состояний тестов (они обрабатываются в test_handlers)
    test_states = [
        TestStates.choosing_test,
        LadderTest.waiting_answer,
        AnxietyTest.q1, AnxietyTest.q2, AnxietyTest.q3, AnxietyTest.q4, AnxietyTest.q5,
        CompatibilityTest.q1, CompatibilityTest.q2, CompatibilityTest.q3, CompatibilityTest.q4, CompatibilityTest.q5,
        ParentingStyleTest.q1, ParentingStyleTest.q2, ParentingStyleTest.q3, ParentingStyleTest.q4, ParentingStyleTest.q5,
        SelfAcceptanceTest.q1, SelfAcceptanceTest.q2, SelfAcceptanceTest.q3, SelfAcceptanceTest.q4, SelfAcceptanceTest.q5
    ]

    if current_state in test_states:
        # Игнорируем – сообщения обрабатываются хендлерами тестов
        return

    # Если ни одно из условий не подошло
    await message.answer("Используйте /start для начала работы")


# Запуск бота
async def main():
    logger.info("Бот запускается...")
    logger.info(f"База знаний загружена, {len(kb.chunks)} чанков")
    init_db()
    logger.info(f"YandexGPT: {'Включён' if YC_USE_GPT else 'Выключен'}")
    logger.info(f"Tavily поиск: {'Включён' if TAVILY_USE_SEARCH else 'Выключен'}")

    # Устанавливаем команды
    await set_bot_commands()

    # Удаляем вебхук (на всякий случай)
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем поллинг
    await dp.start_polling(bot)

app.mount("/docs", StaticFiles(directory="static/docs"), name="docs")

if __name__ == "__main__":
    asyncio.run(main())