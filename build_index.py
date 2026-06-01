import os
import pickle
import logging
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KB_PATH = "data/family_advice.txt"

def build_and_save():
    # 1. Загружаем модель
    model = SentenceTransformer('all-MiniLM-L6-v2')
    logger.info("Модель загружена.")

    # 2. Читаем базу знаний
    with open(KB_PATH, 'r', encoding='utf-8') as f:
        text = f.read()

    # 3. Разбиваем на чанки
    raw_chunks = [chunk.strip() for chunk in text.split('\n\n') if chunk.strip()]
    if not raw_chunks:
        raise ValueError("База знаний пуста!")

    # 4. Создаём эмбеддинги
    logger.info(f"Создаю эмбеддинги для {len(raw_chunks)} чанков...")
    embeddings = model.encode(raw_chunks, convert_to_numpy=True)
    faiss.normalize_L2(embeddings)

    # 5. Строим FAISS индекс
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    logger.info(f"Индекс построен, размерность: {dim}.")

    # 6. Сохраняем всё в папку data
    os.makedirs("data", exist_ok=True)
    faiss.write_index(index, "data/family_advice.txt.index")
    with open("data/family_advice.txt.chunks.pkl", 'wb') as f:
        pickle.dump(raw_chunks, f)
    # Чистые чанки (без тегов) тоже сохраним
    import re
    clean_chunks = [re.sub(r'^#[^\n]+\n', '', chunk, flags=re.MULTILINE) for chunk in raw_chunks]
    with open("data/family_advice.txt.chunks_clean.pkl", 'wb') as f:
        pickle.dump(clean_chunks, f)

    logger.info("Индекс и чанки успешно сохранены!")

if __name__ == "__main__":
    build_and_save()