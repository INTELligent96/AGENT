from pathlib import Path
from .indexer import RAGIndexer
from llm.registry import LLMRegistry

class RAGQuestionAnswerer:
    def __init__(self, config: dict, tools_config: dict, registry: LLMRegistry):
        self.indexer = RAGIndexer(config, tools_config)
        self.registry = registry

    def ask(self, question: str) -> str:
        print(f"Поиск по базе для вопроса: '{question}'...")
        context_chunks = self.indexer.search(question, top_k=5)

        if not context_chunks:
            return "В базе данных не найдено информации по этому вопросу."

        context_text = ""
        for i, chunk in enumerate(context_chunks, 1):
            source = Path(chunk['source']).name
            context_text += f"--- Фрагмент {i} (Источник: {source}, часть {chunk['chunk_id']}) ---\n"
            context_text += chunk['text'] + "\n\n"

        system_prompt = (
            "Ты — ассистент по работе с документами. Отвечай на вопрос пользователя, "
            "ОПИРАЯСЬ ТОЛЬКО на предоставленные фрагменты текста. "
            "Если в тексте нет ответа, честно скажи, что не знаешь. "
            "Обязательно указывай, из какого файла взята информация. "
            "Отвечай кратко и по делу."
        )

        user_prompt = f"КОНТЕКСТ:\n{context_text}\n\nВОПРОС: {question}"

        print("Запуск отказоустойчивой генерации (complex_reasoning)...")
        return self.registry.generate_with_fallback("complex_reasoning", user_prompt, system_prompt)
