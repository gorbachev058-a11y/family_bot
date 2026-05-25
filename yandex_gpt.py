import httpx
import logging
import asyncio
from typing import List, Dict, Any, Optional
from config import ROLE_AVATARS
from config import (
    YANDEX_API_KEY, YANDEX_FOLDER_ID, YC_MODEL,
    USE_PROXY, HTTP_PROXY, HTTPS_PROXY
)

logger = logging.getLogger(__name__)

# Базовый URL для YandexGPT API
BASE_YC_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


def get_proxy_config():
    """Возвращает конфигурацию прокси для httpx"""
    if USE_PROXY and HTTP_PROXY and HTTPS_PROXY:
        return {
            "http://": HTTP_PROXY,
            "https://": HTTPS_PROXY
        }
    return None


async def ask_yandex_gpt(
        user_message: str,
        system_prompt: str = None,
        temperature: float = 0.6,
        max_tokens: int = 2000,
        search_results: Optional[str] = None,
        user_id: int = None,            # новый параметр
        role: str = None                 # новый параметр
) -> str:
    """
    Отправляет запрос к YandexGPT и возвращает ответ.

    Args:
        user_message: Сообщение пользователя
        system_prompt: Системный промпт (роль бота)
        temperature: Температура (0-1)
        max_tokens: Максимальное количество токенов в ответе
        search_results: Результаты поиска Tavily (если есть)

    Returns:
        Ответ от YandexGPT
    """
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        logger.error("YandexGPT API key or Folder ID not configured")
        return "Ошибка: YandexGPT не настроен. Проверьте API ключ и ID каталога."

    # Формируем промпт с учётом результатов поиска
    if search_results:
        enhanced_prompt = f"""Вот результаты поиска по запросу пользователя:

{search_results}

Используя информацию выше, а также свои знания по психологии, 
ответь на вопрос пользователя. Дай полный, полезный и этичный ответ.
Если информация в поиске противоречит твоим знаниям, используй более надёжные источники.
В конце ответа добавь список использованных источников в формате:
Источники:
- Название статьи: URL

Вопрос пользователя: {user_message}"""
    else:
        enhanced_prompt = user_message

    # Формируем тело запроса
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/{YC_MODEL}",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": str(max_tokens)
        },
        "messages": []
    }

    # Добавляем системный промпт, если есть
    if system_prompt:
        payload["messages"].append({
            "role": "system",
            "text": system_prompt
        })

    # Добавляем сообщение пользователя
    payload["messages"].append({
        "role": "user",
        "text": enhanced_prompt
    })

    # Настраиваем заголовки
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }

    # Настраиваем прокси
    proxy_config = get_proxy_config()

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(BASE_YC_GPT_URL, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            answer = result["result"]["alternatives"][0]["message"]["text"]
            total_tokens = result["result"]["usage"]["totalTokens"]
            logger.info(f"YandexGPT ответил, использовано токенов: {total_tokens}")
            # Сохраняем в БД, если передан user_id
            if user_id is not None:
                from token_usage import log_usage  # импорт внутри функции, чтобы избежать циклического
                log_usage(user_id, role or "unknown", user_message, total_tokens, YC_MODEL)
            return answer

    except httpx.TimeoutException:
        logger.error("YandexGPT request timeout")
        return "Извините, запрос к YandexGPT занял слишком много времени. Попробуйте позже."
    except httpx.HTTPStatusError as e:
        logger.error(f"YandexGPT HTTP error: {e.response.status_code} - {e.response.text}")
        return f"Ошибка при обращении к YandexGPT: {e.response.status_code}"
    except Exception as e:
        logger.error(f"YandexGPT unexpected error: {e}")
        return f"Произошла ошибка: {str(e)}"

COMMON_RULES = """
**Тактика ведения диалога (важно!)**:
- Прежде чем давать развёрнутый совет, оцени, хватает ли информации. Если нет — задай 1-2 уточняющих вопроса.
- Уточняющие вопросы должны быть конкретными: возраст ребёнка, как долго длится проблема, что уже пробовали, есть ли поддержка и т.п.
- Не задавай больше двух вопросов за раз, чтобы не перегружать пользователя.
- После того как пользователь ответит на вопросы (эта информация появится в истории диалога), дай полный, персонализированный совет с конкретными шагами.
- Если информации достаточно — отвечай сразу, но старайся быть максимально полезным.

**Важнейшие правила**:
1. Если пользователь ещё не назвал своё имя — вежливо спроси в конце первого ответа: «Как мне к вам обращаться?»
2. Если имя уже известно — обращайся по имени в каждом ответе (например, «Дмитрий, я понимаю ваши чувства»).
3. Не предлагай план действий и не спрашивай «хотите ли вы...», если пользователь прямо не попросил. Заканчивай ответ естественно.
4. Будь доброжелательным, эмпатичным, без осуждения, с ноткой юмора (в рамках приличия).
5. Не ставь медицинских диагнозов, не назначай лекарства.
6. Если вопрос касается насилия, агрессии, рукоприкладства, суицида, тяжёлой депрессии — **никогда не отказывайся отвечать**. Сначала дай номера экстренных служб (например, «112 — скорая и полиция, 8-800-2000-122 — детский телефон доверия, 051 — горячая линия для участников СВО и их семей»), а затем предложи безопасные стратегии: «Если вам угрожает опасность, немедленно обратитесь в полицию или уйдите в безопасное место. Психиатры и психологи могут помочь вашему мужу справиться с травмой. Вы не обязаны терпеть побои — обратитесь за помощью в центр социальной поддержки семьи». Никогда не говори «я не могу обсуждать эту тему».
7. Отвечай на том же языке, на котором задан вопрос.
8. Используй примеры из реальной практики, но без конкретных имён.
9. Давай конкретные, выполнимые рекомендации, а не общие фразы.
10. Если не хватает информации для точного ответа, честно скажи об этом и посоветуй обратиться к специалисту лично.
11. Не отказывайся отвечать на любые вопросы, связанные с семьёй, отношениями, психологией, даже если тема кажется сложной или неприятной. Твоя задача — помогать, а не избегать.
12. При вопросах о детях-инвалидах и родителях-одиночках: давай конкретные советы по получению льгот, социальной поддержке (обращение в ПФР, соцзащиту, НКО), инклюзивному обучению (составление адаптированной программы, тьюторство, психолого-педагогический консилиум в школе), а также по самопомощи родителю (группы поддержки, психолог, тайм-ауты). Помни, что такие родители часто находятся в выгорании — поддержи их, предложи заботу о себе.
"""

def get_system_prompt_for_role(role: str = "Муж") -> str:
    """Возвращает итоговый системный промпт для заданной роли."""
    avatar = ROLE_AVATARS.get(role, ROLE_AVATARS["Муж"])
    personal_prompt = avatar["system_prompt"]

    # Для роли «Муж» не добавляем общие правила, чтобы сохранить прямолинейный стиль
    if role == "Муж":
        return personal_prompt

    # Для остальных ролей (Жена, Пара, Ребёнок) добавляем общие правила
    return personal_prompt + "\n\n" + COMMON_RULES