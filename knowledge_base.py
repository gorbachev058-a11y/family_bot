import os
import pickle
import logging
import re
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

logger = logging.getLogger(__name__)


class KnowledgeBase:
    def __init__(self, kb_path: str, model_name: str = 'all-MiniLM-L6-v2'):
        self.kb_path = kb_path
        self.model = SentenceTransformer(model_name)
        self.chunks = []
        self.chunks_without_tags = []
        self.index = None
        self._load_or_build()

    def _load_or_build(self):
        index_file = self.kb_path + '.index'
        chunks_file = self.kb_path + '.chunks.pkl'
        chunks_clean_file = self.kb_path + '.chunks_clean.pkl'

        if os.path.exists(index_file) and os.path.exists(chunks_file):
            logger.info("Загрузка существующего индекса...")
            self.index = faiss.read_index(index_file)
            with open(chunks_file, 'rb') as f:
                self.chunks = pickle.load(f)
            with open(chunks_clean_file, 'rb') as f:
                self.chunks_without_tags = pickle.load(f)
        else:
            logger.info("Создание нового индекса...")
            self._build_index()
            faiss.write_index(self.index, index_file)
            with open(chunks_file, 'wb') as f:
                pickle.dump(self.chunks, f)
            with open(chunks_clean_file, 'wb') as f:
                pickle.dump(self.chunks_without_tags, f)
            logger.info("Индекс сохранён.")

    def _build_index(self):
        with open(self.kb_path, 'r', encoding='utf-8') as f:
            text = f.read()

        # Разделяем по пустым строкам
        raw_chunks = [chunk.strip() for chunk in text.split('\n\n') if chunk.strip()]

        self.chunks = []
        self.chunks_without_tags = []

        for chunk in raw_chunks:
            self.chunks.append(chunk)
            # Убираем теги из начала
            clean_chunk = re.sub(r'^#[^\n]+\n', '', chunk, flags=re.MULTILINE)
            self.chunks_without_tags.append(clean_chunk)

        if not self.chunks:
            self.chunks = ["База знаний пуста. Добавьте тексты в файл."]
            self.chunks_without_tags = ["База знаний пуста. Добавьте тексты в файл."]

        # Индексируем чистые чанки (без тегов)
        embeddings = self.model.encode(self.chunks_without_tags, convert_to_numpy=True)
        faiss.normalize_L2(embeddings)
        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)
        logger.info(f"Индекс построен, {len(self.chunks)} чанков.")

    def hybrid_search(self, query: str, top_k: int = 5, keyword_weight: float = 0.3):
        """Гибридный поиск: эмбеддинги + ключевые слова"""
        # Сначала эмбеддинг-поиск
        emb_results = self.search(query, top_k=top_k * 2)  # берём больше кандидатов

        # Простая фильтрация по ключевым словам из запроса
        keywords = set(query.lower().split())
        important_keywords = {'дочк', 'разговарива', 'молчит', 'ребенк', 'дет', 'общени'}

        scored = []
        for chunk in emb_results:
            score = 0
            chunk_lower = chunk.lower()
            # Бонус за важные ключевые слова
            for kw in important_keywords:
                if kw in chunk_lower:
                    score += 0.2
            scored.append((score, chunk))

        # Сортируем по бонусу и берём top_k
        scored.sort(reverse=True, key=lambda x: x[0])
        return [chunk for score, chunk in scored[:top_k]]

    def search(self, query: str, top_k: int = 5):
        """
        Ищет top_k похожих чанков. Возвращает оригинальные чанки (с тегами).
        """
        if not self.chunks or self.index is None or self.index.ntotal == 0:
            logger.warning("База знаний пуста")
            return []

        # Кодируем запрос
        logger.info(f"Поиск по запросу: '{query}'")
        query_emb = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_emb)

        # Ищем чанки
        search_k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_emb, search_k)

        results = []
        logger.info(f"📊 Найдено {len(indices[0])} чанков")
        for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
            chunk_text = self.chunks[idx]
            # Логируем оценку, индекс и начало чанка (без лишних переносов)
            preview = chunk_text[:200].replace('\n', ' ') + "..." if len(chunk_text) > 200 else chunk_text.replace('\n',
                                                                                                                   ' ')
            logger.info(f"  {i + 1}. Оценка: {score:.4f} | Индекс: {idx} | Текст: {preview}")
            results.append(chunk_text)

        return results