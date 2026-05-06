# advice.py
import random
import os

ADVICE_FILE = "data/daily_advice.txt"

def get_daily_advice():
    """Возвращает случайный совет дня."""
    if os.path.exists(ADVICE_FILE):
        with open(ADVICE_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if lines:
            return random.choice(lines)
    # Запасные советы
    default_advice = [
        "Проведите время с семьёй без гаджетов.",
        "Слушайте друг друга, не перебивая.",
        "Выражайте благодарность каждый день.",
        "Уделите 15 минут разговору по душам.",
        "Помните: вы команда.",
        "Обнимите близкого человека.",
        "Скажите что-то приятное без повода."
    ]
    return random.choice(default_advice)