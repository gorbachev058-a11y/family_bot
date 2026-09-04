import asyncio
import logging
import os
from typing import Optional, List, Dict
import json
import redis.asyncio as redis

# Импортируем реальные функции из yandex_gpt
from yandex_gpt import ask_yandex_gpt, get_system_prompt_for_role

# Архитектурные улудшения
from ai_provider import AIProvider
from yandex_gpt import YandexGPTProvider

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройки Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB_CACHE = int(os.getenv("REDIS_DB_CACHE", 1))

redis_cache = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB_CACHE, decode_responses=True)

async def get_cache(key: str):
    data = await redis_cache.get(key)
    if data:
        return json.loads(data)
    return None

async def set_cache(key: str, value: str, ttl: int = 86400):
    await redis_cache.setex(key, ttl, json.dumps(value))

# Глобальные переменные
_searcher = None
_conversation_history: Dict[str, List[Dict[str, str]]] = {}

TAVILY_USE_SEARCH = False
YC_USE_GPT = True

# ============================================================
# 1. ДЕТЕКТОР СОСТОЯНИЙ (без изменений)
# ============================================================
def detect_user_state(query: str, history: list) -> str:
    lower_q = query.lower()
    witness_keywords = [
        "брат бьет", "друг бьет", "родственник бьет", "свидетель",
        "я хочу помочь", "знакомый бьет", "сват бьет", "зять бьет",
        "шурин бьет", "муж сестры", "деверь", "свояк"
    ]
    if any(kw in lower_q for kw in witness_keywords):
        return "witness"

    if len(history) >= 4:
        user_questions = [msg["content"] for msg in history if msg["role"] == "user"]
        if len(user_questions) >= 2:
            last_q = user_questions[-1].lower()
            prev_q = user_questions[-2].lower()
            common_phrases = ["разобраться", "что делать", "как быть", "что мне делать", "как понять", "почему", "что не так"]
            if any(phrase in last_q for phrase in common_phrases) and any(phrase in prev_q for phrase in common_phrases):
                return "repetitive"

    if len(history) < 2:
        return "new_dialog"

    venting_phrases = ["не могу", "устал", "достало", "бесит", "надоело", "как же", "почему", "за что"]
    if any(phrase in lower_q for phrase in venting_phrases) and "?" not in lower_q:
        return "venting"

    anger_phrases = ["зол", "бешен", "взбеси", "разозли", "ненавиж", "терпеть не могу"]
    if any(phrase in lower_q for phrase in anger_phrases):
        return "angry"

    confused_phrases = ["не знаю", "растерян", "не понимаю", "что делать", "как быть", "помогите"]
    if any(phrase in lower_q for phrase in confused_phrases):
        return "confused"

    question_words = ["что", "как", "почему", "зачем", "когда", "где", "кто"]
    if any(qw in lower_q for qw in question_words) and "?" in query:
        return "asking"

    return "asking"

def get_searcher():
    global _searcher
    if _searcher is None and TAVILY_USE_SEARCH:
        # from tavily_search import TavilySearcher
        # _searcher = TavilySearcher()
        pass
    return _searcher

def is_refusal(text: str) -> bool:
    refusal_phrases = [
        "не могу обсуждать", "не могу ответить", "не могу дать ответ",
        "извините, я не могу", "не в моей компетенции", "не могу комментировать",
        "не могу говорить на эту тему", "не могу обсуждать эту тему",
        "не могу помочь", "я не могу", "отказываюсь"
    ]
    lower_text = text.lower()
    return any(phrase in lower_text for phrase in refusal_phrases)

# ============================================================
# 2. FALLBACK (без изменений)
# ============================================================
def build_fallback_answer(query: str, context_chunks: list, role: str) -> str:
    needs_help = any(kw in query.lower() for kw in [
        "насили", "бьёт", "агресс", "побои", "рукоприклад", "угрожа",
        "пьёт", "алкоголь", "не разговаривает", "птср", "сво", "ветеран"
    ])
    is_witness = any(kw in query.lower() for kw in [
        "брат", "друг", "родственник", "свидетель", "я хочу помочь",
        "знакомый", "сват", "зять", "шурин", "деверь", "свояк",
        "муж сестры", "родной брат"
    ])
    answer = ""
    if context_chunks:
        answer = (
            "Я не могу самостоятельно дать ответ на этот вопрос, но вот информация из моей базы знаний, "
            "которая может помочь:\n\n"
        )
        for i, chunk in enumerate(context_chunks[:3], 1):
            clean_chunk = chunk
            if chunk.startswith('#'):
                lines = chunk.split('\n', 1)
                if len(lines) > 1:
                    clean_chunk = lines[1]
            answer += f"**{i}.** {clean_chunk}\n\n"
    if needs_help:
        if is_witness:
            answer += (
                "❗ **Вы — свидетель насилия в семье. Вот что важно:**\n\n"
                "1️⃣ **Не пытайтесь спасать агрессора советами** — это опасно для вас и для жертвы.\n"
                "2️⃣ **Скажите жертве:** «Я рядом, я верю вам. Я помогу». Предложите конкретную помощь (деньги, ночлег, сопровождение).\n"
                "3️⃣ **Договоритесь о сигнале** (слово или эмодзи) для вызова полиции.\n"
                "4️⃣ **Не оправдывайте агрессора его прошлым** — это его ответственность, а не ваша.\n"
                "5️⃣ **Если есть дети** — подумайте об их безопасности, предложите временно забрать их к себе.\n\n"
                "📞 **Телефоны экстренной помощи:**\n"
                "- **112** (единая служба спасения)\n"
                "- **8-800-2000-122** (детский телефон доверия)\n"
                "- **051** (горячая линия для участников СВО и их семей)\n"
                "- Центр социальной поддержки семьи (по месту жительства)\n\n"
                "Помните: насилие недопустимо, вы не одни. ✅"
            )
        else:
            answer += (
                "❗ **Если вы или ваши близкие подвергаются насилию, немедленно обратитесь за помощью:**\n"
                "- **112** (единая служба спасения)\n"
                "- **8-800-2000-122** (детский телефон доверия)\n"
                "- **051** (горячая линия для участников СВО и их семей)\n"
                "- Центр социальной поддержки семьи (по месту жительства)\n\n"
                "Помните: насилие недопустимо, вы не одни. ✅"
            )
            if any(kw in query.lower() for kw in ["разобраться в себе", "понять себя", "что делать"]):
                exercises = (
                    "\n\n**Практические упражнения для самоанализа:**\n"
                    "1. **Дневник чувств**: Каждый вечер записывайте 3 эмоции, которые испытывали за день, и что их вызвало.\n"
                    "2. **Техника «пустой стул»**: Представьте, что напротив сидит ваша девушка. Скажите ей вслух всё, что хотели бы сказать, а затем представьте её ответ.\n"
                    "3. **Список ожиданий**: Напишите два списка — что вы ждали от отношений и что вы давали. Сравните.\n"
                    "4. **Вопросы к себе**: «Что я могу изменить в себе, чтобы быть счастливым независимо от партнёра?»\n"
                    "5. **Визуализация будущего**: Представьте свою жизнь через 5 лет — с ней и без неё. Что вам ближе?\n"
                )
                answer += exercises
        return answer
    else:
        if not context_chunks:
            return (
                "Извините, я не могу ответить на этот вопрос через интернет, "
                "но вы можете обратиться к психологу очно или по телефону доверия **8-800-2000-122**. "
                "Ваша ситуация важна, помощь рядом."
            )
        return answer

def get_conversation_history_for_detector(user_id: str = "default", max_messages: int = 4) -> list:
    return _conversation_history.get(user_id, [])[-max_messages:]

def add_to_detector_history(user_id: str, role: str, content: str):
    if user_id not in _conversation_history:
        _conversation_history[user_id] = []
    _conversation_history[user_id].append({"role": role, "content": content})
    if len(_conversation_history[user_id]) > 20:
        _conversation_history[user_id] = _conversation_history[user_id][-20:]

# ============================================================
# 3. ОСНОВНАЯ ФУНКЦИЯ GENERATE_ANSWER (ИСПРАВЛЕНА)
# ============================================================
async def generate_answer(query: str, context_chunks: list, role: str, user_id: int = None, ai_provider: Optional[AIProvider] = None) -> str:
    # Проверка кеша
    cache_key = f"{query}:{role}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"✅ Ответ взят из Redis-кеша для запроса: {query[:50]}...")
        return cached

    # --- Детектор состояния ---
    user_id_str = str(user_id) if user_id else "default"
    history = get_conversation_history_for_detector(user_id_str)
    state = detect_user_state(query, history)
    logger.info(f"Состояние пользователя: {state}")

    state_instruction = ""
    if state == "venting":
        state_instruction = (
            "[ВАЖНО] Пользователь сейчас выплёскивает эмоции. "
            "Не задавай вопросов, не перебивай, не советуй. Просто выслушай и покажи, что ты рядом. "
            "Используй фразы: «Я тебя слышу», «Это действительно тяжело», «Расскажи, что чувствуёшь»."
        )
    elif state == "repetitive":
        state_instruction = (
            "[ВАЖНО] Пользователь уже задавал похожий вопрос ранее. "
            "НЕ задавай уточняющих вопросов и НЕ переспрашивай. "
            "Сразу дай прямой, конкретный и практический ответ без дополнительных вопросов. "
            "Используй максимум информации из базы знаний, чтобы дать полезные упражнения или техники."
        )
    elif state == "angry":
        state_instruction = (
            "[ВАЖНО] Пользователь раздражён и зол. "
            "НЕ переспрашивай, зен. Если не знаешь, что сказать, так и скажи: «Давай по делу, я слушаю»."
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
    elif state == "witness":
        state_instruction = (
            "[ВАЖНО] Пользователь — свидетель насилия в чужой семье. "
            "Он хочет помочь, но не знает как. Не давай советов напрямую агрессору. "
            "Сосредоточься на том, как поддержать жертву и как безопасно действовать свидетелю. "
            "Не предлагай 'план действий' в общем виде — лучше дай конкретные шаги для свидетеля. "
            "Обязательно спроси, есть ли в этой семье дети, и предложи подумать об их безопасности. "
            "Не обесценивай ситуацию фразами «всё будет хорошо». "
            "Помни: твоя задача — не спасать агрессора, а помогать жертве и свидетелю сохранить безопасность."
        )

    # Антизацикливание
    if len(history) >= 2:
        last_bot_msg = None
        second_last_bot_msg = None
        for msg in reversed(history):
            if msg["role"] == "assistant":
                if last_bot_msg is None:
                    last_bot_msg = msg["content"]
                elif second_last_bot_msg is None:
                    second_last_bot_msg = msg["content"]
                    break
        if last_bot_msg and second_last_bot_msg:
            if "Как мне к вам обращаться?" in last_bot_msg and "Как мне к вам обращаться?" in second_last_bot_msg:
                state_instruction += "\n[ПРЕДУПРЕЖДЕНИЕ] Ты уже дважды спросил имя. НЕ спрашивай его снова. Просто продолжай диалог."
            if any(phrase in last_bot_msg for phrase in ["расскажи", "опиши", "как давно", "сколько времени"]) and \
                    any(phrase in second_last_bot_msg for phrase in ["расскажи", "опиши", "как давно", "сколько времени"]):
                state_instruction += "\n[ПРЕДУПРЕЖДЕНИЕ] Ты задаёшь похожие вопросы второй раз. НЕ переспрашивай. Сразу дай ответ по существу."
            if "чувствуешь" in last_bot_msg and "чувствуешь" in second_last_bot_msg:
                state_instruction += "\n[ПРЕДУПРЕЖДЕНИЕ] Ты уже дважды спросил о чувствах. НЕ переспрашивай. Дай конкретный совет или поддержку без вопросов."

    if state_instruction:
        enhanced_query = f"{state_instruction}\n\nЗапрос пользователя: {query}"
    else:
        enhanced_query = query

    add_to_detector_history(user_id_str, "user", query)

    # Если YandexGPT выключен — только база знаний
    if not YC_USE_GPT:
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

    # --- Режим с ИИ ---
    try:
        system_prompt = get_system_prompt_for_role(role)
        search_results_text = None
        if TAVILY_USE_SEARCH:
            searcher = get_searcher()
            if searcher:
                logger.info("Запуск Tavily поиска...")
                # тут реальный вызов

        # Если провайдер не передан, создаём экземпляр YandexGPTProvider
        if ai_provider is None:
            ai_provider = YandexGPTProvider()

        logger.info("Отправка запроса в YandexGPT...")
        answer = await ai_provider.generate_response(
            prompt=enhanced_query,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2500,
            search_results=search_results_text,
            user_id=user_id,
            role=role
        )

        add_to_detector_history(user_id_str, "assistant", answer)

        if is_refusal(answer):
            logger.warning(f"YandexGPT вернул отказ: {answer[:100]}")
            fallback = build_fallback_answer(query, context_chunks, role)
            await set_cache(cache_key, fallback, 86400)
            return fallback

        if answer.startswith(("Ошибка", "Извините", "Произошла ошибка")):
            logger.warning(f"YandexGPT вернул ошибку: {answer[:100]}")
        else:
            logger.info("YandexGPT ответил успешно")

        await set_cache(cache_key, answer, 86400)
        return answer

    except asyncio.TimeoutError:
        logger.error("Таймаут при генерации ответа")
        return "Извините, время ожидания ответа истекло. Попробуйте позже."
    except Exception as e:
        logger.error(f"Ошибка в generate_answer: {e}", exc_info=True)
        return f"Произошла ошибка при генерации ответа: {str(e)}"