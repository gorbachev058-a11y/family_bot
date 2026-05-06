import asyncio
import logging
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_relevancy

# Импортируем ваши рабочие функции из проекта
from knowledge_base import KnowledgeBase
from rag import generate_answer

# Настройка логирования (чтобы видеть процесс)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализируем базу знаний (один раз, чтобы не пересоздавать индекс)
kb = KnowledgeBase("data/family_advice.txt")

# Тестовые вопросы — должны покрывать разные темы из новых чанков
TEST_QUESTIONS = [
    "Что делать матери ребенка-инвалида?",
    "Как одинокой маме справиться с выгоранием?",
    "Как объяснить учителю особенности ребенка с СДВГ?",
    "Как наладить отношения с мужем после измены?",
    "Что делать, если подросток не хочет учиться?",
]

# Фиксированная роль для тестов (можно оставить "пара" или "жена")
TEST_ROLE = "пара"
# Фиктивный user_id для тестов
TEST_USER_ID = 999999

async def run_test_pipeline():
    """Прогоняет тестовые вопросы через ваш RAG и собирает ответы + контексты."""
    questions = []
    answers = []
    contexts = []

    for q in TEST_QUESTIONS:
        logger.info(f"\n🔹 Обработка вопроса: {q}")
        # 1. Поиск в FAISS
        retrieved_chunks = kb.search(q, top_k=5)
        # 2. Генерация ответа
        answer = await generate_answer(
            query=q,
            context_chunks=retrieved_chunks,
            role=TEST_ROLE,
            user_id=TEST_USER_ID
        )
        questions.append(q)
        answers.append(answer)
        contexts.append(retrieved_chunks)  # RAGAS ожидает список чанков для каждого вопроса
        logger.info(f"   Ответ получен: {answer[:100]}...")

    # Формируем датасет в формате RAGAS
    data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
    }
    dataset = Dataset.from_dict(data)

    # Оцениваем
    logger.info("\n📊 Запуск оценки RAGAS...")
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_relevancy],
    )

    # Выводим результаты
    print("\n========== РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ RAG ==========")
    print(result)
    print("==================================================\n")

    # Дополнительно можно сохранить результат в CSV
    df = result.to_pandas()
    df.to_csv("rag_test_results.csv", index=False)
    logger.info("Результаты сохранены в rag_test_results.csv")

if __name__ == "__main__":
    asyncio.run(run_test_pipeline())