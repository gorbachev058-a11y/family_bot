import os
import uuid
import logging
from pydub import AudioSegment
import speech_recognition as sr
import openai
from config import STT_ENGINE, OPENAI_API_KEY, TEMP_DIR

logger = logging.getLogger(__name__)

if STT_ENGINE == "whisper" and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

async def recognize_google(audio_bytes: bytes) -> str:
    """Распознавание речи через Google Speech Recognition"""
    ogg_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.ogg")
    wav_path = ogg_path.replace(".ogg", ".wav")
    try:
        with open(ogg_path, "wb") as f:
            f.write(audio_bytes)

        sound = AudioSegment.from_ogg(ogg_path)
        sound.export(wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data, language="ru-RU")
        return text
    except sr.UnknownValueError:
        return "Не удалось распознать речь"
    except Exception as e:
        logger.error(f"Google STT error: {e}")
        return "Ошибка при обработке аудио"
    finally:
        for path in [ogg_path, wav_path]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass

async def recognize_whisper(audio_bytes: bytes) -> str:
    """Распознавание через OpenAI Whisper API"""
    if not OPENAI_API_KEY:
        return "Whisper API ключ не настроен"
    temp_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.ogg")
    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)
        with open(temp_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe("whisper-1", audio_file, language="ru")
        return transcript.text
    except Exception as e:
        logger.error(f"Whisper error: {e}")
        return "Ошибка при распознавании через Whisper"
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except:
            pass

async def recognize_speech(audio_bytes: bytes) -> str:
    """Общая функция распознавания"""
    if STT_ENGINE == "whisper" and OPENAI_API_KEY:
        return await recognize_whisper(audio_bytes)
    else:
        return await recognize_google(audio_bytes)