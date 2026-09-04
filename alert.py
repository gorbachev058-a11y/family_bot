# alert.py
import os
import asyncio
from aiogram import Bot

ALERT_BOT_TOKEN = os.getenv("ALERT_BOT_TOKEN")  # Токен отдельного бота для оповещений
ALERT_CHAT_ID = os.getenv("ALERT_CHAT_ID")     # ID чата/пользователя для уведомлений

bot = None

def init_alert_bot():
    global bot
    if ALERT_BOT_TOKEN and ALERT_CHAT_ID:
        bot = Bot(token=ALERT_BOT_TOKEN)

async def send_alert(message: str):
    if bot:
        try:
            await bot.send_message(ALERT_CHAT_ID, f"🚨 {message}")
        except Exception as e:
            print(f"Не удалось отправить оповещение: {e}")