import logging
import asyncio
from config import YC_USE_GPT, TAVILY_USE_SEARCH
from yandex_gpt import ask_yandex_gpt, get_system_prompt_for_role
from tavily_search import TavilySearcher
from cachetools import TTLCache

# Кеш для ответов: максимум 200 элементов, TTL 3600 секунд (1 час)
cache = TTLCache(maxsize=200, ttl=3600)

logger = logging.getLogger(__name__)

_searcher = None


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


async def generate_answer(query: str, context_chunks: list, role: str, user_id: int = None) -> str:
    """Генерирует ответ с использованием YandexGPT и поиска Tavily, с fallback при отказе."""
    # Проверка кеша
    cache_key = (query, role)
    if cache_key in cache:
        logger.info(f"✅ Ответ взят из кеша для запроса: {query[:50]}...")
        return cache[cache_key]

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
            user_message=query,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2500,
            search_results=search_results_text,
            user_id=user_id,
            role=role
        )

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