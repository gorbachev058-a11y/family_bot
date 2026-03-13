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


async def generate_answer(query: str, context_chunks: list, role: str, user_id: int = None) -> str:
    # Проверка кеша
    cache_key = (query, role)
    if cache_key in cache:
        logger.info(f"✅ Ответ взят из кеша для запроса: {query[:50]}...")
        return cache[cache_key]
    """
    Генерирует ответ с использованием YandexGPT и Tavily поиска.
    """
    if not YC_USE_GPT:
        # Режим без ИИ (заглушка)
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
            user_id=user_id,  # передаём
            role=role  # и роль
        )

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