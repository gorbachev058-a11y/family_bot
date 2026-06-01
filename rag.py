import logging
import asyncio
from config import YC_USE_GPT, TAVILY_USE_SEARCH
from yandex_gpt import ask_yandex_gpt, get_system_prompt_for_role
from tavily_search import TavilySearcher
from cachetools import TTLCache
from state_detector import detect_user_state

# Кеш для ответов: максимум 200 элементов, TTL 3600 секунд (1 час)
cache = TTLCache(maxsize=200, ttl=3600)

logger = logging.getLogger(__name__)

_searcher = None

# Хранилище истории диалогов для детектора зацикливания
_conversation_history = {}


def get_searcher():
    global _searcher
    if _searcher is None and TAVILY_USE_SEARCH:
        _searcher = TavilySearcher()
    return _searcher


def is_refusal(text: str) -> bool:
    """Проверяет, является ли ответ отказом от YandexGPT."""
    refusal_phrases = [
        "не могу обсуждать", "не могу ответить", "не могу дать ответ",
        "извините, я не могу", "не в моей компетенции", "не могу комментировать",
        "не могу говорить на эту тему", "не могу обсуждать эту тему",
        "не могу помочь", "я не могу", "отказываюсь"
    ]
    lower_text = text.lower()
    return any(phrase in lower_text for phrase in refusal_phrases)


def build_fallback_answer(query: str, context_chunks: list, role: str) -> str:
    """
    Формирует ответ из базы знаний, если YandexGPT отказался отвечать.
    """
    # Проверяем ключевые слова для добавления телефонов доверия
    needs_help = any(kw in query.lower() for kw in [
        "насили", "бьёт", "агресс", "побои", "рукоприклад", "угрожа",
        "пьёт", "алкоголь", "не разговаривает", "птср", "сво", "ветеран"
    ])

    if context_chunks:
        answer = (
            "Я не могу самостоятельно дать ответ на этот вопрос, но вот информация из моей базы знаний, "
            "которая может помочь:\n\n"
        )
        for i, chunk in enumerate(context_chunks[:3], 1):
            # Убираем теги #... из начала для читаемости
            clean_chunk = chunk
            if chunk.startswith('#'):
                lines = chunk.split('\n', 1)
                if len(lines) > 1:
                    clean_chunk = lines[1]
            answer += f"**{i}.** {clean_chunk}\n\n"

        if needs_help:
            answer += (
                "❗ **Если вы или ваши близкие подвергаются насилию, немедленно обратитесь за помощью:**\n"
                "- **112** (единая служба спасения)\n"
                "- **8-800-2000-122** (детский телефон доверия)\n"
                "- **051** (горячая линия для участников СВО и их семей)\n"
                "- Центр социальной поддержки семьи (по месту жительства)\n\n"
                "Помните: насилие недопустимо, вы не одни. ✅"
            )
        return answer
    else:
        return (
            "Извините, я не могу ответить на этот вопрос через интернет, "
            "но вы можете обратиться к психологу очно или по телефону доверия **8-800-2000-122**. "
            "Ваша ситуация важна, помощь рядом."
        )


def get_conversation_history_for_detector(user_id: str = "default", max_messages: int = 4) -> list:
    """
    Возвращает последние сообщения диалога для детектора состояния.
    В будущем это будет браться из общего хранилища истории.
    """
    return _conversation_history.get(user_id, [])[-max_messages:]


def add_to_detector_history(user_id: str, role: str, content: str):
    """Добавляет сообщение в историю для детектора."""
    if user_id not in _conversation_history:
        _conversation_history[user_id] = []
    _conversation_history[user_id].append({"role": role, "content": content})
    # Ограничиваем длину истории
    if len(_conversation_history[user_id]) > 20:
        _conversation_history[user_id] = _conversation_history[user_id][-20:]


async def generate_answer(query: str, context_chunks: list, role: str, user_id: int = None) -> str:
    """Генерирует ответ с использованием YandexGPT и поиска Tavily, с fallback при отказе."""
    # Проверка кеша
    cache_key = (query, role)
    if cache_key in cache:
        logger.info(f"✅ Ответ взят из кеша для запроса: {query[:50]}...")
        return cache[cache_key]

    # --- Детектор состояния и антизацикливание ---
    user_id_str = str(user_id) if user_id else "default"

    # Получаем историю диалога для этого пользователя
    history = get_conversation_history_for_detector(user_id_str)

    # Определяем состояние пользователя
    state = detect_user_state(query, history)
    logger.info(f"Состояние пользователя: {state}")

    # Формируем инструкцию для модели в зависимости от состояния
    state_instruction = ""
    if state == "venting":
        state_instruction = (
            "[ВАЖНО] Пользователь сейчас выплёскивает эмоции. "
            "Не задавай вопросов, не перебивай, не советуй. Просто выслушай и покажи, что ты рядом. "
            "Используй фразы: «Я тебя слышу», «Это действительно тяжело», «Расскажи, что чувствуешь»."
        )
    elif state == "angry":
        state_instruction = (
            "[ВАЖНО] Пользователь раздражён и зол. "
            "НЕ переспрашивай, НЕ задавай уточняющих вопросов. Извинись, если это уместно, и сразу переходи к сути. "
            "Будь краток и полезен. Если не знаешь, что сказать, так и скажи: «Давай по делу, я слушаю»."
        )
    elif state == "confused":
        state_instruction = (
            "[ВАЖНО] Пользователь растерян и не знает, что делать. "
            "Предложи 2-3 варианта действий, но не дави. Спроси, какой из вариантов ближе."
        )
    elif state == "new_dialog":
        state_instruction = (
            "[ВАЖНО] Это начало диалога. Поприветствуй пользователя и спроси, что привело его сюда. "
            "Не используй имя, если его ещё не назвали."
        )
    # Для "asking" инструкция не добавляется

    # Проверка на зацикливание по истории
    if len(history) >= 2:
        last_bot_msg = None
        second_last_bot_msg = None
        # Ищем последние два ответа бота в истории
        for msg in reversed(history):
            if msg["role"] == "assistant":
                if last_bot_msg is None:
                    last_bot_msg = msg["content"]
                elif second_last_bot_msg is None:
                    second_last_bot_msg = msg["content"]
                    break

        if last_bot_msg and second_last_bot_msg:
            # Проверка на повторение вопроса про имя
            if "Как мне к вам обращаться?" in last_bot_msg and "Как мне к вам обращаться?" in second_last_bot_msg:
                state_instruction += (
                    "\n[ПРЕДУПРЕЖДЕНИЕ] Ты уже дважды спросил имя. НЕ спрашивай его снова. Просто продолжай диалог."
                )
            # Проверка на повторение уточняющих вопросов
            if any(phrase in last_bot_msg for phrase in ["расскажи", "опиши", "как давно", "сколько времени"]) and \
                    any(phrase in second_last_bot_msg for phrase in
                        ["расскажи", "опиши", "как давно", "сколько времени"]):
                state_instruction += (
                    "\n[ПРЕДУПРЕЖДЕНИЕ] Ты задаёшь похожие вопросы второй раз. НЕ переспрашивай. Сразу дай ответ по существу."
                )

    # Добавляем инструкцию в запрос
    if state_instruction:
        enhanced_query = f"{state_instruction}\n\nЗапрос пользователя: {query}"
    else:
        enhanced_query = query

    # Добавляем сообщение пользователя в историю детектора
    add_to_detector_history(user_id_str, "user", query)
    # --- Конец детектора ---

    if not YC_USE_GPT:
        # Режим без ИИ (только база знаний)
        if not context_chunks:
            return "К сожалению, в моей базе знаний пока нет ответа на этот вопрос."

        response_parts = [f"📚 Вот что я нашёл по вашему вопросу (роль: {role}):\n"]
        for i, chunk in enumerate(context_chunks, 1):
            clean_chunk = chunk
            if chunk.startswith('#'):
                lines = chunk.split('\n', 1)
                if len(lines) > 1:
                    tags = lines[0]
                    content = lines[1]
                    clean_chunk = f"*{tags}*\n\n{content}"
            response_parts.append(f"\n━━━━━━━━━━━━━━━━━━━━\n**Источник {i}**\n\n{clean_chunk}")
        response_parts.append("\n\n💡 *Для более точных ответов включите YandexGPT в настройках.*")
        return "\n".join(response_parts)

    # Режим с ИИ
    try:
        system_prompt = get_system_prompt_for_role(role)
        search_results_text = None

        if TAVILY_USE_SEARCH:
            searcher = get_searcher()
            if searcher:
                logger.info("Запуск Tavily поиска...")
                search_results = await searcher.search(query)
                if search_results:
                    search_results_text = searcher.format_results_for_prompt(search_results)
                    logger.info("Tavily поиск завершён успешно")
                else:
                    logger.warning("Tavily поиск не дал результатов")

        logger.info("Отправка запроса в YandexGPT...")
        answer = await ask_yandex_gpt(
            user_message=enhanced_query,  # Используем улучшенный запрос с инструкцией
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2500,
            search_results=search_results_text,
            user_id=user_id,
            role=role
        )

        # Добавляем ответ бота в историю детектора
        add_to_detector_history(user_id_str, "assistant", answer)

        # ПРОВЕРКА НА ОТКАЗ
        if is_refusal(answer):
            logger.warning(f"YandexGPT вернул отказ: {answer[:100]}")
            # Используем fallback из базы знаний
            fallback = build_fallback_answer(query, context_chunks, role)
            # Кешируем fallback
            cache[cache_key] = fallback
            return fallback

        if answer.startswith(("Ошибка", "Извините", "Произошла ошибка")):
            logger.warning(f"YandexGPT вернул ошибку: {answer[:100]}")
        else:
            logger.info("YandexGPT ответил успешно")

        cache[cache_key] = answer
        return answer

    except asyncio.TimeoutError:
        logger.error("Таймаут при генерации ответа")
        return "Извините, время ожидания ответа истекло. Попробуйте позже."
    except Exception as e:
        logger.error(f"Ошибка в generate_answer: {e}", exc_info=True)
        return f"Произошла ошибка при генерации ответа: {str(e)}"