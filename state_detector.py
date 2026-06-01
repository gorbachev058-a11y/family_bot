# state_detector.py

import re

def detect_user_state(message: str, history: list = None) -> str:
    """
    Определяет состояние пользователя по его сообщению и истории диалога.
    Возвращает одно из:
    - "venting" — пользователь выплёскивает эмоции, нужно валидировать и слушать.
    - "confused" — пользователь не знает, что делать, нужны варианты.
    - "asking" — конкретный запрос, можно отвечать фактами.
    - "angry" — пользователь раздражён, нельзя переспрашивать и тупить.
    - "new_dialog" — первый запрос в диалоге.
    """
    msg_lower = message.lower().strip()

    # Явные маркеры раздражения
    angry_markers = ['тупой', 'залип', 'не понимаешь', 'сколько можно', 'бесит', 'достало', 'хватит']
    if any(marker in msg_lower for marker in angry_markers):
        return "angry"

    # Если это первое сообщение (история пуста или нет контекста)
    if not history or len(history) <= 1:
        return "new_dialog"

    # Эмоциональные маркеры (выплёскивание)
    venting_markers = ['больно', 'страшно', 'не могу', 'плачу', 'тоскливо', 'одиноко', 'безнадёжно',
                       'меня бесит', 'достало', 'ненавижу', 'не хочу жить']
    if any(marker in msg_lower for marker in venting_markers):
        return "venting"

    # Маркеры растерянности
    confused_markers = ['не знаю', 'что делать', 'как быть', 'подскажи', 'посоветуй', 'не понимаю']
    if any(marker in msg_lower for marker in confused_markers):
        return "confused"

    # По умолчанию — конкретный запрос
    return "asking"