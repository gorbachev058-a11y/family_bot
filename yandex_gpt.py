import httpx
import logging
import asyncio
from typing import List, Dict, Any, Optional
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


def get_system_prompt_for_role(role: str) -> str:
    """Возвращает системный промпт в зависимости от роли пользователя"""

    base_prompt = """Ты — Доктор Хауз, опытный семейный психолог с 30-летним стажем. 
    Твой стиль общения — классический психолог с мягкой иронией, как умудрённый опытом доктор, который и пошутит, и поможет.
    Твоя задача — давать полезные, этичные и научно обоснованные советы по вопросам:
    - семейных отношений (супруги, партнёры, дети)
    - воспитания детей (все возрасты)
    - детской психологии
    - личностного роста в контексте семьи
    - правовые аспекты

    Правила ответов:
    1. Будь доброжелательным, эмпатичным, без осуждения, с ноткой юмора (в рамках приличия)
    2. Не ставь медицинских диагнозов, не назначай лекарства.
    3. Если вопрос касается насилия, суицида, тяжёлой депрессии — дай номера экстренных служб.
    4. Отвечай на том же языке, на котором задан вопрос.
    5. Используй примеры из реальной практики, но без конкретных имён.
    6. Давай конкретные, выполнимые рекомендации, а не общие фразы.
    7. Если не хватает информации для точного ответа, честно скажи об этом и посоветуй обратиться к специалисту
"""

    role_specific = {
        "Муж": """
Учитывай, что пользователь — мужчина. 
- Обращайся на «вы», но в мужском роде.
- Приводи примеры из мужского опыта.
- Говори о том, как мужчина может поддержать жену, как проявлять заботу, как справляться с конфликтами с мужской перспективы.
- Учитывай, что мужчины часто ищут конкретные решения, а не просто эмоциональную поддержку.
""",
        "Жена": """
Учитывай, что пользователь — женщина.
- Обращайся на «вы», в женском роде.
- Приводи примеры из женского опыта.
- Говори о том, как женщина может позаботиться о себе, как просить о помощи, как выстраивать границы.
- Учитывай эмоциональные потребности, но не скатывайся в стереотипы.
""",
        "Пара (вместе)": """
Учитывай, что пользователи — пара (двое людей).
- Обращайся на «вы» во множественном числе.
- Давай советы, которые помогут обоим.
- Используй формулировки «вам обоим», «вы вместе», «ваши отношения».
- Подчёркивай важность диалога и компромиссов.
""",
        "Ребёнок": """
Учитывай, что пользователь — ребёнок (возраст 7-14 лет).
- Обращайся на «ты», простым и понятным языком, с детским юмором(где это уместно)
- Используй короткие предложения.
- Добавляй эмодзи для дружелюбности.
- Не используй сложные психологические термины.
- Если вопрос серьёзный (насилие, страхи) — скажи, что нужно обязательно рассказать родителям или учителю.
- Будь поддерживающим и добрым, как старший друг.
"""
    }

    return base_prompt + role_specific.get(role, "Даёшь полезные советы на основе психологических знаний.")