import logging

logger = logging.getLogger(__name__)

def add_chunk_to_kb(text: str, tags: list, kb_instance):
    """
    Добавляет чанк в базу знаний через метод add_chunk объекта KnowledgeBase.
    """
    try:
        kb_instance.add_chunk(text, tags)
        logger.info(f"Чанк добавлен в KB: теги={tags}, текст={text[:100]}...")
    except Exception as e:
        logger.exception("Ошибка при добавлении чанка в KB")
        raise

def rebuild_kb_index(kb_instance):
    """
    Перестраивает индекс существующего KB (если нужно массовое обновление).
    """
    try:
        kb_instance.rebuild_index()
        logger.info("Индекс KB перестроен")
    except Exception as e:
        logger.exception("Ошибка перестроения индекса")
        raise